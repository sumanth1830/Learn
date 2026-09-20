import os
import time
import boto3
import tempfile

import mlflow
from celery import shared_task

from .models import (
    Question, Answer, Quiz, SourceText, QuizAggregateMetrics,
    QuizGenerationLog, QuizNodeCost, QuizTrace,
)
from celery.exceptions import SoftTimeLimitExceeded
from agentic_app.workflow import get_graph
from agentic_app.schema import QuizDetails
from django.utils import timezone
from datetime import timedelta
from quizmaker.pib_ingestion import poll_pib_feed
from quizmaker.rag_chunking import save_chunks_for_source_text
from .digest_tasks import generate_daily_digest_task, retry_daily_digest_task
from .topics_preview_tasks import generate_topics_preview_task


GUARDRAIL_USER_MESSAGES = {
    "injection": "Your instructions couldn't be processed as a quiz customization request. Please revise and try again.",
    "manipulative": "Your instructions couldn't be processed as a fair quiz request. Please revise and try again.",
    "off_topic": "Your instructions included something unrelated to creating a quiz. Please revise and try again.",
    "profanity": "Your request couldn't be processed as written. Please revise and try again.",
    "inappropriate_source": "The uploaded document doesn't look like educational material we can build a quiz from. Please try a different file.",
}

SAFETY_USER_MESSAGES = {
    "gratuitous_detail": "We weren't able to generate an appropriately-toned quiz from this material. Please try again or use a different source document.",
    "tone_mismatch": "We weren't able to generate an appropriately-toned quiz from this material. Please try again or use a different source document.",
}


def extract_text_from_pdf(pdf_path):
    """
    Llama Parse First, in the event of failure
    Docling gets executed
    """
    try:
        return _extract_with_llamaparse(pdf_path)
    except Exception as e:
        print(f"[extract] LlamaParse failed, falling back to Docling: {e}")
        return _extract_with_docling(pdf_path)


def _extract_with_llamaparse(pdf_path):
    from llama_cloud import LlamaCloud

    print("Llama Parse Extraction.....")
    api_key = os.getenv("LLAMA_CLOUD_API_KEY")
    if not api_key:
        raise RuntimeError("LLAMA_CLOUD_API_KEY not set")

    base_url = os.getenv("LLAMA_CLOUD_BASE_URL")
    client = LlamaCloud(api_key=api_key, base_url=base_url)

    with open(pdf_path, "rb") as f:
        result = client.parsing.parse(
            upload_file=f,
            tier="cost_effective",
            version="latest",
            expand=["markdown"],
        )

    pages = result.markdown.pages
    return "\n\n".join(page.markdown for page in pages)


def _extract_with_docling(pdf_path):
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_table_structure = True
    pipeline_options.accelerator_options = AcceleratorOptions(num_threads=8, device="cpu")

    print("Falling back to Docling.....")
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )
    result = converter.convert(pdf_path)
    return result.document.export_to_markdown()


def extract_trace_cost_breakdown(trace):
    spans = trace.data.spans
    span_by_id = {s.span_id: s for s in spans}

    def find_agent_ancestor(span):
        current = span
        while current:
            parent_id = getattr(current, "parent_id", None)
            if not parent_id or parent_id not in span_by_id:
                return None
            parent = span_by_id[parent_id]
            name = getattr(parent, "name", "")
            if name.endswith("_agent") or name.endswith("_node"):
                return name
            current = parent
        return None

    node_breakdown = []
    total_cost = 0.0

    for span in spans:
        if span.name == "ChatOpenAI":
            cost_data = span.llm_cost or {}
            tokens = span.get_attribute("mlflow.chat.tokenUsage") or {}
            model = span.get_attribute("mlflow.llm.model")
            agent = find_agent_ancestor(span) or "unknown"

            span_total_cost = cost_data.get("total_cost") or 0.0

            node_breakdown.append({
                "agent": agent,
                "model": model,
                "cost": span_total_cost,
                "input_cost": cost_data.get("input_cost") or 0.0,
                "output_cost": cost_data.get("output_cost") or 0.0,
                "prompt_tokens": tokens.get("input_tokens"),
                "completion_tokens": tokens.get("output_tokens"),
                "duration_seconds": (span.end_time_ns - span.start_time_ns) / 1e9,
            })
            total_cost += span_total_cost

    return node_breakdown, total_cost


def _fetch_trace_data(quiz):
    """
    Shared by every entry point that runs graph.invoke() - fresh
    creation, retry, and resume all need this identical logic.
    Returns (trace_id, node_breakdown, total_cost, total_time_seconds).
    """
    trace_id = None
    node_breakdown = []
    total_cost = 0.0
    total_time_seconds = None
    try:
        trace_id = mlflow.get_last_active_trace_id()
        if trace_id:
            trace = mlflow.get_trace(trace_id=trace_id, flush=True)
            node_breakdown, total_cost = extract_trace_cost_breakdown(trace)
            total_time_seconds = trace.info.execution_duration / 1000
    except Exception as e:
        print(f"[quiz {quiz.pk}] trace fetch failed: {e}")
    return trace_id, node_breakdown, total_cost, total_time_seconds


def _finalize_quiz_generation(quiz, final_state, trace_id, node_breakdown, total_cost, total_time_seconds, attempt_id):
    """
    Shared tail logic used by every entry point (fresh creation, retry,
    resume) once final_state is in hand - writes the metrics tables,
    branches on end_reason, persists questions if approved.
    """
    end_reason = final_state.get("end_reason")

    QuizAggregateMetrics.objects.update_or_create(
        quiz=quiz,
        defaults=dict(
            end_reason=end_reason or "",
            structural_attempts=final_state.get("structural_attempts", 0),
            evaluator_attempts=final_state.get("evaluator_attempts", 0),
            correction_occurred=bool(final_state.get("correction_occurred", 0)),
            guardrail_category=final_state.get("guardrail_category", ""),
            safety_category=final_state.get("safety_category", ""),
            total_time_seconds=total_time_seconds,
            total_cost=total_cost,
        ),
    )

    QuizGenerationLog.objects.update_or_create(
        quiz=quiz,
        defaults=dict(
            structural_feedback=final_state.get("retry_feedback", "") or "",
            evaluation_feedback=[
                fi.model_dump() if hasattr(fi, "model_dump") else fi
                for fi in final_state.get("evaluation_feedback_items", [])
            ],
            guardrail_reason=final_state.get("guardrail_reason", "") or "",
            safety_reason=final_state.get("safety_reason", "") or "",
        ),
    )

    QuizNodeCost.objects.bulk_create([
        QuizNodeCost(
            quiz=quiz,
            attempt_id=attempt_id,
            agent=item["agent"],
            model=item["model"] or "",
            cost=item["cost"],
            input_cost=item["input_cost"],
            output_cost=item["output_cost"],
            prompt_tokens=item["prompt_tokens"],
            completion_tokens=item["completion_tokens"],
            duration_seconds=item["duration_seconds"],
        )
        for item in node_breakdown
    ])

    if end_reason == "approved":
        generated_quiz = final_state["generated_quiz"]

        print(f"[quiz {quiz.pk}] requested max_questions={quiz.max_questions}, "
              f"agent returned {len(generated_quiz.quiz_items)} item(s)")

        QUESTION_TYPE_MAP = {
            "single choice question": "SQ",
            "multiple choice question": "MCQ",
        }
        LETTER_TO_INDEX = {"A": 0, "B": 1, "C": 2, "D": 3}

        try:
            quiz.questions.all().delete()

            for item in generated_quiz.quiz_items:
                correct_index = LETTER_TO_INDEX[item.answer]

                question = Question.objects.create(
                    quiz=quiz,
                    question_text=item.question,
                    question_type=QUESTION_TYPE_MAP.get(item.question_type, "SQ"),
                    topic=quiz.quiz_topic,
                    explanation=item.explanation,
                    creator=quiz.creator,
                    hint=item.hint,
                    source_citation=item.source_citation,
                )
                for i, option_text in enumerate(item.options):
                    Answer.objects.create(
                        question=question,
                        answer_text=option_text,
                        is_correct=(i == correct_index),
                        is_option=True,
                    )

            quiz.status = "READY"
            quiz.save(update_fields=["status"])

        except Exception as e:
            quiz.status = "FAILED_API_ERROR"
            quiz.error_message = f"Quiz was generated but couldn't be saved: {e}"
            quiz.save(update_fields=["status", "error_message"])

    elif end_reason == "guardrail_blocked":
        category = final_state.get("guardrail_category")
        quiz.status = "FAILED_BLOCKED"
        quiz.error_message = GUARDRAIL_USER_MESSAGES.get(
            category, final_state.get("guardrail_reason", "")
        )
        quiz.save(update_fields=["status", "error_message"])

    elif end_reason == "safety check failed":
        category = final_state.get("safety_category")
        quiz.status = "FAILED_BLOCKED"
        quiz.error_message = SAFETY_USER_MESSAGES.get(
            category, final_state.get("safety_reason", "")
        )
        quiz.save(update_fields=["status", "error_message"])

    elif end_reason in ("structural checks exhausted", "evaluator attempts exhausted"):
        quiz.status = "FAILED_EXHAUSTED"
        quiz.error_message = "We weren't able to generate a satisfactory quiz after several attempts. You can try again."
        quiz.save(update_fields=["status", "error_message"])

    else:
        quiz.status = "FAILED_API_ERROR"
        quiz.error_message = f"Unexpected end state: {end_reason!r}"
        quiz.save(update_fields=["status", "error_message"])


def _record_crash(quiz, final_state, trace_id, node_breakdown, total_cost, total_time_seconds, attempt_id, crash_type):
    QuizAggregateMetrics.objects.update_or_create(
        quiz=quiz,
        defaults=dict(
            end_reason=f"crashed_{crash_type}",
            structural_attempts=final_state.get("structural_attempts", 0),
            evaluator_attempts=final_state.get("evaluator_attempts", 0),
            correction_occurred=bool(final_state.get("correction_occurred", 0)),
            guardrail_category=final_state.get("guardrail_category", ""),
            safety_category=final_state.get("safety_category", ""),
            total_time_seconds=total_time_seconds,
            total_cost=total_cost,
        ),
    )
    QuizGenerationLog.objects.update_or_create(
        quiz=quiz,
        defaults=dict(
            structural_feedback=final_state.get("retry_feedback", "") or "",
            evaluation_feedback=[],
            guardrail_reason=final_state.get("guardrail_reason", "") or "",
            safety_reason=final_state.get("safety_reason", "") or "",
        ),
    )
    QuizNodeCost.objects.bulk_create([
        QuizNodeCost(
            quiz=quiz,
            attempt_id=attempt_id,
            agent=item["agent"],
            model=item["model"] or "",
            cost=item["cost"] if isinstance(item["cost"], (int, float)) else 0.0,
            input_cost=item.get("input_cost", 0.0),
            output_cost=item.get("output_cost", 0.0),
            prompt_tokens=item["prompt_tokens"],
            completion_tokens=item["completion_tokens"],
            duration_seconds=item.get("duration_seconds"),
        )
        for item in node_breakdown
    ])


def _run_quiz_generation(quiz, source_text):
    final_state = {}
    trace_id = None
    node_breakdown = []
    total_cost = 0.0
    total_time_seconds = None
    attempt_id = f"{quiz.pk}-{int(time.time())}"
    crashed = False
    crash_type = None

    try:
        quiz_details = QuizDetails(
            quiz_topic=quiz.quiz_topic,
            exam_name=quiz.exam_name,
            difficulty=quiz.difficulty,
            description=quiz.description,
            tips_for_quiz_creation=quiz.tips_for_quiz_creation,
            max_questions=quiz.max_questions,
        )
        initial_state = {"quiz_details": quiz_details, "source_text": source_text}
        config = {"configurable": {"thread_id": attempt_id}}

        final_state = get_graph().invoke(initial_state, config)

    except SoftTimeLimitExceeded:
        crashed = True
        crash_type = "timeout"
    except Exception as e:
        crashed = True
        crash_type = "exception"
        crash_exception = e
    finally:
        # Pre LLM Cost fix if the generation fails
        trace_id, node_breakdown, total_cost, total_time_seconds = _fetch_trace_data(quiz)

        if trace_id:
            QuizTrace.objects.get_or_create(
                quiz=quiz, mlflow_trace_id=trace_id,
                defaults={"attempt_id": attempt_id, "crashed": crashed},
            )

    if crashed:
        _record_crash(quiz, final_state, trace_id, node_breakdown, total_cost, total_time_seconds, attempt_id, crash_type)
        quiz.status = "FAILED_API_ERROR"
        quiz.error_message = (
            "Generation took too long and was stopped. Try a shorter document or fewer questions."
            if crash_type == "timeout" else str(crash_exception)
        )
        quiz.save(update_fields=["status", "error_message"])
        raise crash_exception if crash_type == "exception" else SoftTimeLimitExceeded()

    _finalize_quiz_generation(quiz, final_state, trace_id, node_breakdown, total_cost, total_time_seconds, attempt_id)


@shared_task
def generate_quiz_task(quiz_id, file_key):
    """
    Fresh quiz creation - downloads the PDF from bucket storage in
    production (Django and this Celery worker run in separate containers
    with no shared filesystem). In local dev, both processes run on the
    same machine, so file_key is just a plain local path already on disk.
    """
    print("Generating Quiz....")
    try:
        quiz = Quiz.objects.get(pk=quiz_id)
    except Quiz.DoesNotExist:
        return

    quiz.status = "PROCESSING"
    quiz.save(update_fields=["status"])

    using_bucket = bool(os.getenv("AWS_ENDPOINT_URL"))
    local_path = None
    s3_client = None
    bucket_name = None

    try:
        if using_bucket:
            s3_client = boto3.client("s3", endpoint_url=os.getenv("AWS_ENDPOINT_URL"))
            bucket_name = os.getenv("AWS_S3_BUCKET_NAME")
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                s3_client.download_fileobj(bucket_name, file_key, tmp)
                local_path = tmp.name
        else:
            local_path = file_key  # already a real local path in dev

        source_text = extract_text_from_pdf(local_path)
        SourceText.objects.create(quiz=quiz, source_text=source_text)
        try:
            save_chunks_for_source_text(
                source_text=SourceText.objects.get(quiz=quiz),
                user=quiz.creator,
                topic_name=quiz.quiz_topic,
            )
        except Exception as e:
            print(f"[quiz {quiz_id}] chunking/embedding failed, continuing anyway: {e}")

    except Exception as e:
        quiz.status = "FAILED_API_ERROR"
        quiz.error_message = f"Couldn't read the uploaded document: {e}"
        quiz.save(update_fields=["status", "error_message"])
        return
    finally:
        if using_bucket:
            if local_path and os.path.exists(local_path):
                os.remove(local_path)
            try:
                s3_client.delete_object(Bucket=bucket_name, Key=file_key)
            except Exception as e:
                print(f"[quiz {quiz_id}] couldn't delete bucket object {file_key}: {e}")
        else:
            if local_path and os.path.exists(local_path):
                os.remove(local_path)

    # Only reached if the try block above completed with no exception
    _run_quiz_generation(quiz, source_text)

@shared_task
def retry_quiz_task(quiz_id):
    """
    FAILED_EXHAUSTED retry - reuses the stored SourceText, no re-upload
    or re-extraction needed. Fresh graph run, new thread_id.
    """
    try:
        quiz = Quiz.objects.get(pk=quiz_id)
    except Quiz.DoesNotExist:
        return

    try:
        source_text = quiz.source_text_record.source_text
    except SourceText.DoesNotExist:
        quiz.status = "FAILED_API_ERROR"
        quiz.error_message = "The original source document is no longer available for retry. Please create a new quiz."
        quiz.save(update_fields=["status", "error_message"])
        return

    quiz.status = "PROCESSING"
    quiz.save(update_fields=["status"])

    _run_quiz_generation(quiz, source_text)


@shared_task
def resume_quiz_task(quiz_id):
    try:
        quiz = Quiz.objects.get(pk=quiz_id)
    except Quiz.DoesNotExist:
        return

    last_trace = quiz.traces.order_by("-created_at").first()
    if not last_trace:
        quiz.status = "FAILED_API_ERROR"
        quiz.error_message = "Nothing to resume - please create a new quiz."
        quiz.save(update_fields=["status", "error_message"])
        return

    thread_id = last_trace.attempt_id
    config = {"configurable": {"thread_id": thread_id}}

    try:
        state_snapshot = get_graph().get_state(config)
    except Exception:
        state_snapshot = None

    if not state_snapshot or not state_snapshot.values:
        quiz.status = "FAILED_API_ERROR"
        quiz.error_message = "Nothing to resume - please create a new quiz."
        quiz.save(update_fields=["status", "error_message"])
        return

    quiz.status = "PROCESSING"
    quiz.save(update_fields=["status"])

    final_state = {}
    trace_id = None
    node_breakdown = []
    total_cost = 0.0
    total_time_seconds = None
    crashed = False
    crash_type = None

    try:
        final_state = get_graph().invoke(None, config)
    except SoftTimeLimitExceeded:
        crashed = True
        crash_type = "timeout"
    except Exception as e:
        crashed = True
        crash_type = "exception"
        crash_exception = e
    finally:
        trace_id, node_breakdown, total_cost, total_time_seconds = _fetch_trace_data(quiz)
        if trace_id:
            QuizTrace.objects.get_or_create(
                quiz=quiz, mlflow_trace_id=trace_id,
                defaults={"attempt_id": thread_id, "crashed": crashed},
            )

    if crashed:
        _record_crash(quiz, final_state, trace_id, node_breakdown, total_cost, total_time_seconds, thread_id, crash_type)
        quiz.status = "FAILED_API_ERROR"
        quiz.error_message = (
            "Resuming took too long and was stopped."
            if crash_type == "timeout" else str(crash_exception)
        )
        quiz.save(update_fields=["status", "error_message"])
        raise crash_exception if crash_type == "exception" else SoftTimeLimitExceeded()

    _finalize_quiz_generation(quiz, final_state, trace_id, node_breakdown, total_cost, total_time_seconds, thread_id)

@shared_task
def cleanup_stuck_quizzes():
    cutoff = timezone.now() - timedelta(minutes=20)
    stuck_quizzes = Quiz.objects.filter(status="PROCESSING", updated_at__lt=cutoff)

    for quiz in stuck_quizzes:
        quiz.status = "FAILED_API_ERROR"
        quiz.error_message = "Something went wrong during generation. Please try again."
        quiz.save(update_fields=["status", "error_message"])
        print(f"[cleanup] marked quiz {quiz.pk} as failed - stuck in PROCESSING since {quiz.updated_at}")


@shared_task
def poll_pib_feed_task():
    count = poll_pib_feed()
    print(f"[PIB poll] saved {count} new articles")
    return count


# For the Digest Quiz Generation on Click
@shared_task
def generate_quiz_from_text_task(quiz_id, source_text):
    print("Generating Quiz from digest text....")
    try:
        quiz = Quiz.objects.get(pk=quiz_id)
    except Quiz.DoesNotExist:
        return

    quiz.status = "PROCESSING"
    quiz.save(update_fields=["status"])

    try:
        SourceText.objects.create(quiz=quiz, source_text=source_text)
    except Exception as e:
        quiz.status = "FAILED_API_ERROR"
        quiz.error_message = f"Couldn't save the digest source text: {e}"
        quiz.save(update_fields=["status", "error_message"])
        return

    _run_quiz_generation(quiz, source_text)
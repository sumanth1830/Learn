from ..llms import get_topics_preview_llm
from ..prompts import topics_preview_prompt
from ..schema import TopicsPreviewBriefResult
from quizmaker.models import QuizAttemptAnswer
from quizmaker.rag_retrieval import retrieve_similar_chunks


def _extract_usage(response):
    meta = response.response_metadata.get("token_usage", {})
    return {
        "prompt_tokens": meta.get("prompt_tokens", 0),
        "completion_tokens": meta.get("completion_tokens", 0),
        "cost": meta.get("cost", 0),
    }


def topics_preview_agent(user):
    uncovered_answers = QuizAttemptAnswer.objects.filter(
        quiz_history__user=user,
        is_correct=False,
    ).exclude(
        covered_in_briefs__isnull=False,
    ).select_related("question").order_by("created_at")[:15]

    questions_with_context = ""
    chunk_lookup = {}
    for answer in uncovered_answers:
        question = answer.question
        correct_answer = question.answers.filter(is_correct=True).first()
        chunks = retrieve_similar_chunks(
            f"{question.question_text} {question.source_citation}", user
        )
        questions_with_context += f"\nQuestion {answer.pk}: {question.question_text}\n"
        questions_with_context += f"Correct answer: {correct_answer.answer_text}\n"
        questions_with_context += f"Citation: {question.source_citation}\n"
        questions_with_context += "Retrieved context:\n"
        for chunk in chunks:
            questions_with_context += f"  [Chunk {chunk.pk}] {chunk.header}: {chunk.content}\n"
            chunk_lookup[chunk.pk] = chunk.header

    prompt = topics_preview_prompt.invoke({"questions_with_context": questions_with_context})
    llm_with_structure = get_topics_preview_llm().with_structured_output(TopicsPreviewBriefResult, include_raw=True)
    result = llm_with_structure.invoke(prompt)

    return result["parsed"], uncovered_answers,  _extract_usage(result["raw"]), chunk_lookup
from .models.rag import TopicsPreviewBrief, TopicsPreviewCost
from django.contrib.auth.models import User
from agentic_app.agents.topics_preview_nodes import topics_preview_agent
import time
from celery import shared_task


@shared_task
def generate_topics_preview_task(user_id):
    user = User.objects.get(pk=user_id)

    start_time = time.time()
    parsed_result, uncovered_answers, usage, chunk_lookup = topics_preview_agent(user)
    elapsed_seconds = time.time() - start_time

    content = []
    for exp in parsed_result.explanations:
        content.append({
            "question_id": exp.question_id,
            "question_text": exp.question_text,
            "explanation": exp.explanation,
            "chunk_references": [
                {"chunk_id": cid, "header": chunk_lookup.get(cid, "")}
                for cid in exp.chunk_ids
            ],
        })

    brief = TopicsPreviewBrief.objects.create(
        user=user,
        content=content,
        skipped_questions=[
            {"question_id": s.question_id, "reason": s.reason}
            for s in parsed_result.questions_skipped
        ],
    )
    brief.wrong_answers_covered.set(uncovered_answers)

    TopicsPreviewCost.objects.create(
        brief=brief,
        prompt_tokens=usage["prompt_tokens"],
        completion_tokens=usage["completion_tokens"],
        cost=usage["cost"],
        total_time_seconds=elapsed_seconds,
    )

    print(f"[topics preview {user.username}] generated, cost=${usage['cost']:.4f}, "
          f"time={elapsed_seconds:.1f}s, covered={len(parsed_result.explanations)}, "
          f"skipped={len(parsed_result.questions_skipped)}")

    return brief.pk
import re
from datetime import timedelta

import markdown
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db.models import Count, Q

from quizmaker.models import QuizHistory, QuizAttemptAnswer, TopicsPreviewBrief, SourceChunk
from quizmaker.models.engagement import compute_current_streak


@login_required
def profile_view(request):
    user = request.user

    streak = compute_current_streak(user)

    now = timezone.now()
    tomorrow_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    seconds_until_reset = int((tomorrow_midnight - now).total_seconds())

    uncovered_count = QuizAttemptAnswer.objects.filter(
        quiz_history__user=user, is_correct=False
    ).exclude(covered_in_briefs__isnull=False).count()

    latest_brief = TopicsPreviewBrief.objects.filter(user=user).order_by("-created_at").first()

    backstop_eligible = (
            latest_brief
            and (timezone.now() - latest_brief.created_at) >= timedelta(weeks=2)
            and uncovered_count >= 5
    )

    can_generate_brief = uncovered_count >= 15 or backstop_eligible

    total_quizzes = QuizHistory.objects.filter(user=user).count()
    topic_stats = (
        QuizAttemptAnswer.objects.filter(quiz_history__user=user)
        .values("question__topic")
        .annotate(
            total=Count("id"),
            correct=Count("id", filter=Q(is_correct=True)),
        )
    )

    topic_accuracy = []
    for row in topic_stats:
        topic = row["question__topic"]
        if not topic:
            continue
        accuracy = round((row["correct"] / row["total"] * 100), 1) if row["total"] else 0
        topic_accuracy.append({"topic": topic, "accuracy": accuracy, "total": row["total"]})

    topic_accuracy.sort(key=lambda t: t["accuracy"], reverse=True)
    # Strong topic shown as weak topic fix
    top_topics = topic_accuracy[:3]
    remaining = topic_accuracy[3:]
    weak_topics = remaining[-3:][::-1] if remaining else []

    attempts = QuizHistory.objects.filter(user=user)
    total_correct = sum(a.num_correct for a in attempts)
    total_attempted = sum(a.total_attempted for a in attempts)
    overall_accuracy = round((total_correct / total_attempted * 100) if total_attempted else 0, 1)

    return render(request, "quizmaker/profile.html", {
        "streak": streak,
        "seconds_until_reset": seconds_until_reset,
        "total_quizzes": total_quizzes,
        "overall_accuracy": overall_accuracy,
        "top_topics": top_topics,
        "weak_topics": weak_topics,
        "can_generate_brief": can_generate_brief,
        "latest_brief": latest_brief,
        "uncovered_count": uncovered_count,
    })


@login_required
def generate_topics_preview_view(request):
    from ..topics_preview_tasks import generate_topics_preview_task
    generate_topics_preview_task.delay(request.user.pk)
    messages.success(request, "Your brief is being generated — check back in a moment.")
    return redirect("quiz:profile")


@login_required
def topics_preview_list_view(request):
    briefs = TopicsPreviewBrief.objects.filter(user=request.user).order_by("-created_at")
    for brief in briefs:
        if brief.content:
            first_explanation = brief.content[0].get("explanation", "")
            brief.plain_excerpt = re.sub(r"\[Chunk\s*\d+\]", "", first_explanation)
        else:
            brief.plain_excerpt = ""
    return render(request, "quizmaker/topics_preview_list.html", {"briefs": briefs})


def clean_header(header):
    parts = [p.strip() for p in header.split("/")]
    return parts[-1]


@login_required
def topics_preview_detail_view(request, pk):
    brief = get_object_or_404(TopicsPreviewBrief, pk=pk, user=request.user)

    enriched_explanations = []
    for entry in brief.content:
        headers = [
            clean_header(ref["header"]).replace("*", "").strip()
            for ref in entry["chunk_references"] if ref["header"]
        ]
        # topic_references = " / ".join(headers)
        print(headers)
        enriched_explanations.append({
            "question_text": entry["question_text"],
            "explanation": re.sub(r"\[Chunk\s*\d+\]", "", entry["explanation"]),
            "topic_references_list": headers,
        })

    all_briefs = list(TopicsPreviewBrief.objects.filter(user=request.user).order_by("created_at"))
    index = all_briefs.index(brief)
    prev_brief = all_briefs[index - 1] if index > 0 else None
    next_brief = all_briefs[index + 1] if index < len(all_briefs) - 1 else None

    return render(request, "quizmaker/topics_preview_detail.html", {
        "brief": brief,
        "explanations": enriched_explanations,
        "prev_brief": prev_brief,
        "next_brief": next_brief,
    })


@login_required
def rate_topics_preview_view(request, pk):
    brief = get_object_or_404(TopicsPreviewBrief, pk=pk, user=request.user)
    rating = request.POST.get("rating")
    if rating in ("up", "down"):
        brief.rating = rating
        brief.save(update_fields=["rating"])
    return redirect("quiz:topics_preview_detail", pk=pk)
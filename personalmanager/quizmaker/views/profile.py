from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone
from django.db.models import Count, Q

from quizmaker.models import QuizHistory, QuizAttemptAnswer
from quizmaker.models.engagement import compute_current_streak


@login_required
def profile_view(request):
    user = request.user

    streak = compute_current_streak(user)

    now = timezone.now()
    tomorrow_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    seconds_until_reset = int((tomorrow_midnight - now).total_seconds())

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
    top_topics = topic_accuracy[:3]
    weak_topics = topic_accuracy[-3:][::-1] if len(topic_accuracy) > 3 else []

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
    })
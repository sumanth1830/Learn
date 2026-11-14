"""JSON API for the Unity game.

The Unity Web build is served from the same origin, so these views use the
normal Django session and CSRF cookie. Each chapter is one quiz (a boss
battle) plus the flashcards made from it (that chapter's village area).

Spaced repetition: a card is due 2**correct_streak days after it was last
reviewed (or created, if never reviewed). "sim_days" pushes the clock
forward so the demo can show the village decaying without waiting.
"""
import json
import re
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from ..models import FlashCard, Quiz, QuizAttemptAnswer, QuizHistory, UserActivity

MAX_SIM_DAYS = 60
CHAPTER_RE = re.compile(r"\bch(?:apter)?\.?\s*(\d+)", re.IGNORECASE)


def _sim_days(value):
    try:
        days = int(value or 0)
    except (TypeError, ValueError):
        days = 0
    return max(0, min(days, MAX_SIM_DAYS))


def _now(sim_days):
    return timezone.now() + timedelta(days=sim_days)


def _due_at(card):
    base = card.last_reviewed_at or card.created_at
    return base + timedelta(days=2 ** min(card.correct_streak, 10))


def _chapter_key(topic):
    match = CHAPTER_RE.search(topic or "")
    return f"ch{match.group(1)}" if match else ""


def _body(request):
    try:
        return json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return None


@login_required
@ensure_csrf_cookie
def game_view(request):
    """The page that hosts the Unity build. ensure_csrf_cookie makes sure the
    csrftoken cookie exists so the game can send it back on POSTs."""
    return render(request, "quizmaker/game.html")


@login_required
@require_GET
def game_state_view(request):
    """Every chapter the player has: its quiz (boss) and how neglected its
    flashcards (village area) are at the simulated date."""
    sim_days = _sim_days(request.GET.get("sim_days"))
    now = _now(sim_days)

    cards_by_topic = {}
    for card in FlashCard.objects.filter(creator=request.user):
        cards_by_topic.setdefault(card.topic, []).append(card)

    chapters = []
    quizzes = (Quiz.objects.filter(creator=request.user, status="READY")
               .order_by("quiz_topic", "-created_at"))
    seen_topics = set()
    for quiz in quizzes:
        if quiz.quiz_topic in seen_topics:
            continue  # newest quiz per topic only
        cards = cards_by_topic.get(quiz.quiz_topic)
        if not cards:
            continue  # a chapter needs flashcards for its village area
        seen_topics.add(quiz.quiz_topic)
        overdue = sum(1 for c in cards if _due_at(c) <= now)
        best = (QuizHistory.objects.filter(quiz=quiz, user=request.user)
                .order_by("-num_correct").values_list("num_correct", flat=True).first())
        chapters.append({
            "key": _chapter_key(quiz.quiz_topic),
            "topic": quiz.quiz_topic,
            "quiz_id": quiz.pk,
            "quiz_name": quiz.quiz_name,
            "num_questions": quiz.questions.count(),
            "best_score": best if best is not None else -1,
            "num_cards": len(cards),
            "num_overdue": overdue,
            "overdue_fraction": round(overdue / len(cards), 3),
        })

    chapters.sort(key=lambda c: (len(c["key"]), c["key"]))
    return JsonResponse({"sim_days": sim_days, "chapters": chapters})


@login_required
@require_GET
def game_quiz_view(request, pk):
    """A quiz's questions for one boss battle. The correct option is sent
    so the game can react instantly; the score is recomputed on submit."""
    quiz = get_object_or_404(Quiz, pk=pk, creator=request.user, status="READY")
    questions = []
    for q in quiz.questions.prefetch_related("answers").order_by("pk"):
        options = sorted((a for a in q.answers.all() if a.is_option), key=lambda a: a.pk)
        questions.append({
            "id": q.pk,
            "text": q.question_text,
            "hint": q.hint,
            "explanation": q.explanation,
            "options": [{"id": a.pk, "text": a.answer_text} for a in options],
            "correct_id": next((a.pk for a in options if a.is_correct), 0),
        })
    return JsonResponse({
        "quiz_id": quiz.pk,
        "name": quiz.quiz_name,
        "topic": quiz.quiz_topic,
        "key": _chapter_key(quiz.quiz_topic),
        "questions": questions,
    })


@login_required
@require_POST
def game_quiz_submit_view(request, pk):
    """Body: {"answers": [{"question_id": 1, "answer_id": 7}, ...]}.
    Saves a normal QuizHistory + QuizAttemptAnswer rows, so a battle shows
    up in the site's quiz history like any other attempt."""
    quiz = get_object_or_404(Quiz, pk=pk, creator=request.user, status="READY")
    body = _body(request)
    if body is None or not isinstance(body.get("answers"), list):
        return JsonResponse({"error": "Expected JSON with an 'answers' list."}, status=400)

    picked = {}
    for item in body["answers"]:
        if isinstance(item, dict):
            picked[item.get("question_id")] = item.get("answer_id")

    questions = list(quiz.questions.prefetch_related("answers"))
    with transaction.atomic():
        history = QuizHistory.objects.create(
            quiz=quiz, user=request.user, total_attempted=len(questions))
        num_correct = 0
        for q in questions:
            answer = next((a for a in q.answers.all() if a.pk == picked.get(q.pk)), None)
            is_correct = bool(answer and answer.is_correct)
            num_correct += is_correct
            QuizAttemptAnswer.objects.create(
                quiz_history=history, question=q,
                selected_answer=answer, is_correct=is_correct)
        history.num_correct = num_correct
        history.num_wrong = len(questions) - num_correct
        history.save(update_fields=["num_correct", "num_wrong"])

    UserActivity.objects.get_or_create(user=request.user, activity_date=timezone.now().date())
    return JsonResponse({"history_id": history.pk, "num_correct": num_correct,
                         "total": len(questions)})


@login_required
@require_GET
def game_flashcards_view(request):
    """Cards for one chapter topic, overdue ones first."""
    topic = request.GET.get("topic", "")
    now = _now(_sim_days(request.GET.get("sim_days")))
    cards = []
    for card in FlashCard.objects.filter(creator=request.user, topic=topic):
        due = _due_at(card)
        cards.append({
            "id": card.pk,
            "front": card.front_text,
            "hint": card.hint,
            "back": card.explanation,
            "streak": card.correct_streak,
            "overdue": due <= now,
            "_due": due,
        })
    cards.sort(key=lambda c: c["_due"])
    for c in cards:
        del c["_due"]
    return JsonResponse({"topic": topic, "cards": cards})


@login_required
@require_POST
def game_flashcard_review_view(request, pk):
    """Body: {"mastered": true, "sim_days": 0}. Same streak rule as the
    site's study mode. The review is stamped at the simulated date so a
    reviewed card stops counting as overdue in the simulation."""
    card = get_object_or_404(FlashCard, pk=pk, creator=request.user)
    body = _body(request)
    if body is None:
        return JsonResponse({"error": "Expected JSON."}, status=400)

    card.last_reviewed_at = _now(_sim_days(body.get("sim_days")))
    card.correct_streak = card.correct_streak + 1 if body.get("mastered") else 0
    card.save(update_fields=["last_reviewed_at", "correct_streak"])
    UserActivity.objects.get_or_create(user=request.user, activity_date=timezone.now().date())
    return JsonResponse({"id": card.pk, "streak": card.correct_streak})


@login_required
@require_POST
def game_reset_view(request):
    """Demo control: make every card fresh again (reviewed 'now')."""
    updated = FlashCard.objects.filter(creator=request.user).update(
        last_reviewed_at=timezone.now(), correct_streak=0)
    return JsonResponse({"reset": updated})
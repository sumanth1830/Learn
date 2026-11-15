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
from django.db.models import Count, Max

from ..models import (FlashCard, GameProfile, Quiz, QuizAttemptAnswer, QuizHistory,
                      UserActivity, VillageArea)

MAX_SIM_DAYS = 60
CHAPTER_RE = re.compile(r"\bch(?:apter)?\.?\s*(\d+)", re.IGNORECASE)
# Game economy (the Unity battle uses the same numbers for its animation;
# the server's result is the one that counts).
COINS_PER_RIGHT = 10
PERFECT_BONUS = 30
MAX_BATTLE_LOSS = 0.30     # an all-wrong battle costs this much area health at strength 1
BLOCKED_HIT = 0.01         # area health lost per right answer at strength 1
MAX_NEGLECT_DRAIN = 0.70   # area health hidden when every card in the chapter is overdue
REPAIR_COST = 10           # coins per repair
REPAIR_AMOUNT = 0.05       # area health restored per repair
DEMO_START_COINS = 100     # wallet after the demo reset


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

def _overdue_fraction(user, topic, now):
    cards = list(FlashCard.objects.filter(creator=user, topic=topic))
    if not cards:
        return 0.0
    return sum(1 for c in cards if _due_at(c) <= now) / len(cards)


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
    """Everything the village screen needs: coins, and per chapter its area's
    health (battle damage minus neglect at the simulated date), its quizzes
    with best scores, and the current boss quiz (newest not yet perfected)."""
    sim_days = _sim_days(request.GET.get("sim_days"))
    now = _now(sim_days)

    cards_by_topic = {}
    for card in FlashCard.objects.filter(creator=request.user):
        cards_by_topic.setdefault(card.topic, []).append(card)

    # Best score per quiz in one grouped query: {quiz_id: best}.
    best_by_quiz = dict(QuizHistory.objects.filter(user=request.user)
                        .values_list("quiz_id").annotate(best=Max("num_correct")))
    base_by_key = dict(VillageArea.objects.filter(user=request.user)
                       .values_list("chapter_key", "base_health"))

    quizzes_by_topic = {}
    for quiz in (Quiz.objects.filter(creator=request.user, status="READY")
                 .annotate(n=Count("questions")).order_by("-created_at")):
        quizzes_by_topic.setdefault(quiz.quiz_topic, []).append(quiz)

    chapters = []
    for topic, quizzes in quizzes_by_topic.items():
        cards = cards_by_topic.get(topic)
        if not cards:
            continue  # a chapter needs flashcards for its village area
        key = _chapter_key(topic)
        overdue = sum(1 for c in cards if _due_at(c) <= now)
        fraction = overdue / len(cards)

        quiz_list = []
        for q in quizzes:
            best = best_by_quiz.get(q.pk, -1)
            quiz_list.append({
                "quiz_id": q.pk,
                "name": q.quiz_name,
                "num_questions": q.n,
                "best_score": best,
                "perfect": q.n > 0 and best >= q.n,
            })
        current = next((q for q in quiz_list if not q["perfect"]), quiz_list[0])

        base = base_by_key.get(key, 1.0) if key else 1.0
        chapters.append({
            "key": key,
            "topic": topic,
            "quiz_id": current["quiz_id"],
            "quiz_name": current["name"],
            "num_questions": current["num_questions"],
            "best_score": current["best_score"],
            "num_cards": len(cards),
            "num_overdue": overdue,
            "overdue_fraction": round(fraction, 3),
            "area_base_health": round(base, 3),
            "area_health": round(max(0.0, base - MAX_NEGLECT_DRAIN * fraction), 3),
            "quizzes": quiz_list,
        })

    chapters.sort(key=lambda c: (len(c["key"]), c["key"]))
    coins = (GameProfile.objects.filter(user=request.user)
             .values_list("coins", flat=True).first() or 0)
    village = (sum(c["area_health"] for c in chapters) / len(chapters)) if chapters else 1.0
    return JsonResponse({
        "sim_days": sim_days,
        "coins": coins,
        "village_health": round(village, 3),
        "chapters": chapters,
    })


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
    """Body: {"answers": [{"question_id": 1, "answer_id": 7}, ...], "sim_days": 0}.

    Saves a normal QuizHistory + QuizAttemptAnswer rows, then settles the
    game economy on the server: coins for improvement on this quiz, and the
    boss's damage to the chapter's village area (scaled by neglect)."""
    quiz = get_object_or_404(Quiz, pk=pk, creator=request.user, status="READY")
    body = _body(request)
    if body is None or not isinstance(body.get("answers"), list):
        return JsonResponse({"error": "Expected JSON with an 'answers' list."}, status=400)

    picked = {}
    for item in body["answers"]:
        if isinstance(item, dict):
            picked[item.get("question_id")] = item.get("answer_id")

    questions = list(quiz.questions.prefetch_related("answers"))
    total = len(questions)
    key = _chapter_key(quiz.quiz_topic)
    now = _now(_sim_days(body.get("sim_days")))
    strength = 1.0 + _overdue_fraction(request.user, quiz.quiz_topic, now)
    per_wrong = MAX_BATTLE_LOSS / max(1, total)

    with transaction.atomic():
        history = QuizHistory.objects.create(quiz=quiz, user=request.user, total_attempted=total)
        profile, _ = GameProfile.objects.select_for_update().get_or_create(user=request.user)
        prev_best = (QuizHistory.objects.filter(quiz=quiz, user=request.user)
                     .aggregate(best=Max("num_correct"))["best"] or 0)
        num_correct = 0
        area_loss = 0.0
        for q in questions:
            answer = next((a for a in q.answers.all() if a.pk == picked.get(q.pk)), None)
            is_correct = bool(answer and answer.is_correct)
            num_correct += is_correct
            area_loss += (BLOCKED_HIT if is_correct else per_wrong) * strength
            QuizAttemptAnswer.objects.create(
                quiz_history=history, question=q,
                selected_answer=answer, is_correct=is_correct)
        history.num_correct = num_correct
        history.num_wrong = total - num_correct
        history.save(update_fields=["num_correct", "num_wrong"])

        # Coins only for beating your previous best on this quiz (no farming).
        coins_earned = max(0, num_correct - prev_best) * COINS_PER_RIGHT
        if num_correct == total and prev_best < total:
            coins_earned += PERFECT_BONUS

        profile.coins += coins_earned
        profile.save(update_fields=["coins", "updated_at"])

        area_health = None
        if key:
            area, _ = VillageArea.objects.select_for_update().get_or_create(
                user=request.user, chapter_key=key)
            area.base_health = max(0.0, area.base_health - area_loss)
            area.save(update_fields=["base_health", "updated_at"])
            area_health = round(area.base_health, 3)

    UserActivity.objects.get_or_create(user=request.user, activity_date=timezone.now().date())
    return JsonResponse({
        "history_id": history.pk,
        "num_correct": num_correct,
        "total": total,
        "coins_earned": coins_earned,
        "coins_total": profile.coins,
        "area_key": key,
        "area_loss": round(area_loss, 3),
        "area_base_health": area_health,
    })


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
def game_area_repair_view(request, key):
    """Spend REPAIR_COST coins to restore REPAIR_AMOUNT of an area's battle
    damage. Neglect is not repaired here: reviewing the cards cures that."""
    if not re.fullmatch(r"ch\d+", key):
        return JsonResponse({"error": "Unknown area."}, status=400)

    with transaction.atomic():
        profile, _ = GameProfile.objects.select_for_update().get_or_create(user=request.user)
        area, _ = VillageArea.objects.select_for_update().get_or_create(
            user=request.user, chapter_key=key)
        if area.base_health >= 1.0:
            return JsonResponse({"error": "This area is already fully repaired."}, status=400)
        if profile.coins < REPAIR_COST:
            return JsonResponse({"error": f"Repairs cost {REPAIR_COST} coins."}, status=400)
        profile.coins -= REPAIR_COST
        profile.save(update_fields=["coins", "updated_at"])
        area.base_health = min(1.0, area.base_health + REPAIR_AMOUNT)
        area.save(update_fields=["base_health", "updated_at"])

    return JsonResponse({
        "coins_total": profile.coins,
        "area_key": key,
        "area_base_health": round(area.base_health, 3),
    })


@login_required
@require_POST
def game_reset_view(request):
    """Demo control: fresh cards, a fully repaired village and starter coins.
    Quiz history is kept."""
    with transaction.atomic():
        updated = FlashCard.objects.filter(creator=request.user).update(
            last_reviewed_at=timezone.now(), correct_streak=0)
        VillageArea.objects.filter(user=request.user).update(base_health=1.0)
        GameProfile.objects.update_or_create(
            user=request.user, defaults={"coins": DEMO_START_COINS})
    return JsonResponse({"reset": updated, "coins_total": DEMO_START_COINS})
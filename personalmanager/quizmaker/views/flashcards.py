from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import ListView
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from ..forms import FlashCardForm
from ..models import FlashCard, QuizHistory, UserActivity


class FlashCardCreate(LoginRequiredMixin, CreateView):
    model = FlashCard
    template_name = "quizmaker/flashcard_form.html"
    form_class = FlashCardForm

    def form_valid(self, form):
        # Since we are not assigning user in the form, we are manually assigning
        form.instance.creator = self.request.user
        return super().form_valid(form)


class FlashCardUpdate(LoginRequiredMixin, UpdateView):
    model = FlashCard
    fields = ["front_text", "hint", "explanation", "topic"]
    template_name = "quizmaker/flashcard_form.html"


class FlashCardDelete(LoginRequiredMixin, DeleteView):
    model = FlashCard
    template_name = "quizmaker/flashcard_confirm_delete.html"


@login_required
def flash_card_list_view(request):
    sort = request.GET.get("sort", "recent")
    cards = FlashCard.objects.filter(creator=request.user)

    if sort == "topic":
        cards = cards.order_by('topic', '-created_at')
    else:
        cards = cards.order_by('-created_at')

    topic_groups = []
    seen = {}
    for card in cards:
        if card.topic not in seen:
            seen[card.topic] = {"topic": card.topic, "count": 0, "preview": card.front_text}
            topic_groups.append(seen[card.topic])
        seen[card.topic]["count"] += 1

    return render(request, "quizmaker/flashcard_list.html", {
        "topic_groups": topic_groups,
        "sort": sort,
    })


@login_required
def flashcard_topic_detail_view(request, topic):
    cards = FlashCard.objects.filter(creator=request.user, topic=topic).order_by("-created_at")
    if not cards.exists():
        raise Http404("No flashcards found for this topic.")

    return render(request, "quizmaker/flashcard_topic_detail.html", {
        "topic": topic,
        "cards": cards,
    })


@login_required
def create_flashcards_from_quiz(request, pk):
    if request.method != "POST":
        return redirect("quiz:quiz_results", pk=pk)

    quiz_history = get_object_or_404(QuizHistory, pk=pk, user=request.user)
    scope = request.POST.get("scope", "incorrect")

    attempt_answers = quiz_history.attempt_answers.select_related("question")
    if scope == "incorrect":
        attempt_answers = attempt_answers.filter(is_correct=False)

    created = 0
    skipped_duplicates = 0
    for attempt_answer in attempt_answers:
        question = attempt_answer.question

        if FlashCard.objects.filter(creator=request.user, front_text=question.question_text).exists():
            skipped_duplicates += 1
            continue

        FlashCard.objects.create(
            front_text=question.question_text,
            hint=question.hint or "",
            explanation=question.explanation or "No explanation available for this question.",
            topic=quiz_history.quiz.quiz_topic,
            creator=request.user,
        )
        created += 1

    quiz_history.flashcards_created = True
    quiz_history.save(update_fields=["flashcards_created"])

    if created:
        msg = f"Created {created} flashcard{'s' if created != 1 else ''} under \"{quiz_history.quiz.quiz_topic}.\""
        if skipped_duplicates:
            msg += f" ({skipped_duplicates} already existed and were skipped.)"
        messages.success(request, msg)
    else:
        messages.info(request, "No new flashcards created — all of these already existed.")

    return redirect("quiz:flashcard_list")


@login_required
def flashcard_topic_delete_view(request, topic):
    cards = FlashCard.objects.all().filter(creator=request.user, topic=topic)
    count = cards.count()

    if count == 0:
        raise Http404("No Flashcards found for this topic")

    if request.method == "POST":
        cards.delete()
        messages.success(request, f"Deleted {count} flashcard{'s' if count != 1 else ''} under \"{topic}.\"")
        return redirect("quiz:flashcard_list")

    return render(request, "quizmaker/flashcard_topic_confirm_delete.html", {
        "topic": topic,
        "count": count,
    })


@login_required
def flashcard_study_view(request, topic):
    cards = FlashCard.objects.all().filter(creator=request.user, topic=topic).order_by("-created_at")
    if not cards.exists():
        raise Http404("No Flashcards found for this topic")

    return render(request, "quizmaker/flashcard_study.html", {
        'topic': topic,
        'cards': cards
    })


@login_required
def flashcard_review_submit_view(request, pk):
    flashcard = get_object_or_404(FlashCard, pk=pk, creator=request.user)
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request."}, status=405)

    rating = request.POST.get("rating")  # "learning" or "mastered"

    flashcard.last_reviewed_at = timezone.now()
    if rating == "mastered":
        flashcard.correct_streak += 1
    else:
        flashcard.correct_streak = 0
    flashcard.save(update_fields=["last_reviewed_at", "correct_streak"])

    UserActivity.objects.get_or_create(
        user=request.user, activity_date=timezone.now().date()
    )

    return JsonResponse({"success": True})
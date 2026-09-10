import pdfplumber
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, Http404, JsonResponse
import uuid


from .models import Quiz, QuizHistory, FlashCard, QuizAttemptAnswer, Question
from django.views.generic.edit import UpdateView, DeleteView, CreateView
from django.views.generic import ListView
from .forms import FlashCardForm, QuizCreationForm, SignupForm
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from .tasks import generate_quiz_task
from django.core.files.storage import default_storage
# Create your views here.

PDF_TEXT_CHAR_LIMIT = 48000
MIN_PDF_TEXT_CHARS = 300
MAX_PDF_PAGES = 15

def home(request):
    # template = loader.get_template("quizmaker/home.html")
    # return redirect("Welcome to the Quiz Maker!")
    return render(request, "quizmaker/home.html")

@login_required
def profile_view(request):
    return render(request, 'quizmaker/profile.html')


def login_view(request):
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            # send them wherever makes sense post-login — home shown here
            return redirect("quiz:home")
    else:
        form = AuthenticationForm(request)

    return render(request, "login.html", {"form": form})


# def logout_view(request):
#     logout(request)
#     return redirect("quiz:home")

class SignUp(CreateView):
    form_class = SignupForm
    # reverse lazy generates a full url from a name
    success_url = reverse_lazy("quiz:home")
    template_name = "registration/signup.html"

# class FlashCardList(LoginRequiredMixin, ListView):
#     model = FlashCard
#     template_name = "quizmaker/flashcard_list.html"
#
#     def get_queryset(self):
#         sort_by = self.request.GET.get('sort', 'recent')
#         if sort_by == "topic":
#             return FlashCard.objects.all().order_by('topic')
#         return FlashCard.objects.all().order_by('-created_at')
#
#     def get_context_data(
#         self, *, object_list = ..., **kwargs
#     ):
#         # Accessing context data
#         context = super().get_context_data(**kwargs)
#         # Capturing parameter from the url and adding the sort variable to context
#         # The HTML is updated accordingly
#         context['sort'] = self.request.GET.get('sort', 'recent')
#         return context

class FlashCardCreate(LoginRequiredMixin, CreateView):
    model = FlashCard
    # throws error - no need of fields when you specify them on forms
    # fields = ["front_text", "hint", "explanation", "topic"]
    template_name = "quizmaker/flashcard_form.html"
    form_class = FlashCardForm

    def form_valid(self, form):
        # Since we are not assigning user in the form, we are manually assigning
        # After sqlite3.IntegrityError NOT NULL constraint failed: quizmaker_flashcard.creator_id
        form.instance.creator = self.request.user
        return super().form_valid(form)

class FlashCardUpdate(LoginRequiredMixin, UpdateView):
    model = FlashCard
    fields = ["front_text", "hint", "explanation", "topic"]
    template_name = "quizmaker/flashcard_form.html"

class FlashCardDelete(LoginRequiredMixin, DeleteView):
    model = FlashCard
    template_name = "quizmaker/flashcard_confirm_delete.html"

class QuizHistoryList(LoginRequiredMixin, ListView):
    model = QuizHistory
    template_name = "quizmaker/quizhistory_list.html"

    def get_queryset(self):
        sort_by = self.request.GET.get("sort", "recent")
        if sort_by == "topic":
            return QuizHistory.objects.all().order_by("quiz__quiz_topic")
        return QuizHistory.objects.all().order_by('-created_at')

    def get_context_data(
        self, *, object_list = ..., **kwargs
    ):
        context = super().get_context_data()
        context['sort'] = self.request.GET.get('sort', 'recent')
        return context

class QuizHistoryDelete(LoginRequiredMixin, DeleteView):
    model = QuizHistory
    template_name = "quizmaker/flashcard_confirm_delete.html"

# class QuizCreateView(CreateView):
#     model = Quiz
#     form_class = QuizCreationForm
#     template_name = "quizmaker/quiz_form.html"
#
#     def form_valid(self, form):
#         pdf_file = self.request.FILES.get("pdf_file")
#         if not pdf_file:
#             form.add_error(None, "Please attach a PDF for quiz generation.")
#             return self.form_invalid(form)
#
#         try:
#             pdf_file.seek(0)
#             with pdfplumber.open(pdf_file) as pdf:
#                 extracted_text = "\n".join(
#                     page.extract_text() for page in pdf.pages if page.extract_text()
#                 )
#             pdf_file.seek(0)
#
#         except Exception as e:
#             form.add_error(
#                 None,
#                 "We couldn't read that PDF — it may be corrupted or scanned as images "
#                 "without extractable text."
#             )
#             return self.form_invalid(form)
#
#         char_count = len(extracted_text)
#         print(f"[pdf check] file size: {pdf_file.size:,} bytes, "
#               f"extracted text: {char_count:,} chars, "
#               f"limit: {PDF_TEXT_CHAR_LIMIT:,} chars")
#         if char_count > PDF_TEXT_CHAR_LIMIT:
#             form.add_error(
#                 None,
#                 f"This PDF has too much text for reliable quiz generation "
#                 f"({char_count:,} characters; the limit is {PDF_TEXT_CHAR_LIMIT:,}, "
#                 f"roughly 8-15 pages). Try a shorter document, or split it into sections."
#             )
#             return self.form_invalid(form)
#
#         if char_count < MIN_PDF_TEXT_CHARS:
#             form.add_error(
#                 None,
#                 "This PDF doesn't have enough extractable text to generate a quiz from "
#                 "— it may be scanned or image-based. Try a different file."
#             )
#             return self.form_invalid(form)
#
#
#         quiz = form.save(commit=False)
#         quiz.creator = self.request.user
#         quiz.status = "PENDING"
#         quiz.save()
#
#         temp_name = f"tmp_uploads/{uuid.uuid4()}_{pdf_file.name}"
#         saved_path = default_storage.save(temp_name, pdf_file)
#         full_path = default_storage.path(saved_path)
#         generate_quiz_task.delay(quiz.pk, full_path)
#
#         return redirect("quiz:processing", pk=quiz.pk)


class QuizCreateView(CreateView):
    model = Quiz
    form_class = QuizCreationForm
    template_name = "quizmaker/quiz_form.html"

    def form_valid(self, form):
        pdf_file = self.request.FILES.get("pdf_file")
        if not pdf_file:
            form.add_error(None, "Please attach a PDF for quiz generation.")
            return self.form_invalid(form)

        try:
            pdf_file.seek(0)
            with pdfplumber.open(pdf_file) as pdf:
                page_count = len(pdf.pages)
            pdf_file.seek(0)  # reset pointer so it can still be saved to disk below
        except Exception:
            form.add_error(None, "We couldn't read that PDF — it may be corrupted.")
            return self.form_invalid(form)

        if page_count == 0:
            form.add_error(None, "This PDF appears to have no pages.")
            return self.form_invalid(form)

        if page_count > MAX_PDF_PAGES:
            form.add_error(
                None,
                f"This PDF has {page_count} pages; the limit is {MAX_PDF_PAGES} "
                f"pages for reliable quiz generation. Try a shorter document, "
                f"or split it into sections."
            )
            return self.form_invalid(form)

        quiz = form.save(commit=False)
        quiz.creator = self.request.user
        quiz.status = "PENDING"
        quiz.save()

        temp_name = f"tmp_uploads/{uuid.uuid4()}_{pdf_file.name}"
        saved_path = default_storage.save(temp_name, pdf_file)
        full_path = default_storage.path(saved_path)
        generate_quiz_task.delay(quiz.pk, full_path)

        return redirect("quiz:processing", pk=quiz.pk)


def quiz_processing_view(request, pk):
    quiz = get_object_or_404(Quiz, pk=pk, creator=request.user)
    return render(request, "quizmaker/quiz_processing.html", {"quiz": quiz})

def quiz_status_view(request, pk):
    quiz = get_object_or_404(Quiz, pk=pk, creator=request.user)
    data = {"status": quiz.status}
    if quiz.status == "READY":
        data["redirect_url"] = reverse("quiz:quiz_take", args=[quiz.pk])
    elif quiz.status == "FAILED":
        data["error_message"] = quiz.error_message
    return JsonResponse(data)


@login_required
def quiz_take_view(request, pk):
    quiz = get_object_or_404(Quiz, pk=pk, creator=request.user)

    if request.method == "POST":
        total = quiz.questions.count()

        history = QuizHistory.objects.create(
            quiz=quiz,
            user=request.user,
            num_correct=0,
            num_wrong=0,
            total_attempted=total,
        )

        num_correct = 0
        for question in quiz.questions.all():
            selected_id = request.POST.get(f"question_{question.pk}")
            # .filter(question=question, ...) keeps the lookup scoped to
            # this question's own options, even if someone tampered with
            # the POST data to reference an answer from a different question.
            selected_answer = (
                question.answers.filter(pk=selected_id).first()
                if selected_id else None
            )
            is_correct = bool(selected_answer and selected_answer.is_correct)
            if is_correct:
                num_correct += 1

            QuizAttemptAnswer.objects.create(
                quiz_history=history,
                question=question,
                selected_answer=selected_answer,
                is_correct=is_correct,
            )

        history.num_correct = num_correct
        history.num_wrong = total - num_correct
        history.save(update_fields=["num_correct", "num_wrong"])

        return redirect("quiz:quiz_results", pk=history.pk)

    return render(request, "quizmaker/quiz_take.html", {"quiz": quiz})

@login_required
def quiz_results_view(request, pk):
    # pk here is the QuizHistory id (a specific attempt), not the Quiz id —
    # the same quiz can be taken more than once, each with its own results.
    quiz_history = get_object_or_404(QuizHistory, pk=pk, user=request.user)
    return render(request, "quizmaker/quiz_results.html", {"quiz_history": quiz_history})


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

        correct_answer = question.answers.filter(is_correct=True).first()

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
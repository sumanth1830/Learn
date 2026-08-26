from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, Http404, JsonResponse
from django.template import loader
import uuid

from .models import Quiz, QuizHistory, FlashCard, QuizAttemptAnswer
from django.views.generic.edit import UpdateView, DeleteView, CreateView
from django.views.generic import ListView
from .forms import FlashCardForm, QuizCreationForm
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.urls import reverse_lazy, reverse
from .tasks import generate_quiz_task
from django.core.files.storage import default_storage
# Create your views here.

def home(request):
    template = loader.get_template("quizmaker/home.html")
    # return redirect("Welcome to the Quiz Maker!")
    return render(request, "quizmaker/home.html")


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
    form_class = UserCreationForm
    # reverse lazy generates a full url from a name
    success_url = reverse_lazy("quiz:home")
    template_name = "registration/signup.html"

class FlashCardList(LoginRequiredMixin, ListView):
    model = FlashCard
    template_name = "quizmaker/flashcard_list.html"

class FlashCardCreate(LoginRequiredMixin, CreateView):
    model = FlashCard
    fields = ["front_text", "hint", "explanation", "topic"]
    template_name = "quizmaker/flashcard_form.html"
    form_class = FlashCardForm

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

class QuizHistoryDelete(LoginRequiredMixin, DeleteView):
    model = QuizHistory
    template_name = "quizmaker/flashcard_confirm_delete.html"

class QuizCreateView(CreateView):
    model = Quiz
    form_class = QuizCreationForm
    template_name = "quizmaker/quiz_form.html"

    def form_valid(self, form):
        pdf_file = self.request.FILES.get("pdf_file")
        if not pdf_file:
            form.add_error(None, "Please attach a PDF for quiz generation.")
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

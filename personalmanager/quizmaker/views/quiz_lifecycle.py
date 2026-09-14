import os
import tempfile
import uuid

import boto3
import pdfplumber
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.storage import default_storage
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic.edit import CreateView

from ..forms import QuizCreationForm
from ..models import Quiz, QuizAttemptAnswer, QuizFlag, QuizHistory, QuizReview
from ..tasks import generate_quiz_task, resume_quiz_task, retry_quiz_task

MAX_PDF_PAGES = 15


class QuizCreateView(LoginRequiredMixin, CreateView):
    model = Quiz
    form_class = QuizCreationForm
    template_name = "quizmaker/quiz_form.html"

    def get_initial(self):
        initial = super().get_initial()
        from_quiz_id = self.request.GET.get("from_quiz")
        if from_quiz_id:
            prior_quiz = Quiz.objects.filter(pk=from_quiz_id, creator=self.request.user).first()
            if prior_quiz:
                initial.update({
                    "quiz_name": prior_quiz.quiz_name,
                    "quiz_topic": prior_quiz.quiz_topic,
                    "description": prior_quiz.description,
                    "max_questions": prior_quiz.max_questions,
                    "difficulty": prior_quiz.difficulty,
                    "tips_for_quiz_creation": prior_quiz.tips_for_quiz_creation,
                    "exam_name": prior_quiz.exam_name,
                })

                category = getattr(getattr(prior_quiz, "aggregate_metrics", None), "guardrail_category", "") or \
                           getattr(getattr(prior_quiz, "aggregate_metrics", None), "safety_category", "")
                if category in ("off_topic", "manipulative"):
                    initial.pop("tips_for_quiz_creation", None)
        return initial

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

        # Production: Django and the Celery worker run in separate
        # containers with no shared filesystem, so the file has to go to
        # real object storage. Local dev: both run on the same machine,
        # so plain disk works fine and avoids needing bucket credentials
        # just to develop.
        if os.getenv("AWS_ENDPOINT_URL"):
            s3_client = boto3.client("s3", endpoint_url=os.getenv("AWS_ENDPOINT_URL"))
            file_key = f"tmp_uploads/{uuid.uuid4()}_{pdf_file.name}"
            s3_client.upload_fileobj(pdf_file, os.getenv("AWS_S3_BUCKET_NAME"), file_key)
        else:
            temp_name = f"tmp_uploads/{uuid.uuid4()}_{pdf_file.name}"
            saved_path = default_storage.save(temp_name, pdf_file)
            file_key = default_storage.path(saved_path)

        generate_quiz_task.delay(quiz.pk, file_key)

        return redirect("quiz:processing", pk=quiz.pk)


@login_required
def quiz_processing_view(request, pk):
    quiz = get_object_or_404(Quiz, pk=pk, creator=request.user)
    return render(request, "quizmaker/quiz_processing.html", {"quiz": quiz})


@login_required
def quiz_status_view(request, pk):
    quiz = get_object_or_404(Quiz, pk=pk, creator=request.user)
    data = {"status": quiz.status}
    if quiz.status == "READY":
        data["redirect_url"] = reverse("quiz:quiz_take", args=[quiz.pk])
    elif quiz.status in ("FAILED_BLOCKED", "FAILED_EXHAUSTED", "FAILED_API_ERROR"):
        data["error_message"] = quiz.error_message
        if quiz.status == "FAILED_API_ERROR":
            has_thread_id = bool(getattr(getattr(quiz, "generation_log", None), "thread_id", ""))
            data["can_resume"] = has_thread_id
    return JsonResponse(data)


@login_required
def quiz_retry_view(request, pk):
    quiz = get_object_or_404(Quiz, pk=pk, creator=request.user)

    if quiz.status != "FAILED_EXHAUSTED":
        messages.error(request, "This quiz isn't in a state that can be retried.")
        return redirect("quiz:processing", pk=quiz.pk)

    retry_quiz_task.delay(quiz.pk)
    return redirect("quiz:processing", pk=quiz.pk)


@login_required
def quiz_resume_view(request, pk):
    quiz = get_object_or_404(Quiz, pk=pk, creator=request.user)
    if quiz.status != "FAILED_API_ERROR":
        messages.error(request, "This quiz isn't in a state that can be resumed.")
        return redirect("quiz:processing", pk=quiz.pk)
    resume_quiz_task.delay(quiz.pk)
    return redirect("quiz:processing", pk=quiz.pk)


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

        # for the quiz rating/review handling
        url = reverse("quiz:quiz_results", args=[history.pk])
        return redirect(f"{url}?just_completed=1")

    return render(request, "quizmaker/quiz_take.html", {"quiz": quiz})


@login_required
def quiz_results_view(request, pk):
    quiz_history = get_object_or_404(QuizHistory, pk=pk, user=request.user)
    quiz = quiz_history.quiz

    show_review_prompt = (
        request.GET.get("just_completed") == "1"
        and not QuizReview.objects.filter(quiz=quiz).exists()
    )

    existing_flags = QuizFlag.objects.filter(quiz=quiz, reporter=request.user)
    quiz_already_flagged = existing_flags.filter(question__isnull=True).exists()
    flagged_question_ids = set(
        existing_flags.filter(question__isnull=False).values_list("question_id", flat=True)
    )

    return render(request, "quizmaker/quiz_results.html", {
        "quiz_history": quiz_history,
        "show_review_prompt": show_review_prompt,
        "quiz_already_flagged": quiz_already_flagged,
        "flagged_question_ids": flagged_question_ids,
    })
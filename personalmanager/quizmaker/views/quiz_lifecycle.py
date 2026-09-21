import os
import tempfile
import uuid

import boto3
import pdfplumber
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.storage import default_storage
from django.http import JsonResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic.edit import CreateView

from ..forms import QuizCreationForm
from ..models import Quiz, QuizAttemptAnswer, QuizFlag, QuizHistory, QuizReview, UserActivity
from ..tasks import generate_quiz_task, resume_quiz_task, retry_quiz_task


# To limit the PDF file content
MAX_PDF_PAGES = 15


class QuizCreateView(LoginRequiredMixin, CreateView):
    model = Quiz
    form_class = QuizCreationForm
    template_name = "quizmaker/quiz_form.html"

    def get_initial(self):
        """
        To handle the content during Revise and Resubmit flow
        and prefill the quiz details in the Quiz Form,
        skipping the description and tips for generation fields
        """
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
                    initial.pop("description", None)
        return initial

    def form_valid(self, form):
        """
        Validating the form
        Making sure the PDF files are not large enough
        to handle cost and context of llm models
        """
        pdf_file = self.request.FILES.get("pdf_file")
        if not pdf_file:
            form.add_error(None, "Please attach a PDF for quiz generation.")
            return self.form_invalid(form)

        try:
            pdf_file.seek(0)
            with pdfplumber.open(pdf_file) as pdf:
                page_count = len(pdf.pages)
            pdf_file.seek(0)
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

        # Production: Needs bucket credentials as Django and Celery work in separate containers
        # Development: This works fine
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
    """
    Processing Quiz Page displayed while Celery worker runs in the background
    """
    quiz = get_object_or_404(Quiz, pk=pk, creator=request.user)
    return render(request, "quizmaker/quiz_processing.html", {"quiz": quiz})


@login_required
def quiz_status_view(request, pk):
    """
    This view comes into effect when there is an error/problem in the Quiz Generation
    """
    quiz = get_object_or_404(Quiz, pk=pk, creator=request.user)
    data = {"status": quiz.status}
    if quiz.status == "READY":
        data["redirect_url"] = reverse("quiz:quiz_take", args=[quiz.pk])
    elif quiz.status in ("FAILED_BLOCKED", "FAILED_EXHAUSTED", "FAILED_API_ERROR"):
        data["error_message"] = quiz.error_message
        if quiz.status == "FAILED_API_ERROR":
            has_trace = quiz.traces.exists()
            data["can_resume"] = has_trace
    return JsonResponse(data)


@login_required
def quiz_retry_view(request, pk):
    """
    To initiate the retry quiz task and redo the quiz generation
    when the earlier attempt hit the limits on either Structural or
    Evaluator
    """
    quiz = get_object_or_404(Quiz, pk=pk, creator=request.user)

    if quiz.status != "FAILED_EXHAUSTED":
        messages.error(request, "This quiz isn't in a state that can be retried.")
        return redirect("quiz:processing", pk=quiz.pk)

    retry_quiz_task.delay(quiz.pk)
    return redirect("quiz:processing", pk=quiz.pk)


@login_required
def quiz_resume_view(request, pk):
    """
    To resume the quiz, if there is an API error during the quiz generation
    Checkpointer comes into picture here
    """
    quiz = get_object_or_404(Quiz, pk=pk, creator=request.user)
    if quiz.status != "FAILED_API_ERROR":
        messages.error(request, "This quiz isn't in a state that can be resumed.")
        return redirect("quiz:processing", pk=quiz.pk)
    resume_quiz_task.delay(quiz.pk)
    return redirect("quiz:processing", pk=quiz.pk)


@login_required
def quiz_take_view(request, pk):
    """
    Quiz is presented to the user in this view
    Logged info on Quiz History, Quiz Attempt Answer, User Activity models
    """
    quiz = get_object_or_404(Quiz, pk=pk)

    is_digest_quiz = hasattr(quiz, "source_digest")
    if not is_digest_quiz and quiz.creator != request.user:
        raise Http404("No Quiz matches the given query.")

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

        # For user activity tracking - updates when user takes a quiz
        UserActivity.objects.get_or_create(
            user=request.user, activity_date=timezone.now().date()
        )

        # for the quiz rating/review handling
        url = reverse("quiz:quiz_results", args=[history.pk])
        return redirect(f"{url}?just_completed=1")

    return render(request, "quizmaker/quiz_take.html", {"quiz": quiz})


@login_required
def quiz_results_view(request, pk):
    """
    View to display the user results, ability to flag questions
    Correct Answer with explanation to the User.
    justcompleted=1 is used as a query param to differentiate and provide
    option to show user rating view
    It's only shown during first time the user visits the quiz results page
    """
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
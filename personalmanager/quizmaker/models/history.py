from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse

from .base import TimeStampedModel
from .quiz import Quiz, Question, Answer


class QuizHistory(TimeStampedModel):
    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name='attempts'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="quiz_history"
    )
    num_correct = models.IntegerField(default=0)
    num_wrong = models.IntegerField(default=0)
    total_attempted = models.IntegerField(default=0)
    flashcards_created = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user} - {self.quiz.quiz_name} ({self.created_at.strftime('%Y-%m-%d')})"

    def get_absolute_url(self):
        return reverse("quiz:quiz_history_list")


class QuizAttemptAnswer(TimeStampedModel):
    """One row per question, per attempt — what the user picked and whether
    it was right. QuizHistory alone only has the aggregate counts; this is
    what makes a detailed results review possible."""
    quiz_history = models.ForeignKey(
        QuizHistory,
        on_delete=models.CASCADE,
        related_name="attempt_answers",
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="attempt_answers",
    )
    selected_answer = models.ForeignKey(
        Answer,
        on_delete=models.CASCADE,
        related_name="+",
        null=True,
        blank=True,  # null if the question somehow went unanswered
    )
    is_correct = models.BooleanField(default=False)
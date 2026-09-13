from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.contrib.auth.models import User

from .base import TimeStampedModel


class Quiz(TimeStampedModel):
    difficulty_types = [
        ("EASY", "Easy"),
        ("MED", "Medium"),
        ("HARD", "Hard"),
    ]
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("PROCESSING", "Processing"),
        ("READY", "Ready"),
        ("FAILED_BLOCKED", "Blocked"),
        ("FAILED_EXHAUSTED", "Failed - Retries Exhausted"),
        ("FAILED_API_ERROR", "Failed - System Error"),
    ]
    EXAM_CHOICES = [
        ("UPSC", "UPSC Prelims"),
        ("GENERAL", "General Knowledge"),
        ("AI_ML", "AI / Machine Learning"),
        ("INTERVIEW_PREP", "Interview Preparation"),
        ("GRADE_12_BELOW", "12th Grade and Below"),
    ]

    status = models.CharField(max_length=17, choices=STATUS_CHOICES, default="PENDING")
    error_message = models.TextField(blank=True)

    quiz_name = models.CharField(max_length=30)
    quiz_topic = models.CharField(max_length=50)
    max_questions = models.IntegerField(
        default=0,
        validators=[
            MinValueValidator(1, message="Must generate at least 1 question."),
            MaxValueValidator(20, message="Can only generate 20 questions at once.")
        ]
    )
    difficulty = models.CharField(max_length=6, choices=difficulty_types, default="EASY")
    tips_for_quiz_creation = models.TextField(blank=True)
    exam_name = models.CharField(max_length=20, choices=EXAM_CHOICES, default="UPSC")
    description = models.TextField(blank=True)
    creator = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_quizzes"
    )


class Question(TimeStampedModel):
    QUESTION_TYPES = [
        ("MCQ", "Multiple Choice Questions"),
        ("SQ", "Single Answer Questions")
    ]
    question_text = models.TextField()
    topic = models.CharField(max_length=50)
    question_type = models.CharField(choices=QUESTION_TYPES, max_length=3)
    hint = models.TextField(default="")
    explanation = models.TextField(
        blank=True,
        help_text="Why the correct answer is correct, grounded in the source material."
    )
    creator = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_questions"
    )
    source_citation = models.TextField(
        blank=True,
        default="",
        help_text="The passage from the source document this question's facts were drawn from.",
    )
    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name="questions",
    )

    def __str__(self):
        return f"[{self.question_type}] {self.question_text[:50]}"


class Answer(TimeStampedModel):
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="answers"
    )
    answer_text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)
    is_option = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.answer_text} (Correct: {self.is_correct})"
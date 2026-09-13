from django.db import models
from django.contrib.auth.models import User

from .base import TimeStampedModel
from .quiz import Quiz, Question


class QuizReview(TimeStampedModel):
    RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]
    MATCH_CHOICES = [
        ("YES", "Yes"),
        ("SOMEWHAT", "Somewhat"),
        ("NO", "No"),
        ("N/A", "N/A"),
    ]

    quiz = models.OneToOneField(Quiz, on_delete=models.CASCADE, related_name="review")
    rating = models.IntegerField(choices=RATING_CHOICES)
    matched_instructions = models.CharField(max_length=8, choices=MATCH_CHOICES, default="N/A")

    def __str__(self):
        return f"{self.quiz} - {self.rating}★"


class QuizFlag(TimeStampedModel):
    REASON_CHOICES = [
        ("FACTUALLY_INCORRECT", "Factually incorrect"),
        ("DOESNT_MATCH_SOURCE", "Doesn't match the source material"),
        ("INAPPROPRIATE", "Inappropriate content"),
        ("TECHNICAL_ISSUE", "Technical issue (formatting, broken display, etc.)"),
        ("OTHER", "Other"),
    ]

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="flags")
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="flags",
        null=True, blank=True,  # null = whole-quiz flag, set = this specific question
    )
    reporter = models.ForeignKey(User, on_delete=models.CASCADE, related_name="quiz_flags")
    reason = models.CharField(max_length=24, choices=REASON_CHOICES)
    detail = models.TextField(blank=True, default="")

    def __str__(self):
        target = f"Q: {self.question_id}" if self.question_id else "whole quiz"
        return f"{self.quiz} ({target}) - {self.reason}"
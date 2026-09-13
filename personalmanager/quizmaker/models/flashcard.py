from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse

from .base import TimeStampedModel


class FlashCard(TimeStampedModel):
    front_text = models.TextField(verbose_name="Flash Text")
    hint = models.TextField(default="")
    explanation = models.TextField(verbose_name="Explanation")
    topic = models.CharField(max_length=50, verbose_name="Topic")
    creator = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="flashcards"
    )

    def __str__(self):
        return f"{self.front_text[:30]}"

    def get_absolute_url(self):
        return reverse("quiz:flashcard_list")
from django.db import models
from django.contrib.auth.models import User

from .base import TimeStampedModel


class PilotAccessCode(TimeStampedModel):
    code = models.CharField(max_length=20, unique=True)
    used_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    used_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=100, blank=True)

    def __str__(self):
        status = f"used by {self.used_by}" if self.used_by else "unused"
        return f"{self.code} ({status})"
from datetime import timedelta

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

from .base import TimeStampedModel


class UserActivity(TimeStampedModel):
    """
    One row per user per calendar day (server UTC as computing based on user timezone is complex for now)
    they did something that counts toward their streak - a completed quiz, or a flashcard
    study session.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="activity_days")
    activity_date = models.DateField()

    class Meta:
        unique_together = [("user", "activity_date")]

    def __str__(self):
        return f"{self.user} - {self.activity_date}"


# Utility function
def compute_current_streak(user):
    """
    Walks backward from today (server UTC) counting consecutive days
    with a UserActivity row. Stops at the first gap.
    """
    activity_dates = set(
        UserActivity.objects.filter(user=user).values_list("activity_date", flat=True)
    )

    today = timezone.now().date()
    streak = 0
    check_date = today

    while check_date in activity_dates:
        streak += 1
        check_date -= timedelta(days=1)

    return streak
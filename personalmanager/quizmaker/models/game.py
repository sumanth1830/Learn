from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from .base import TimeStampedModel


class GameProfile(TimeStampedModel):
    """A player's game state for the Unity game: the coin wallet.
    Coins are earned in boss battles and spent repairing the village."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="game_profile")
    coins = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.user} - {self.coins} coins"


class VillageArea(TimeStampedModel):
    """One chapter's area of a player's village.

    base_health (0-1) is what battles damage and repairs restore. Neglect
    (overdue flashcards) is subtracted when the health is read, so time
    passing needs no background job."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="village_areas")
    chapter_key = models.CharField(max_length=10)   # "ch4", "ch6", ...
    base_health = models.FloatField(
        default=1.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "chapter_key"],
                                    name="unique_village_area_per_user"),
        ]

    def __str__(self):
        return f"{self.user} - {self.chapter_key}: {self.base_health:.0%}"
from django.contrib.auth.models import User
from django.db import models
from pgvector.django import VectorField, HnswIndex

from . import QuizAttemptAnswer
from .base import TimeStampedModel


class SourceChunk(TimeStampedModel):
    source_text = models.ForeignKey(
        "SourceText", on_delete=models.CASCADE, related_name="chunks"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="source_chunks"
    )
    content = models.TextField()
    header = models.CharField(max_length=255, blank=True, default="")
    chunk_type = models.CharField(
        max_length=10,
        choices=[("prose", "Prose"), ("table", "Table")],
        default="prose",
    )
    topic_name = models.CharField(max_length=100, blank=True, default="")
    embedding = VectorField(dimensions=1536)

    class Meta:
        indexes = [
            HnswIndex(
                name="source_chunk_embedding_idx",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            )
        ]


class TopicsPreviewBrief(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="topics_previews")
    content = models.JSONField(default=list, blank=True)
    wrong_answers_covered = models.ManyToManyField(QuizAttemptAnswer, related_name="covered_in_briefs")
    rating = models.CharField(
        max_length=10,
        choices=[("up", "Thumbs Up"), ("down", "Thumbs Down")],
        null=True,
        blank=True,
    )
    skipped_questions = models.JSONField(default=list, blank=True)


class TopicsPreviewCost(TimeStampedModel):
    brief = models.OneToOneField(TopicsPreviewBrief, on_delete=models.CASCADE, related_name="cost")
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    cost = models.DecimalField(max_digits=10, decimal_places=6)
    total_time_seconds = models.FloatField()
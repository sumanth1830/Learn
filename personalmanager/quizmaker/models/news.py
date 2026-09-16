from django.db import models

from quizmaker.models import TimeStampedModel, Quiz


class NewsArticle(TimeStampedModel):
    pib_release_id = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=255)
    title_slug = models.CharField(max_length=60, db_index=True)
    issuing_authority = models.CharField(max_length=150, blank=True, default="")
    source_url = models.URLField()
    published_at = models.DateTimeField(null=True, blank=True)
    raw_text = models.TextField()
    digest_included = models.BooleanField(null=True, blank=True)
    filter_reason = models.TextField(blank=True, default="")

    def __str__(self):
        return f"{self.title[:60]} ({self.pib_release_id})"


class DailyDigest(TimeStampedModel):
    digest_date = models.DateField(unique=True)
    content = models.TextField(blank=True, default="")
    quiz = models.OneToOneField(
        Quiz, null=True, blank=True, on_delete=models.SET_NULL, related_name="source_digest"
    )

    def __str__(self):
        return f"Digest for {self.digest_date}"
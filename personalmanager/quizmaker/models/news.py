from django.db import models

from quizmaker.models import TimeStampedModel, Quiz


class NewsArticle(TimeStampedModel):
    pib_release_id = models.CharField(max_length=50, unique=True)
    title = models.TextField()
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


class DigestNodeCost(models.Model):
    digest = models.ForeignKey(DailyDigest, on_delete=models.CASCADE, related_name="node_costs")
    node_name = models.CharField(max_length=50)  # "filter", "relevance_filter", "summary", "evaluator"
    attempt = models.IntegerField(default=0)
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    cost = models.DecimalField(max_digits=10, decimal_places=6)


class DigestAggregateMetrics(models.Model):
    digest = models.OneToOneField(DailyDigest, on_delete=models.CASCADE, related_name="metrics")
    total_cost = models.DecimalField(max_digits=10, decimal_places=6)
    total_calls = models.IntegerField(default=0)
    groups_approved = models.IntegerField(default=0)
    groups_exhausted = models.IntegerField(default=0)
    total_time_seconds = models.FloatField()
    run_log = models.JSONField(default=dict, blank=True)
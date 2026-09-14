from django.db import models

from .base import TimeStampedModel
from .quiz import Quiz


class QuizAggregateMetrics(TimeStampedModel):
    quiz = models.OneToOneField(Quiz, on_delete=models.CASCADE, related_name="aggregate_metrics")

    end_reason = models.CharField(max_length=40, default="")
    structural_attempts = models.IntegerField(default=0)
    evaluator_attempts = models.IntegerField(default=0)
    correction_occurred = models.BooleanField(default=False)
    guardrail_category = models.CharField(max_length=30, blank=True, default="")
    safety_category = models.CharField(max_length=30, blank=True, default="")
    total_time_seconds = models.FloatField(null=True, blank=True)
    total_cost = models.FloatField(default=0.0)

    def __str__(self):
        return f"{self.quiz} - {self.end_reason}"


class QuizGenerationLog(TimeStampedModel):
    quiz = models.OneToOneField(Quiz, on_delete=models.CASCADE, related_name="generation_log")
    structural_feedback = models.TextField(blank=True, default="")
    evaluation_feedback = models.JSONField(default=list, blank=True)
    guardrail_reason = models.TextField(blank=True, default="")
    safety_reason = models.TextField(blank=True, default="")

    def __str__(self):
        return f"Generation log for {self.quiz}"


class SourceText(TimeStampedModel):
    quiz = models.OneToOneField(Quiz, on_delete=models.CASCADE, related_name="source_text_record")
    source_text = models.TextField()

    def __str__(self):
        return f"Source text for {self.quiz}"


class QuizNodeCost(TimeStampedModel):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="node_costs")
    attempt_id = models.CharField(max_length=60, blank=True, default="")
    agent = models.CharField(max_length=30)
    model = models.CharField(max_length=60, blank=True, default="")
    cost = models.FloatField(default=0.0)
    input_cost = models.FloatField(default=0.0)
    output_cost = models.FloatField(default=0.0)
    prompt_tokens = models.IntegerField(null=True, blank=True)
    completion_tokens = models.IntegerField(null=True, blank=True)
    duration_seconds = models.FloatField(null=True, blank=True)

    def __str__(self):
        return f"{self.quiz} - {self.agent} (${self.cost:.4f})"


class QuizTrace(TimeStampedModel):
    """
    To save traces of a quiz, as we can have multiple traces
    when generation fails midway
    """
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="traces")
    attempt_id = models.CharField(max_length=60)
    mlflow_trace_id = models.CharField(max_length=100)
    crashed = models.BooleanField(default=False)

    class Meta:
        unique_together = [("quiz", "mlflow_trace_id")]

    def __str__(self):
        return f"{self.quiz} - {self.attempt_id} ({self.mlflow_trace_id})"
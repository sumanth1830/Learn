from django.db import models
from django.contrib.auth.models import User

# Create your models here.
class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class Question(TimeStampedModel):
    QUESTION_TYPES = [
        ("MCQ", "Multiple Choice Questions"),
        ("SQ", "Single Answer Questions")
    ]
    question_text = models.CharField(max_length=100)
    topic = models.CharField(max_length=50)
    question_type = models.CharField(choices=QUESTION_TYPES, max_length=3)
    creator = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_questions"
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

class Quiz(TimeStampedModel):
    quiz_topic = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    creator = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_quizzes"
    )
    questions = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="questions",
    )

class QuizHistory(TimeStampedModel):
    # quiz_date = models.DateField()
    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name='attempts'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="quiz_history"
    )
    num_correct = models.IntegerField(default=0)
    num_wrong = models.IntegerField(default=0)
    total_attempted = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.user} - {self.quiz.title} ({self.created_at.strftime('%Y-%m-%d')})"

    def get_absolute_url(self):
        return "list"


class FlashCard(TimeStampedModel):
    front_text = models.CharField(max_length=100, verbose_name="Flash Text")
    hint = models.CharField(max_length=100, blank=True)
    explanation = models.CharField(max_length=255, verbose_name="Explanation")
    topic = models.CharField(max_length=50, verbose_name="Topic")
    creator = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="flashcards"
    )

    def __str__(self):
        return f"{self.front_text[:30]}"

    def get_absolute_url(self):
        return "list"

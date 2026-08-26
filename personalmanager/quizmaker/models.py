from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse

# Create your models here.
class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Quiz(TimeStampedModel):
    difficulty_types = [
        ("EASY", "Easy"),
        ("MED", "Medium"),
        ("HARD", "Hard"),
    ]
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("PROCESSING", "Processing"),
        ("READY", "Ready"),
        ("FAILED", "Failed"),
    ]
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="PENDING")
    error_message = models.TextField(blank=True)

    quiz_name = models.CharField(max_length=30)
    quiz_topic = models.CharField(max_length=50)
    max_questions = models.IntegerField(
        default=0,
        validators=[
            MinValueValidator(1, message="Must generate at least 1 question."),
            MaxValueValidator(20, message="Can only generate 20 questions at once.")
        ]
    )
    difficulty = models.CharField(max_length=6, choices=difficulty_types, default="EASY")
    tips_for_quiz_creation = models.TextField(blank=True)
    exam_name = models.CharField(max_length=40, help_text="Specify the exam you are preparing for to generate tailored quiz questions.")
    description = models.TextField(blank=True)
    creator = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_quizzes"
    )
    # questions = models.ForeignKey(
    #     Question,
    #     on_delete=models.CASCADE,
    #     related_name="questions",
    # )


class Question(TimeStampedModel):
    QUESTION_TYPES = [
        ("MCQ", "Multiple Choice Questions"),
        ("SQ", "Single Answer Questions")
    ]
    question_text = models.TextField()
    topic = models.CharField(max_length=50)
    question_type = models.CharField(choices=QUESTION_TYPES, max_length=3)
    explanation = models.TextField(
        blank=True,
        help_text="Why the correct answer is correct, grounded in the source material."
    )
    creator = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_questions"
    )
    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name="questions",
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
        return f"{self.user} - {self.quiz.quiz_name} ({self.created_at.strftime('%Y-%m-%d')})"

    def get_absolute_url(self):
        return reverse("quiz:quiz_history_list")


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
        return reverse("quiz:flashcard_list")

class QuizAttemptAnswer(TimeStampedModel):
    """One row per question, per attempt — what the user picked and whether
    it was right. QuizHistory alone only has the aggregate counts; this is
    what makes a detailed results review possible."""
    quiz_history = models.ForeignKey(
        QuizHistory,
        on_delete=models.CASCADE,
        related_name="attempt_answers",
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="attempt_answers",
    )
    selected_answer = models.ForeignKey(
        Answer,
        on_delete=models.CASCADE,
        related_name="+",
        null=True,
        blank=True,  # null if the question somehow went unanswered
    )
    is_correct = models.BooleanField(default=False)
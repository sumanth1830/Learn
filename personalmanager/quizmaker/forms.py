from django import forms
from .models import FlashCard, Quiz

class FlashCardForm(forms.ModelForm):
    class Meta:
        model = FlashCard
        fields = ("front_text", "hint", "explanation", "topic")

class QuizCreationForm(forms.ModelForm):
    class Meta:
        model = Quiz
        fields = (
            "quiz_name", "quiz_topic", "description", "max_questions",
            "difficulty", "tips_for_quiz_creation", "exam_name"
        )
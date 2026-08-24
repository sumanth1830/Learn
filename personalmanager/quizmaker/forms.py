from django import forms
from .models import FlashCard, QuizHistory

class FlashCardForm(forms.ModelForm):
    class Meta:
        model = FlashCard
        fields = ("front_text", "hint", "explanation", "topic")
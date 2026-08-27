from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone

from .models import FlashCard, Quiz, PilotAccessCode


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


class SignupForm(UserCreationForm):
    access_code = forms.CharField(
        label="Access code",
        max_length=20,
        widget=forms.TextInput(attrs={"autocomplete": "off"}),
    )

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def clean_access_code(self):
        code = self.cleaned_data.get("access_code", "").strip()
        match = PilotAccessCode.objects.filter(code=code, used_by__isnull=True).first()
        if not match:
            raise forms.ValidationError("That access code isn't valid.")

        self._matched_code = match
        return code

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            self._matched_code.used_by = user
            self._matched_code.used_at = timezone.now()
            self._matched_code.save(update_fields=["used_by", "used_at"])
        return user




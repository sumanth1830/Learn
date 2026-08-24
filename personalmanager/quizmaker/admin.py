from django.contrib import admin
from .models import QuizHistory, Quiz, Question, Answer, FlashCard

# Register your models here.
admin.site.register([
    QuizHistory,
    Quiz,
    Question,
    Answer,
    FlashCard,
])
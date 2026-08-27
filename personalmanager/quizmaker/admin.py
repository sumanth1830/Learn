from django.contrib import admin
from .models import QuizHistory, Quiz, Question, Answer, FlashCard, PilotAccessCode

# Register your models here.
admin.site.register([
    QuizHistory,
    Quiz,
    Question,
    Answer,
    FlashCard,
])


@admin.register(PilotAccessCode)
class PilotAccessCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "note", "used_by", "used_at", "created_at")
    list_filter = ("used_by",)
    search_fields = ("code", "note")
    readonly_fields = ("used_by", "used_at")

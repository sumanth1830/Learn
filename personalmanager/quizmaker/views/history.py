from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import ListView
from django.views.generic.edit import DeleteView

from ..models import QuizHistory


class QuizHistoryList(LoginRequiredMixin, ListView):
    model = QuizHistory
    template_name = "quizmaker/quizhistory_list.html"

    def get_queryset(self):
        sort_by = self.request.GET.get("sort", "recent")
        if sort_by == "topic":
            return QuizHistory.objects.all().order_by("quiz__quiz_topic")
        return QuizHistory.objects.all().order_by('-created_at')

    def get_context_data(
        self, *, object_list=..., **kwargs
    ):
        context = super().get_context_data()
        context['sort'] = self.request.GET.get('sort', 'recent')
        return context


class QuizHistoryDelete(LoginRequiredMixin, DeleteView):
    model = QuizHistory
    template_name = "quizmaker/quizhistory_confirm_delete.html"
    success_url = reverse_lazy("quiz:quiz_history_list")
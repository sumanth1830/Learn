from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.generic import ListView
from django.views.generic.edit import DeleteView

from ..models import QuizHistory, Quiz


class QuizHistoryDelete(LoginRequiredMixin, DeleteView):
    model = QuizHistory
    template_name = "quizmaker/quizhistory_confirm_delete.html"
    success_url = reverse_lazy("quiz:quiz_history_list")

    def get_queryset(self):
        return QuizHistory.objects.filter(user=self.request.user)



@login_required
def quizzes_view(request):
    tab = request.GET.get("tab", "ready")

    ready_quizzes = Quiz.objects.filter(
        creator=request.user, status="READY"
    ).exclude(
        pk__in=QuizHistory.objects.filter(user=request.user).values_list("quiz_id", flat=True)
    ).order_by("-created_at")

    sort_by = request.GET.get("sort", "recent")
    history_qs = QuizHistory.objects.filter(user=request.user)
    if sort_by == "topic":
        history_qs = history_qs.order_by("quiz__quiz_topic")
    else:
        history_qs = history_qs.order_by("-created_at")

    return render(request, "quizmaker/quizzes.html", {
        "tab": tab,
        "ready_quizzes": ready_quizzes,
        "history": history_qs,
        "sort": sort_by,
    })
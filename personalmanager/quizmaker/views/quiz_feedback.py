from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from ..models import Question, Quiz, QuizFlag, QuizReview


@login_required
def quiz_review_submit_view(request, pk):
    quiz = get_object_or_404(Quiz, pk=pk, creator=request.user)

    if request.method != "POST":
        return JsonResponse({"error": "Invalid request."}, status=405)

    rating = request.POST.get("rating")
    if not rating:
        return JsonResponse({"error": "Please select a rating."}, status=400)

    QuizReview.objects.update_or_create(
        quiz=quiz,
        defaults={
            "rating": int(rating),
            "matched_instructions": request.POST.get("matched_instructions", "N/A"),
        },
    )
    return JsonResponse({"success": True})


@login_required
def quiz_flag_submit_view(request, pk):
    quiz = get_object_or_404(Quiz, pk=pk)
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request."}, status=405)

    reason = request.POST.get("reason")
    if reason not in dict(QuizFlag.REASON_CHOICES):
        return JsonResponse({"error": "Please select a reason."}, status=400)

    question_id = request.POST.get("question_id") or None
    question = None
    if question_id:
        question = get_object_or_404(Question, pk=question_id, quiz=quiz)

    already_flagged = QuizFlag.objects.filter(
        quiz=quiz, question=question, reporter=request.user
    ).exists()
    if already_flagged:
        return JsonResponse({"error": "You've already flagged this."}, status=409)

    QuizFlag.objects.create(
        quiz=quiz, question=question, reporter=request.user,
        reason=reason, detail=request.POST.get("detail", "").strip(),
    )
    return JsonResponse({"success": True})
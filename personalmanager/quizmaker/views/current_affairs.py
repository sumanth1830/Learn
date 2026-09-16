from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone
from datetime import datetime, timedelta

from ..models import NewsArticle, DailyDigest


@login_required
def current_affairs_view(request):
    date_str = request.GET.get("date")
    if date_str:
        try:
            selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            selected_date = timezone.now().date()
    else:
        selected_date = timezone.now().date()

    articles = NewsArticle.objects.filter(
        published_at__date=selected_date
    ).order_by("issuing_authority", "-published_at")

    grouped = {}
    for article in articles:
        grouped.setdefault(article.issuing_authority or "Other", []).append(article)

    digest = DailyDigest.objects.filter(digest_date=selected_date).first()

    return render(request, "quizmaker/current_affairs.html", {
        "selected_date": selected_date,
        "prev_date": selected_date - timedelta(days=1),
        "next_date": selected_date + timedelta(days=1),
        "grouped_articles": grouped,
        "digest": digest,
    })
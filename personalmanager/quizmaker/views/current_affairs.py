from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from datetime import datetime, timedelta

from ..models import NewsArticle, DailyDigest, Quiz
import re
import markdown
from ..tasks import generate_quiz_from_text_task
from ..models import QuizHistory


def render_digest_content(content):
    def replace_citation(match):
        ids_str = match.group(1)
        ids = [int(x.strip()) for x in ids_str.split(",")]
        links = []
        for article_id in ids:
            article = NewsArticle.objects.filter(id=article_id).first()
            if article and article.source_url:
                links.append(f'<a href="{article.source_url}" target="_blank" rel="noopener">{article_id}</a>')
            else:
                links.append(str(article_id))
        return f'<sup>[{", ".join(links)}]</sup>'

    linked = re.sub(r"\(ID:\s*([\d,\s]+)\)", replace_citation, content)
    md = markdown.Markdown(extensions=["toc"])
    html = md.convert(linked)
    toc_html = md.toc

    return html, toc_html


@login_required
def current_affairs_digest_view(request):
    date_str = request.GET.get("date")
    if date_str:
        try:
            selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            selected_date = timezone.now().date()
    else:
        selected_date = timezone.now().date()

    digest = DailyDigest.objects.filter(digest_date=selected_date).first()
    article_count = NewsArticle.objects.filter(published_at__date=selected_date).count()

    user_history = None
    if digest and digest.quiz:
        user_history = QuizHistory.objects.filter(
            quiz=digest.quiz, user=request.user
        ).order_by("-created_at").first()

    if digest:
        digest.rendered_content, digest.toc_html = render_digest_content(digest.content)

    return render(request, "quizmaker/current_affairs_digest.html", {
        "selected_date": selected_date,
        "prev_date": selected_date - timedelta(days=1),
        "next_date": selected_date + timedelta(days=1),
        "digest": digest,
        "article_count": article_count,
        "user_history": user_history
    })


def current_affairs_articles_view(request):
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

    return render(request, "quizmaker/current_affairs_articles.html", {
        "selected_date": selected_date,
        "prev_date": selected_date - timedelta(days=1),
        "next_date": selected_date + timedelta(days=1),
        "grouped_articles": grouped,
    })


@login_required
def generate_digest_quiz_view(request, date):
    from datetime import datetime
    digest_date = datetime.strptime(date, "%Y-%m-%d").date()
    digest = get_object_or_404(DailyDigest, digest_date=digest_date)

    if digest.quiz:
        return redirect("quiz:processing", pk=digest.quiz.pk)

    quiz = Quiz.objects.create(
        quiz_topic="Current Affairs",
        exam_name="UPSC Prelims",
        difficulty="MED",
        max_questions=20,
        tips_for_quiz_creation="Source material is a daily current-affairs digest covering multiple government ministries - questions should draw from across the full range of topics covered, not just one section.",
        creator=request.user,
        status="PENDING",
    )
    digest.quiz = quiz
    digest.save(update_fields=["quiz"])

    generate_quiz_from_text_task.delay(quiz.pk, digest.content)

    return redirect("quiz:processing", pk=quiz.pk)
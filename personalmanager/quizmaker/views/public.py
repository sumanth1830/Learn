import io
import json
import zipfile

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.db.models import Avg, Count
from django.db.models.functions import TruncDate
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic.edit import CreateView
from pypdf import PdfReader, PdfWriter

from ..forms import SignupForm
from ..models import (
    FlashCard, Quiz, QuizAggregateMetrics, QuizFlag, QuizNodeCost, QuizReview,
    NewsArticle, DigestNodeCost, DigestAggregateMetrics,
    TopicsPreviewBrief, TopicsPreviewCost
)

AGENT_DISPLAY = {
    "guardrail_agent": {"label": "Guardrail", "icon": "ti-shield-check", "role": "danger", "desc": "Filters input and source"},
    "creator_agent": {"label": "Creator", "icon": "ti-sparkles", "role": "pro", "desc": "Generates questions"},
    "safety_agent": {"label": "Safety", "icon": "ti-scan-eye", "role": "accent", "desc": "Checks phrasing and tone"},
    "evaluator_agent": {"label": "Evaluator", "icon": "ti-search", "role": "accent", "desc": "Checks accuracy"},
    "corrector_agent": {"label": "Corrector", "icon": "ti-tool", "role": "warning", "desc": "Fixes flagged issues"},
}

NODE_DISPLAY_NAMES = {
    "filter": "Filter",
    "relevance_filter": "Relevance Filter",
    "summary": "Summarize",
    "evaluator": "Evaluate",
}


def format_tokens(n):
    if not n:
        return "0"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(int(n))


def pdf_split_view(request):
    if request.method == "GET":
        return render(request, "quizmaker/pdf_split.html")

    uploaded_file = request.FILES.get("pdf_file")
    if not uploaded_file:
        return JsonResponse({"error": "Please attach a PDF."}, status=400)

    ranges_raw = request.POST.get("ranges")
    if not ranges_raw:
        return JsonResponse({"error": "Please specify at least one page range."}, status=400)

    try:
        ranges = json.loads(ranges_raw)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({"error": "Invalid range data."}, status=400)

    try:
        reader = PdfReader(uploaded_file)
    except Exception:
        return JsonResponse({"error": "We couldn't read that PDF - it may be corrupted."}, status=400)

    total_pages = len(reader.pages)

    # Never trust the client-side count alone - it exists purely for UX,
    # the server independently re-validates every range against the real file
    for start, end in ranges:
        if not (isinstance(start, int) and isinstance(end, int) and 1 <= start <= end <= total_pages):
            return JsonResponse({
                "error": f"Invalid range {start}-{end} for a {total_pages}-page document."
            }, status=400)

    split_files = []
    for start, end in ranges:
        writer = PdfWriter()
        for page_num in range(start - 1, end):
            writer.add_page(reader.pages[page_num])

        buffer = io.BytesIO()
        writer.write(buffer)
        split_files.append((f"pages_{start}-{end}.pdf", buffer.getvalue()))

    if len(split_files) == 1:
        filename, content = split_files[0]
        response = HttpResponse(content, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for filename, content in split_files:
            zf.writestr(filename, content)

    response = HttpResponse(zip_buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = 'attachment; filename="split_pages.zip"'
    return response


def home(request):
    return render(request, "quizmaker/home.html")


# @login_required
# def profile_view(request):
#     return render(request, 'quizmaker/profile.html')


def login_view(request):
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            return redirect("quiz:home")
    else:
        form = AuthenticationForm(request)

    return render(request, "login.html", {"form": form})


class SignUp(CreateView):
    form_class = SignupForm
    success_url = reverse_lazy("quiz:home")
    template_name = "registration/signup.html"


def dashboard_view(request):
    all_attempts = QuizAggregateMetrics.objects.all()
    # Crashes can happen at any point in the graph - attributing them to
    # one stage would be dishonest, so they're excluded from funnel/
    # self-correction math and reported separately, plainly, instead.
    funnel_base = all_attempts.exclude(end_reason__startswith="crashed_")
    total_attempts = all_attempts.count()
    total_funnel = funnel_base.count()
    crash_count = all_attempts.filter(end_reason__startswith="crashed_").count()

    # "A quiz" on this public page means one a user actually received,
    # not every generation attempt (including ones that later failed to
    # persist, or crashed). READY is the single, consistent definition
    # used everywhere this page counts quizzes.
    total_quiz_count = Quiz.objects.filter(status="READY").count()

    # --- 1. Hero strip ---------------------------------------------------
    # A quiz only counts as "approved" here if it was ALSO actually
    # delivered (status=READY) - the graph approving content and
    # persistence actually succeeding are two different things. A crash
    # between them (e.g. a field-too-long error while saving) shouldn't
    # silently count as a success in these narrative metrics.
    approved_count = funnel_base.filter(
        end_reason="approved", quiz__status="READY"
    ).count()
    approval_rate = (approved_count / total_funnel * 100) if total_funnel else 0
    avg_cost = all_attempts.aggregate(v=Avg("total_cost"))["v"] or 0
    avg_time = all_attempts.filter(total_time_seconds__isnull=False).aggregate(
        v=Avg("total_time_seconds")
    )["v"] or 0

    # --- 2. Funnel ----------------------------------------------------
    guardrail_blocked = funnel_base.filter(end_reason="guardrail_blocked").count()
    structural_failed = funnel_base.filter(end_reason="structural checks exhausted").count()
    safety_failed = funnel_base.filter(end_reason="safety check failed").count()

    passed_guardrail = total_funnel - guardrail_blocked
    passed_structural = passed_guardrail - structural_failed
    passed_safety = passed_structural - safety_failed

    funnel = [
        {"label": "Submitted", "count": total_funnel},
        {"label": "Passed Guardrail", "count": passed_guardrail},
        {"label": "Passed Structural Check", "count": passed_structural},
        {"label": "Passed Safety Check", "count": passed_safety},
        {"label": "Approved", "count": approved_count},
    ]

    # --- 3. Self-correction narrative --------------------------------------
    # Same reasoning as approved_count above - both need the quiz to have
    # actually reached the user, not just been approved by the graph.
    first_pass_count = funnel_base.filter(
        structural_attempts=1, evaluator_attempts=1,
        end_reason="approved", quiz__status="READY",
    ).count()
    self_corrected_count = funnel_base.filter(
        correction_occurred=True,
        end_reason="approved", quiz__status="READY",
    ).count()
    failed_count = total_funnel - approved_count
    designed_failed_count = failed_count

    first_pass_rate = round((first_pass_count / total_funnel * 100) if total_funnel else 0, 1)
    self_corrected_rate = round((self_corrected_count / total_funnel * 100) if total_funnel else 0, 1)
    failed_rate = round((failed_count / total_funnel * 100) if total_funnel else 0, 1)
    designed_failed_rate = round((designed_failed_count / total_funnel * 100) if total_funnel else 0, 1)

    # --- 4. Safety table ----------------------------------------------
    guardrail_categories = (
        funnel_base.exclude(guardrail_category__in=["", "passed"])
        .values("guardrail_category").annotate(count=Count("id")).order_by("-count")
    )
    safety_categories = (
        funnel_base.exclude(safety_category__in=["", "passed"])
        .values("safety_category").annotate(count=Count("id")).order_by("-count")
    )

    # --- 5. Pipeline with real per-node cost/time/tokens -----------------
    node_stats_raw = {
        row["agent"]: row
        for row in QuizNodeCost.objects.values("agent").annotate(
            avg_cost=Avg("cost"), avg_time=Avg("duration_seconds"),
            avg_input=Avg("prompt_tokens"), avg_output=Avg("completion_tokens"),
        )
    }
    pipeline_stages = []
    for agent, meta in AGENT_DISPLAY.items():
        row = node_stats_raw.get(agent)
        pipeline_stages.append({
            "agent": agent,
            "label": meta["label"],
            "icon": meta["icon"],
            "role": meta["role"],
            "desc": meta["desc"],
            "has_calls": row is not None,
            "avg_cost": round(row["avg_cost"], 4) if row and row["avg_cost"] else 0,
            "avg_time": round(row["avg_time"], 1) if row and row["avg_time"] else 0,
            "avg_input": format_tokens(row["avg_input"]) if row else "0",
            "avg_output": format_tokens(row["avg_output"]) if row else "0",
        })

    # Per-node digest pipeline stats
    # Article funnel
    total_ingested = NewsArticle.objects.filter(digest_included__isnull=False).count()
    total_included = NewsArticle.objects.filter(digest_included=True).count()
    total_excluded = NewsArticle.objects.filter(digest_included=False).count()

    digest_node_stats = []
    for node_name in ["filter", "relevance_filter", "summary", "evaluator"]:
        stats = DigestNodeCost.objects.filter(node_name=node_name).aggregate(
            avg_cost=Avg("cost"),
            avg_prompt_tokens=Avg("prompt_tokens"),
            avg_completion_tokens=Avg("completion_tokens"),
        )
        digest_node_stats.append({
            "display_name": NODE_DISPLAY_NAMES[node_name],
            "avg_cost": round(stats["avg_cost"] or 0, 4),
            "avg_prompt_tokens": round(stats["avg_prompt_tokens"] or 0),
            "avg_completion_tokens": round(stats["avg_completion_tokens"] or 0),
        })

    # Digest-level aggregate stats
    digest_summary = DigestAggregateMetrics.objects.aggregate(
        total_digests=Count("id"),
        avg_total_cost=Avg("total_cost"),
        avg_groups_approved=Avg("groups_approved"),
        avg_groups_exhausted=Avg("groups_exhausted"),
        avg_time=Avg("total_time_seconds"),
    )

    # --- 6. Quality signals ---------------------------------------------
    review_qs = QuizReview.objects.all()
    review_count = review_qs.count()
    avg_rating = review_qs.aggregate(v=Avg("rating"))["v"] or 0

    rating_counts = {r: 0 for r in range(1, 6)}
    for row in review_qs.values("rating").annotate(count=Count("id")):
        rating_counts[row["rating"]] = row["count"]
    max_rating_count = max(rating_counts.values()) if any(rating_counts.values()) else 1

    review_response_rate = round((review_count / total_quiz_count * 100) if total_quiz_count else 0, 1)

    match_counts = {"YES": 0, "SOMEWHAT": 0, "NO": 0, "NOT_APPLICABLE": 0}
    for row in review_qs.values("matched_instructions").annotate(count=Count("id")):
        key = "NOT_APPLICABLE" if row["matched_instructions"] == "N/A" else row["matched_instructions"]
        match_counts[key] = row["count"]

    flag_reasons = QuizFlag.objects.values("reason").annotate(count=Count("id")).order_by("-count")
    whole_quiz_flags = QuizFlag.objects.filter(question__isnull=True).count()
    per_question_flags = QuizFlag.objects.filter(question__isnull=False).count()
    flagged_quiz_count = QuizFlag.objects.values("quiz").distinct().count()
    flagged_quiz_rate = round((flagged_quiz_count / total_quiz_count * 100) if total_quiz_count else 0, 1)

    # --- 7. Footer counts -----------------------------------------------
    total_registrations = User.objects.count()
    total_flashcards = FlashCard.objects.count()
    avg_questions = round(Quiz.objects.filter(status="READY").aggregate(v=Avg("max_questions"))["v"] or 0, 1)
    difficulty_counts = Quiz.objects.filter(status="READY").values("difficulty").annotate(count=Count("id")).order_by(
        "difficulty")

    # Topic Brief Metrics
    topics_preview_summary = TopicsPreviewCost.objects.aggregate(
        total_briefs=Count("id"),
        avg_cost=Avg("cost"),
        avg_time=Avg("total_time_seconds"),
        avg_prompt_tokens=Avg("prompt_tokens"),
        avg_completion_tokens=Avg("completion_tokens"),
    )

    briefs = TopicsPreviewBrief.objects.all()
    total_questions_covered = sum(len(b.content) for b in briefs)
    total_questions_skipped = sum(len(b.skipped_questions) for b in briefs)

    rating_counts_briefs = TopicsPreviewBrief.objects.exclude(rating__isnull=True).values("rating").annotate(count=Count("id"))

    # --- Quiz growth: cumulative count by day, plus today's count ---------
    today = timezone.now().date()
    daily_counts = list(
        Quiz.objects.filter(status="READY").annotate(day=TruncDate("created_at"))
        .values("day").annotate(count=Count("id")).order_by("day")
    )
    today_count = Quiz.objects.filter(status="READY", created_at__date=today).count()

    growth_points = ""
    growth_fill_points = ""
    if daily_counts:
        running_total = 0
        cumulative = []
        for row in daily_counts:
            running_total += row["count"]
            cumulative.append(running_total)

        max_val = max(cumulative) or 1
        n = len(cumulative)
        chart_w, chart_h, pad = 600, 110, 10
        step = chart_w / max(n - 1, 1)

        coords = []
        for i, val in enumerate(cumulative):
            x = pad + i * step
            y = pad + chart_h - (val / max_val * chart_h)
            coords.append((round(x, 1), round(y, 1)))

        growth_points = " ".join(f"{x},{y}" for x, y in coords)
        first_x = coords[0][0]
        last_x = coords[-1][0]
        growth_fill_points = f"{growth_points} {last_x},{pad + chart_h} {first_x},{pad + chart_h}"

    context = {
        "total_quizzes": total_quiz_count,
        "approval_rate": round(approval_rate, 1),
        "avg_cost": round(avg_cost, 4),
        "avg_time": round(avg_time, 1),

        "funnel": funnel,
        "funnel_max": total_funnel or 1,

        "first_pass_rate": first_pass_rate,
        "self_corrected_rate": self_corrected_rate,
        "failed_rate": failed_rate,
        "designed_failed_rate": designed_failed_rate,
        "first_pass_count": first_pass_count,
        "self_corrected_count": self_corrected_count,
        "failed_count": failed_count,
        "crash_count": crash_count,

        "guardrail_categories": guardrail_categories,
        "safety_categories": safety_categories,

        "pipeline_stages": pipeline_stages,
        "total_attempts": total_attempts,
        "digest_summary": digest_summary,
        "total_ingested": total_ingested,
        "total_included": total_included,
        "total_excluded": total_excluded,
        "digest_node_stats": digest_node_stats,

        "review_count": review_count,
        "avg_rating": round(avg_rating, 1),
        "rating_counts": [{"stars": s, "count": rating_counts[s]} for s in range(5, 0, -1)],
        "max_rating_count": max_rating_count,
        "review_response_rate": review_response_rate,
        "match_counts": match_counts,

        "flag_reasons": flag_reasons,
        "whole_quiz_flags": whole_quiz_flags,
        "per_question_flags": per_question_flags,
        "flagged_quiz_rate": flagged_quiz_rate,

        "total_registrations": total_registrations,
        "total_flashcards": total_flashcards,
        "avg_questions": avg_questions,
        "difficulty_counts": difficulty_counts,

        "growth_points": growth_points,
        "growth_fill_points": growth_fill_points,
        "today_count": today_count,

        "topics_preview_summary": topics_preview_summary,
        "rating_counts_briefs": rating_counts_briefs,
        "total_questions_covered": total_questions_covered,
        "total_questions_skipped": total_questions_skipped,
    }

    return render(request, "quizmaker/dashboard.html", context)
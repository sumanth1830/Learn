import time
from datetime import datetime

from django.utils import timezone
from celery import shared_task

from .models import NewsArticle, DailyDigest, DigestAggregateMetrics, DigestNodeCost
from agentic_app.workflow import digest_graph

from collections import defaultdict


def _run_digest_generation(digest_date):
    if DailyDigest.objects.filter(digest_date=digest_date).exists():
        print(f"[digest {digest_date}] already exists, skipping")
        return

    articles = list(
        NewsArticle.objects.filter(published_at__date=digest_date)
        .values("id", "title", "raw_text", "source_url", "published_at", "issuing_authority")
    )

    if not articles:
        print(f"[digest {digest_date}] no articles found, skipping")
        return

    initial_state = {
        "articles": articles,
        "excluded_article_ids": [],
    }

    start_time = time.time()
    final_state = digest_graph.invoke(initial_state)
    elapsed_seconds = time.time() - start_time
    end_reason = final_state.get("end_reason", "")

    if end_reason != "approved":
        print(f"[digest {digest_date}] not approved (end_reason={end_reason!r}), no digest saved")
        return

    digest = DailyDigest.objects.create(
        digest_date=digest_date,
        content=final_state["summary_result"].content,
    )

    node_totals = defaultdict(lambda: {"prompt_tokens": 0, "completion_tokens": 0, "cost": 0, "calls": 0})

    if final_state.get("filter_usage"):
        u = final_state["filter_usage"]
        node_totals["filter"]["prompt_tokens"] += u["prompt_tokens"]
        node_totals["filter"]["completion_tokens"] += u["completion_tokens"]
        node_totals["filter"]["cost"] += u["cost"]
        node_totals["filter"]["calls"] += 1

    if final_state.get("relevance_usage"):
        u = final_state["relevance_usage"]
        node_totals["relevance_filter"]["prompt_tokens"] += u["prompt_tokens"]
        node_totals["relevance_filter"]["completion_tokens"] += u["completion_tokens"]
        node_totals["relevance_filter"]["cost"] += u["cost"]
        node_totals["relevance_filter"]["calls"] += 1

    for entry in final_state["summary_result"].all_usage_entries:
        node_totals[entry["node"]]["prompt_tokens"] += entry["prompt_tokens"]
        node_totals[entry["node"]]["completion_tokens"] += entry["completion_tokens"]
        node_totals[entry["node"]]["cost"] += entry["cost"]
        node_totals[entry["node"]]["calls"] += 1

    for node_name, totals in node_totals.items():
        DigestNodeCost.objects.create(
            digest=digest,
            node_name=node_name,
            prompt_tokens=totals["prompt_tokens"],
            completion_tokens=totals["completion_tokens"],
            cost=totals["cost"],
        )

    group_results = final_state["summary_result"].group_results
    total_cost = sum(totals["cost"] for totals in node_totals.values())

    DigestAggregateMetrics.objects.create(
        digest=digest,
        total_cost=sum(totals["cost"] for totals in node_totals.values()),
        total_calls=sum(totals["calls"] for totals in node_totals.values()),
        groups_approved=len([g for g in group_results if g.status == "APPROVED"]),
        groups_exhausted=len([g for g in group_results if g.status != "APPROVED"]),
        total_time_seconds=elapsed_seconds,
    )

    print(f"[digest {digest_date}] approved and saved, cost=${total_cost:.4f}, time={elapsed_seconds:.1f}s")


@shared_task
def generate_daily_digest_task():
    """
    Scheduled once daily, late in the day (11:30 PM IST / 18:00 UTC),
    so the day's articles have had time to accumulate before summarizing.
    """
    today = timezone.now().date()
    _run_digest_generation(today)


@shared_task
def retry_daily_digest_task(digest_date_str):
    """
    Manually invoked - e.g. from the shell - to retry a specific past
    date whose scheduled run ended in correction_limit_exhausted or was
    otherwise never approved.

    Usage:
        from quizmaker.tasks import retry_daily_digest_task
        retry_daily_digest_task.delay("2026-09-17")
    """
    digest_date = datetime.strptime(digest_date_str, "%Y-%m-%d").date()
    _run_digest_generation(digest_date)
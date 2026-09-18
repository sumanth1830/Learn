from collections import defaultdict

from quizmaker.models import NewsArticle
from ..schema import (
    DigestState,
    DigestFilterResult, DigestRelevanceResult,
    GroupSummary, GroupEvaluation, MinistryGroupResult, FinalDigestSummary
)
from ..prompts import filter_digest_prompt, relevance_filter_prompt, group_evaluation_prompt, group_summary_prompt
from ..llms import filter_digest_llm, relevance_filter_llm, group_evaluator_llm, group_summary_llm



def _extract_usage(response):
    meta = response.response_metadata.get("token_usage", {})
    return {
        "prompt_tokens": meta.get("prompt_tokens", 0),
        "completion_tokens": meta.get("completion_tokens", 0),
        "cost": meta.get("cost", 0),
    }


def filter_digest_agent(state: DigestState) -> dict:
    articles = state["articles"]
    numbered_article_titles = "\n".join(
        f"[ID: {article['id']}] {article['title']}" for article in articles
    )
    prompt = filter_digest_prompt.invoke({"numbered_article_titles": numbered_article_titles})
    filter_llm_with_structure = filter_digest_llm.with_structured_output(DigestFilterResult, include_raw=True)

    result = filter_llm_with_structure.invoke(prompt)
    filter_response = result["parsed"]
    decisions = filter_response.decisions
    excluded_ids = [article.article_id for article in decisions if article.exclude]
    return {
        "filter_result": filter_response,
        "excluded_article_ids": excluded_ids,
        "filter_usage": _extract_usage(result["raw"]),
    }


def relevance_filter_agent(state: DigestState) -> dict:
    articles = state["articles"]
    numbered_article_titles = "\n".join(
        f"[ID: {article['id']}] {article['title']}" for article in articles
    )
    prompt = relevance_filter_prompt.invoke({"numbered_article_titles": numbered_article_titles})
    relevance_llm = relevance_filter_llm.with_structured_output(DigestRelevanceResult, include_raw=True)

    result = relevance_llm.invoke(prompt)
    relevance_response = result["parsed"]
    decisions = relevance_response.decisions
    irrelevant_ids = [d.article_id for d in decisions if not d.relevant]

    existing_excluded = state.get("excluded_article_ids", [])
    combined_excluded = list(set(existing_excluded) | set(irrelevant_ids))

    return {
        "relevance_result": relevance_response,
        "excluded_article_ids": combined_excluded,
        "relevance_usage": _extract_usage(result["raw"]),
    }


def process_ministry_group(ministry, articles, max_retries=2):
    """
    Runs an independent generate -> evaluate -> retry cycle for individual
    ministry's articles. Returns the final section (or None if
    exhausted without approval), plus real usage/cost data for every
    call made, so total cost can be compared against the old
    monolithic approach.
    """
    articles_text = "\n".join(
        f"[ID: {a['id']}] {a['title']}\nText: {a['raw_text']}" for a in articles
    )

    usage_log = []
    evaluation_feedback = ""
    group_summary = None
    status = "REJECTED"

    for attempt in range(max_retries + 1):
        prompt = group_summary_prompt.invoke({
            "ministry": ministry,
            "evaluation_feedback": evaluation_feedback,
            "articles_text": articles_text,
        })
        summary_llm = group_summary_llm.with_structured_output(GroupSummary, include_raw=True)
        result = summary_llm.invoke(prompt)
        group_summary = result["parsed"]
        usage_log.append({"node": "summary", "attempt": attempt, **_extract_usage(result["raw"])})

        eval_prompt = group_evaluation_prompt.invoke({
            "content": group_summary.content,
            "articles_text": articles_text,
        })
        eval_llm = group_evaluator_llm.with_structured_output(GroupEvaluation, include_raw=True)
        eval_result = eval_llm.invoke(eval_prompt)
        eval_response = eval_result["parsed"]
        usage_log.append({"node": "evaluator", "attempt": attempt, **_extract_usage(eval_result["raw"])})

        status = eval_response.evaluation_status
        if status == "APPROVED":
            break

        evaluation_feedback = "\n".join(
            f"Article {i.article_id}: {i.note}" for i in eval_response.accuracy_issues
        )

    return {
        "ministry": ministry,
        "status": status,
        "attempts": attempt + 1,
        "section": group_summary if status == "APPROVED" else None,
        "usage_log": usage_log,
    }


def write_back_article_decisions(state):
    filter_decisions = {d.article_id: d for d in state["filter_result"].decisions}
    relevance_decisions = {d.article_id: d for d in state["relevance_result"].decisions}
    excluded_ids = set(state.get("excluded_article_ids", []))

    for article in state["articles"]:
        article_id = article["id"]
        included = article_id not in excluded_ids

        reason = ""
        if not included:
            filter_decision = filter_decisions.get(article_id)
            relevance_decision = relevance_decisions.get(article_id)
            if filter_decision and filter_decision.exclude:
                reason = filter_decision.reason
            elif relevance_decision and not relevance_decision.relevant:
                reason = relevance_decision.reason

        NewsArticle.objects.filter(id=article_id).update(
            digest_included=included,
            filter_reason=reason,
        )


def summarize_and_evaluate_agent(state: DigestState) -> dict:
    write_back_article_decisions(state)
    articles = state["articles"]
    excluded_ids = set(state.get("excluded_article_ids", []))
    survivors = [a for a in articles if a["id"] not in excluded_ids]

    groups = defaultdict(list)
    for a in survivors:
        groups[a.get("issuing_authority") or "Other"].append(a)

    group_results = []
    all_usage_entries = []
    approved_sections = []
    for ministry, group_articles in groups.items():
        result = process_ministry_group(ministry, group_articles)
        usage_totals = {
            "prompt_tokens": sum(u["prompt_tokens"] for u in result["usage_log"]),
            "completion_tokens": sum(u["completion_tokens"] for u in result["usage_log"]),
            "cost": sum(u["cost"] for u in result["usage_log"]),
        }
        group_results.append(MinistryGroupResult(
            ministry=ministry,
            status=result["status"],
            attempts=result["attempts"],
            article_count=len(group_articles),
            **usage_totals,
        ))
        all_usage_entries.extend(result["usage_log"])
        if result["status"] == "APPROVED":
            approved_sections.append((ministry, result["section"].content))

    content = "\n\n".join(f"## {m}\n\n{c}" for m, c in approved_sections)
    end_reason = "approved" if approved_sections else "no_groups_approved"

    return {
        "summary_result": FinalDigestSummary(
            content=content,
            group_results=group_results,
            all_usage_entries=all_usage_entries,
        ),
        "end_reason": end_reason,
    }
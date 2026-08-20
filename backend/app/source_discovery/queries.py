"""Groq-powered query planning for source discovery."""

from __future__ import annotations

import json
from typing import Any

from app.logging_config import get_logger
from app.services.llm import chat_completion, _extract_content
from app.services.llm_json import parse_llm_json
from app.source_discovery.constants import MAX_QUERIES_PER_ROUND, QUERY_CATEGORIES
from app.source_discovery.contracts import QueryPlanResponse, SearchQueryPlan

logger = get_logger(__name__)

_SYSTEM = (
    "You plan web search queries to find ONGOING LISTING SITES (sources) for scholarships, "
    "fellowships, and funded programs — not individual opportunity pages. "
    "Return JSON only with keys: queries (array), round_focus (string). "
    "Each query object: query, category, rationale. "
    "Categories must be exactly one of: aggregator, institutional, government_ngo, professional_association. "
    "Bias institutional and government sources over generic SEO aggregators when profile regions allow."
)

_USER_TEMPLATE = """Profile context:
{context}

Round {round_num} of up to 3. Prior round summary: {prior_summary}

Generate up to {max_queries} diverse search queries. Cover all four categories at least once when possible.
For institutional round 2+, explicitly target .edu, .gov, university department pages, and foundation portals.
Do NOT search for a single scholarship name — search for listing hubs.

JSON example:
{{"queries":[{{"query":"...","category":"institutional","rationale":"..."}}],"round_focus":"..."}}"""


def _fallback_queries(ctx: dict[str, Any], round_num: int) -> QueryPlanResponse:
    fields = ", ".join((ctx.get("target_fields") or [])[:3]) or "graduate funding"
    regions = ", ".join((ctx.get("target_regions") or [])[:3]) or "Europe"
    degree = ctx.get("target_degree") or "graduate"
    base = [
        SearchQueryPlan(
            query=f"{regions} {degree} scholarship listing database site",
            category="aggregator",
            rationale="Find aggregator listing hubs",
        ),
        SearchQueryPlan(
            query=f"university {fields} funded PhD MSc opportunities site:.edu",
            category="institutional",
            rationale="Target university department listings",
        ),
        SearchQueryPlan(
            query=f"government {regions} international student scholarship portal site:.gov",
            category="government_ngo",
            rationale="Government funding portals",
        ),
        SearchQueryPlan(
            query=f"professional association {fields} fellowship grants listing",
            category="professional_association",
            rationale="Association-maintained listings",
        ),
    ]
    if round_num >= 2:
        base.append(
            SearchQueryPlan(
                query=f"site:.edu {fields} graduate funding opportunities directory",
                category="institutional",
                rationale="Second-round institutional bias",
            )
        )
    return QueryPlanResponse(queries=base[:MAX_QUERIES_PER_ROUND], round_focus="deterministic fallback")


async def plan_search_queries(
    ctx: dict[str, Any],
    *,
    round_num: int,
    prior_summary: str = "",
) -> QueryPlanResponse:
    context_json = json.dumps(
        {
            "target_degree": ctx.get("target_degree"),
            "target_fields": ctx.get("target_fields")[:8],
            "target_regions": ctx.get("target_regions"),
            "profile_match": ctx.get("profile_match_any")[:12],
            "region_match": ctx.get("region_match_any")[:12],
        },
        ensure_ascii=False,
    )
    user = _USER_TEMPLATE.format(
        context=context_json,
        round_num=round_num,
        prior_summary=prior_summary or "none",
        max_queries=MAX_QUERIES_PER_ROUND,
    )
    messages = [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]
    try:
        result = await chat_completion(
            messages,
            max_tokens=1200,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        raw = _extract_content(result)
        data = parse_llm_json(raw)
        plan = QueryPlanResponse.model_validate(data)
    except Exception as exc:
        logger.warning("discovery_query_plan_failed", error=str(exc))
        return _fallback_queries(ctx, round_num)

    seen_cats = {q.category for q in plan.queries}
    if len(seen_cats) < 2:
        fallback = _fallback_queries(ctx, round_num)
        merged = plan.queries + [q for q in fallback.queries if q.category not in seen_cats]
        plan.queries = merged[:MAX_QUERIES_PER_ROUND]

    plan.queries = plan.queries[:MAX_QUERIES_PER_ROUND]
    return plan

"""Tier 2 search-grounded verification agent."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logging_config import get_logger
from app.models import Opportunity, OpportunitySource
from app.models.verification import VerificationStatus
from app.services.email import web_search
from app.telemetry.langsmith import traceable
from app.verification.cache import (
    get_org_domain,
    pick_canonical_domain_from_search,
    refresh_domain_legitimacy,
    save_org_domain,
)
from app.verification.compare import compare_claims, confirms_listing, has_material_conflict
from app.verification.contracts import AggregatorClaims, PrescreenResult, VerificationResult
from app.verification.domain_utils import (
    domain_matches_org,
    extract_domain,
    guess_org_name,
    is_institutional_domain,
)
from app.verification.page_intel import fetch_and_extract
from app.verification.prescreen import run_prescreen

logger = get_logger(__name__)


def _claims_from_opportunity(opp: Opportunity) -> AggregatorClaims:
    elig = " ".join(opp.requirements or [])[:800] if opp.requirements else None
    return AggregatorClaims(
        title=opp.title,
        url=opp.url,
        institution=opp.institution,
        program=opp.program,
        deadline=opp.deadline,
        funding_type=opp.funding_type,
        summary=opp.summary,
        eligibility_text=elig,
    )


def _parser_config(source: OpportunitySource | None) -> dict[str, Any]:
    if source and source.parser_config:
        return dict(source.parser_config)
    return {}


@traceable(run_type="chain", name="verification_agent", tags=["verification", "tier2"])
async def verify_opportunity_with_agent(
    session: AsyncSession,
    opportunity: Opportunity,
    source: OpportunitySource | None,
    prescreen: PrescreenResult,
) -> VerificationResult:
    claims = _claims_from_opportunity(opportunity)
    org_name = guess_org_name(claims.title, claims.institution, claims.summary)
    extract_config = _parser_config(source)

    search_queries: list[str] = []
    search_count = 0
    fetch_count = 0
    max_search = settings.verification_max_searches
    max_fetch = settings.verification_max_fetches

    # Resolve canonical domain
    canonical_domain: str | None = None
    primary_url: str | None = None

    # The listing's own domain can never confirm the listing.
    listing_domain = extract_domain(claims.url)
    exclude_domains = {listing_domain} if listing_domain else set()

    cached = await get_org_domain(session, org_name)
    if cached and cached.confidence >= 0.55:
        canonical_domain = cached.canonical_domain
        primary_url = cached.canonical_url
        search_queries.append(f"cache:org_domain:{org_name}")

    if not canonical_domain and search_count < max_search:
        q1 = f'"{org_name}" official site'
        search_queries.append(q1)
        results = await web_search(q1, max_results=5)
        search_count += 1
        canonical_domain, primary_url = pick_canonical_domain_from_search(
            org_name, results, exclude_domains=exclude_domains
        )

    if not canonical_domain and claims.program and search_count < max_search:
        q2 = f'"{org_name}" "{claims.program}" deadline'
        search_queries.append(q2)
        results = await web_search(q2, max_results=5)
        search_count += 1
        canonical_domain, primary_url = pick_canonical_domain_from_search(
            org_name, results, exclude_domains=exclude_domains
        )

    if not canonical_domain and search_count < max_search:
        q3 = f'"{claims.title}" scholarship fellowship apply'
        search_queries.append(q3)
        results = await web_search(q3, max_results=5)
        search_count += 1
        canonical_domain, primary_url = pick_canonical_domain_from_search(
            org_name, results, exclude_domains=exclude_domains
        )

    if canonical_domain:
        await save_org_domain(
            session,
            org_name,
            canonical_domain,
            canonical_url=primary_url,
            confidence=0.75 if is_institutional_domain(canonical_domain) else 0.6,
            meta={"resolved_via": "search"},
            commit=False,
        )

    # Choose fetch target: primary URL, canonical homepage, or original listing
    fetch_targets: list[str] = []
    if prescreen.action == "light_tier2" and is_institutional_domain(extract_domain(claims.url) or ""):
        fetch_targets.append(claims.url)
    if primary_url:
        fetch_targets.append(primary_url)
    if canonical_domain and not any(canonical_domain in u for u in fetch_targets):
        fetch_targets.append(f"https://{canonical_domain}/")

    primary_fields = None
    for url in fetch_targets:
        if fetch_count >= max_fetch:
            break
        if not url:
            continue
        try:
            primary_fields = await fetch_and_extract(
                url,
                org_hint=org_name,
                title_hint=claims.title,
                extract_config=extract_config,
                use_llm=True,
            )
            fetch_count += 1
            primary_url = url
            if primary_fields.deadline or primary_fields.funding_summary:
                break
        except Exception as exc:
            logger.warning("verification_fetch_failed", url=url, error=str(exc))
            fetch_count += 1

    meta: dict[str, Any] = {
        "tier2": {
            "org_name": org_name,
            "canonical_domain": canonical_domain,
            "search_count": search_count,
            "fetch_count": fetch_count,
            "search_queries": search_queries,
        },
        "prescreen": {
            "trust_score": prescreen.trust_score,
            "action": prescreen.action,
            "flags": prescreen.flags,
        },
    }

    if primary_fields is None or not (
        primary_fields.deadline or primary_fields.funding_summary or primary_fields.eligibility_summary
    ):
        return VerificationResult(
            status=VerificationStatus.aggregator_only.value,
            trust_score=prescreen.trust_score,
            prescreen=prescreen,
            primary_url=primary_url,
            search_queries=search_queries,
            meta={**meta, "reason": "no_confirming_primary_page"},
        )

    comparison = compare_claims(claims, primary_fields)
    meta["comparison"] = {
        "all_match": comparison.all_match,
        "partial_match": comparison.partial_match,
        "discrepancies": comparison.discrepancies,
        "fields": [
            {
                "field": f.field,
                "match": f.match,
                "similarity": f.similarity,
                "note": f.note,
                "comparable": f.comparable,
            }
            for f in comparison.fields
        ],
    }
    meta["primary_extraction"] = primary_fields.raw_extraction

    # Only the organization's own site can confirm or contradict a listing.
    # A third-party republisher agreeing with an aggregator proves nothing.
    primary_domain = extract_domain(primary_url or "")
    strong_primary = bool(primary_domain) and (
        is_institutional_domain(primary_domain)
        or domain_matches_org(primary_domain, org_name)
    )
    meta["primary_source"] = {
        "domain": primary_domain,
        "strong": strong_primary,
    }

    if not strong_primary:
        status = VerificationStatus.aggregator_only.value
        trust = prescreen.trust_score
        meta["reason"] = "primary_source_not_authoritative"
    elif confirms_listing(comparison):
        status = VerificationStatus.primary_confirmed.value
        trust = min(1.0, prescreen.trust_score + 0.25)
    elif has_material_conflict(comparison):
        status = VerificationStatus.stale.value
        trust = prescreen.trust_score * (0.85 if comparison.partial_match else 0.7)
    else:
        status = VerificationStatus.aggregator_only.value
        trust = prescreen.trust_score

    return VerificationResult(
        status=status,
        trust_score=round(trust, 3),
        prescreen=prescreen,
        comparison=comparison,
        primary_url=primary_url,
        search_queries=search_queries,
        meta=meta,
    )

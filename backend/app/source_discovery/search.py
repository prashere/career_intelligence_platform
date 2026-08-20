"""Tavily search and domain candidate extraction."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.registry_config import registry_by_id, normalize_source_url
from app.models import CandidateSource, CandidateSourceStatus, OpportunitySource
from app.services.email import web_search
from app.source_discovery.contracts import DomainCandidate, SearchQueryPlan
from app.source_discovery.domains import (
    normalize_registrable_domain,
    pick_best_url_for_domain,
    score_domain_candidate,
)


async def load_excluded_domains(session: AsyncSession) -> set[str]:
    excluded: set[str] = set()
    for entry in registry_by_id().values():
        url = entry.get("url")
        if url:
            dom = normalize_registrable_domain(normalize_source_url(url))
            if dom:
                excluded.add(dom)

    src_rows = await session.execute(select(OpportunitySource.url, OpportunitySource.registry_id))
    for url, _rid in src_rows.all():
        dom = normalize_registrable_domain(url or "")
        if dom:
            excluded.add(dom)

    cand_rows = await session.execute(
        select(CandidateSource.domain, CandidateSource.status)
    )
    for domain, status in cand_rows.all():
        if status in (
            CandidateSourceStatus.approved,
            CandidateSourceStatus.rejected,
            CandidateSourceStatus.pending_review,
        ):
            excluded.add(domain.lower())

    return excluded


async def search_domain_candidates(
    session: AsyncSession,
    plans: list[SearchQueryPlan],
    *,
    excluded: set[str],
    max_domains: int,
) -> list[DomainCandidate]:
    by_domain: dict[str, DomainCandidate] = {}

    for plan in plans:
        results = await web_search(plan.query, max_results=5)
        for hit in results:
            url = hit.get("url") or ""
            domain = normalize_registrable_domain(url)
            if not domain or domain in excluded:
                continue
            if domain in by_domain:
                continue
            best_url = pick_best_url_for_domain(
                url,
                hit.get("title") or "",
                hit.get("content") or hit.get("snippet") or "",
            )
            candidate = DomainCandidate(
                domain=domain,
                discovered_url=best_url,
                title=(hit.get("title") or "")[:500],
                snippet=(hit.get("content") or hit.get("snippet") or "")[:2000],
                search_query=plan.query,
                query_category=plan.category,
                pre_rank_score=score_domain_candidate(
                    domain,
                    hit.get("content") or hit.get("snippet") or "",
                    hit.get("title") or "",
                ),
            )
            by_domain[domain] = candidate

    ranked = sorted(by_domain.values(), key=lambda c: c.pre_rank_score, reverse=True)
    return ranked[:max_domains]

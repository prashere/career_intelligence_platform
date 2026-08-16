"""End-to-end ingestion pipeline orchestration.

Item admission runs in two passes. The discover pass scores an item from its
title, URL and feed snippet and returns admit / investigate / reject. Anything
that is not a confident reject gets its detail page fetched, then scored again
against the full text before it is persisted. Deferring the decision is what
stops sparse listing titles from being thrown away.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.contracts import DiscoverItem, StrategyProbeResult
from app.ingestion.dedupe import upsert_opportunity
from app.ingestion.discover.production import discover_items
from app.ingestion.discover.strategies import title_from_url_slug
from app.ingestion.envelope_store import get_platform_envelope
from app.ingestion.registry_config import registry_regions, resolve_parser_config
from app.ingestion.relevance import (
    Candidate,
    Decision,
    Verdict,
    evaluate,
    explain,
    get_relevance_config,
    profile_terms_from_envelope,
)
from app.ingestion.extract.heuristic import (
    ExtractedOpportunity,
    extract_detail,
    extract_from_feed_item,
    fetch_detail_text,
    should_fetch_detail,
)
from app.ingestion.http_client import make_client
from app.ingestion.tracing import IngestionTracer
from app.models import OpportunitySource, RawDocument
from app.models.ingestion import IngestionRun, IngestionRunStatus, RejectedItem, RejectedStage, TraceLevel
from app.services.ingestion import hash_content, hash_url

DEFAULT_INVESTIGATION_BUDGET = 40


def _parser_config(source: OpportunitySource) -> dict[str, Any]:
    return resolve_parser_config(
        parser_config=source.parser_config,
        registry_id=source.registry_id,
        source_url=source.url,
    )


def _serialize_probe(probe: StrategyProbeResult) -> dict[str, Any]:
    return {
        "kind": probe.kind,
        "ok": probe.ok,
        "item_count": probe.item_count,
        "filtered_count": probe.filtered_count,
        "error": probe.error,
        "skipped": probe.skipped,
        "skip_reason": probe.skip_reason,
        "sample_urls": probe.sample_urls,
        "requires_browser": probe.requires_browser,
    }


@dataclass
class FetchOutcome:
    """Result of fetching and extracting one item, before the admission call."""

    extracted: ExtractedOpportunity
    raw_content: str
    detail_fetched: bool


def _candidate_from_item(item: DiscoverItem, source_regions: list[str]) -> Candidate:
    title = item.title or title_from_url_slug(item.url or "")
    return Candidate(
        url=item.url or "",
        title=title,
        summary=item.summary or "",
        source_regions=source_regions,
    )


def _candidate_from_extract(
    item: DiscoverItem,
    extracted: ExtractedOpportunity,
    source_regions: list[str],
    *,
    detail_fetched: bool,
) -> Candidate:
    return Candidate(
        url=item.url or "",
        title=extracted.title or item.title or "",
        summary=item.summary or "",
        content=extracted.summary or "",
        source_regions=source_regions,
        detail_fetched=detail_fetched,
    )


def _record_rejection(
    session: AsyncSession,
    run: IngestionRun,
    source_id: str | None,
    item: DiscoverItem,
    decision: Decision,
) -> None:
    session.add(
        RejectedItem(
            run_id=run.id,
            source_id=source_id,
            stage=RejectedStage.relevance,
            reason=f"{decision.stage}:{decision.reason}"[:255],
            url=item.url,
            title=item.title[:500] if item.title else None,
            snippet=(item.summary or "")[:500],
            meta=decision.to_dict(),
        )
    )


async def run_source_ingestion(
    session: AsyncSession,
    source_id: str,
    *,
    max_items: int = 40,
    skip_browser: bool = True,
    dry_run: bool = False,
    mode: str = "production",
    investigation_budget: int | None = None,
) -> dict[str, Any]:
    source = await session.get(OpportunitySource, source_id)
    if not source or not source.is_active:
        return {"ok": False, "error": "Source not found or inactive"}

    if source.fetch_mode == "browser" and skip_browser:
        from app.ingestion.fetch.browser import playwright_available

        if not playwright_available():
            source.last_error = (
                "fetch_mode=browser — install playwright (pip install playwright && playwright install chromium)"
            )
            source.consecutive_failures = (source.consecutive_failures or 0) + 1
            await session.commit()
            return {"ok": False, "error": source.last_error, "skipped": True}

    use_browser = not skip_browser or source.fetch_mode == "browser"

    run = IngestionRun(
        source_id=source.id,
        status=IngestionRunStatus.running,
        meta={"mode": mode, "dry_run": dry_run, "max_items": max_items, "use_browser": use_browser},
    )
    session.add(run)
    await session.flush()

    tracer = IngestionTracer(
        session,
        run_id=run.id,
        source_id=source.id,
        source_name=source.name,
    )

    parser_config = _parser_config(source)
    envelope = await get_platform_envelope(session)
    profile = profile_terms_from_envelope(envelope)
    relevance_cfg = get_relevance_config()
    source_regions = registry_regions(source.registry_id)
    budget = investigation_budget if investigation_budget is not None else DEFAULT_INVESTIGATION_BUDGET

    discover_cfg = parser_config.get("discover") or {}
    timeout_ms = discover_cfg.get("request_timeout_ms") or 35000
    timeout = max(30.0, float(timeout_ms) / 1000.0)

    stats: dict[str, Any] = {
        "run_id": run.id,
        "source_id": source.id,
        "source_name": source.name,
        "mode": mode,
        "dry_run": dry_run,
        "discovered": 0,
        "prefilter_drop": 0,
        "admitted": 0,
        "investigated": 0,
        "rejected_at_discover": 0,
        "rejected_after_detail": 0,
        "fetched": 0,
        "created": 0,
        "updated": 0,
        "rejected": 0,
        "errors": 0,
        "strategy_probes": [],
    }

    await tracer.emit(
        "run",
        "run_start",
        f"Ingestion started for {source.name}",
        mode=mode,
        dry_run=dry_run,
        registry_id=source.registry_id,
        fetch_mode=source.fetch_mode,
    )

    try:
        async with tracer.stage("discover"):
            with make_client(timeout=timeout) as client:
                items, strategy, probes = await discover_items(
                    client,
                    parser_config,
                    use_browser=use_browser,
                    tracer=tracer,
                )
                stats["strategy_probes"] = [_serialize_probe(p) for p in probes]
                stats["discovered"] = len(items)
                run.discovered = len(items)
                run.meta = {
                    **(run.meta or {}),
                    "winning_strategy": strategy,
                    "strategy_probes": stats["strategy_probes"],
                }

                if not items:
                    run.status = IngestionRunStatus.partial
                    run.error_message = "No items discovered"
                    source.last_error = run.error_message if not dry_run else source.last_error
                    if not dry_run:
                        source.consecutive_failures = (source.consecutive_failures or 0) + 1
                    session.add(
                        RejectedItem(
                            run_id=run.id,
                            source_id=source.id,
                            stage=RejectedStage.discover,
                            reason="No items discovered",
                        )
                    )
                    await tracer.emit(
                        "discover",
                        "discover_empty",
                        "No items discovered after all strategies",
                        level=TraceLevel.error,
                        probes=stats["strategy_probes"],
                    )
                    _finish_run(run, source, dry_run=dry_run)
                    await session.commit()
                    return {**stats, "ok": False, "error": run.error_message}

                await tracer.emit(
                    "discover",
                    "discover_ok",
                    f"Discovered {len(items)} items via {strategy}",
                    winning_strategy=strategy,
                    count=len(items),
                )

                extract_config = parser_config.get("extract") or {}
                need_detail = should_fetch_detail(source.summary_completeness, extract_config)
                delay_s = max(0.0, (source.politeness_delay_ms or 2500) / 1000.0)

                # Pass 1: triage every discovered item from what the feed gave us.
                async with tracer.stage("triage"):
                    admitted: list[tuple[DiscoverItem, Decision]] = []
                    investigate: list[tuple[DiscoverItem, Decision]] = []

                    for item in items[:max_items]:
                        decision = evaluate(
                            _candidate_from_item(item, source_regions),
                            profile=profile,
                            config=relevance_cfg,
                            stage="discover",
                        )
                        if decision.verdict is Verdict.reject:
                            stats["rejected_at_discover"] += 1
                            _record_rejection(session, run, source.id, item, decision)
                            await tracer.item_event(
                                "triage",
                                "triage_reject",
                                explain(decision),
                                level=TraceLevel.debug,
                                url=item.url,
                                title=item.title,
                                reason=decision.reason,
                                score=round(decision.score, 3),
                            )
                        elif decision.verdict is Verdict.admit:
                            admitted.append((item, decision))
                        else:
                            investigate.append((item, decision))

                    stats["admitted"] = len(admitted)
                    stats["investigated"] = min(len(investigate), budget)

                    if len(investigate) > budget:
                        await tracer.emit(
                            "triage",
                            "investigation_budget",
                            f"Investigation budget reached, deferring {len(investigate) - budget} items",
                            level=TraceLevel.warn,
                            budget=budget,
                            pending=len(investigate),
                        )

                    await tracer.emit(
                        "triage",
                        "triage_summary",
                        f"{len(admitted)} admitted, {stats['investigated']} to investigate, "
                        f"{stats['rejected_at_discover']} rejected",
                        admitted=len(admitted),
                        investigate=stats["investigated"],
                        rejected=stats["rejected_at_discover"],
                    )

                # Pass 2: fetch, re-score with full text, then persist.
                queue = admitted + investigate[:budget]

                async with tracer.stage("process"):
                    for item, triage in queue:
                        force_detail = triage.verdict is Verdict.investigate
                        try:
                            outcome = await _fetch_item(
                                session,
                                client,
                                source,
                                item,
                                extract_config,
                                need_detail or force_detail,
                                delay_s,
                                stats,
                                tracer=tracer,
                                use_browser=use_browser,
                                dry_run=dry_run,
                            )

                            final = triage
                            if outcome.detail_fetched:
                                final = evaluate(
                                    _candidate_from_extract(
                                        item,
                                        outcome.extracted,
                                        source_regions,
                                        detail_fetched=True,
                                    ),
                                    profile=profile,
                                    config=relevance_cfg,
                                    stage="post_extract",
                                )
                                if final.verdict is Verdict.reject:
                                    stats["rejected_after_detail"] += 1
                                    _record_rejection(session, run, source.id, item, final)
                                    await tracer.item_event(
                                        "relevance",
                                        "post_extract_reject",
                                        explain(final),
                                        level=TraceLevel.debug,
                                        url=item.url,
                                        title=item.title,
                                        reason=final.reason,
                                        score=round(final.score, 3),
                                    )
                                    continue

                            if dry_run:
                                continue

                            created_flag = await _persist_item(
                                session,
                                source,
                                item,
                                outcome,
                                run,
                            )
                            if created_flag is True:
                                stats["created"] += 1
                                await tracer.item_event(
                                    "store",
                                    "opportunity_created",
                                    f"Created opportunity ({final.verdict.value}, score {final.score:.2f})",
                                    level=TraceLevel.info,
                                    url=item.url,
                                    title=item.title,
                                    score=round(final.score, 3),
                                )
                            elif created_flag is False:
                                stats["updated"] += 1
                                await tracer.item_event(
                                    "store",
                                    "opportunity_updated",
                                    "Updated opportunity",
                                    level=TraceLevel.info,
                                    url=item.url,
                                    title=item.title,
                                )
                        except Exception as exc:
                            stats["errors"] += 1
                            err = f"{type(exc).__name__}: {exc}"[:255]
                            session.add(
                                RejectedItem(
                                    run_id=run.id,
                                    source_id=source.id,
                                    stage=RejectedStage.extract,
                                    reason=err,
                                    url=item.url,
                                    title=item.title[:500] if item.title else None,
                                    meta={"triage": triage.to_dict()},
                                )
                            )
                            await tracer.item_event(
                                "extract",
                                "extract_error",
                                err,
                                level=TraceLevel.error,
                                url=item.url,
                                title=item.title,
                            )

            stats["prefilter_drop"] = stats["rejected_at_discover"] + stats["rejected_after_detail"]
            stats["rejected"] = stats["prefilter_drop"]

            run.discovered = stats["discovered"]
            run.prefilter_drop = stats["prefilter_drop"]
            run.fetched = stats["fetched"]
            run.created = stats["created"]
            run.updated = stats["updated"]
            run.rejected = stats["rejected"]
            run.errors = stats["errors"]
            run.meta = {
                **(run.meta or {}),
                "relevance": {
                    "admitted": stats["admitted"],
                    "investigated": stats["investigated"],
                    "rejected_at_discover": stats["rejected_at_discover"],
                    "rejected_after_detail": stats["rejected_after_detail"],
                },
            }
            run.status = (
                IngestionRunStatus.failed
                if stats["errors"] and not stats["created"] and not stats["updated"]
                else IngestionRunStatus.partial
                if stats["errors"]
                else IngestionRunStatus.completed
            )
            if not dry_run:
                source.last_fetched_at = datetime.now(timezone.utc)
                source.last_error = None
                source.consecutive_failures = 0
            _finish_run(run, source, dry_run=dry_run)
            await tracer.emit(
                "run",
                "run_complete",
                f"Ingestion finished: +{stats['created']} new, {stats['updated']} updated",
                status=run.status.value,
                **{
                    k: stats[k]
                    for k in (
                        "discovered",
                        "admitted",
                        "investigated",
                        "rejected_at_discover",
                        "rejected_after_detail",
                        "created",
                        "updated",
                        "errors",
                    )
                },
            )
            await session.commit()
            return {**stats, "ok": True}

    except Exception as exc:
        run.status = IngestionRunStatus.failed
        run.error_message = str(exc)
        run.errors += 1
        stats["errors"] += 1
        if not dry_run:
            source.last_error = str(exc)
            source.consecutive_failures = (source.consecutive_failures or 0) + 1
        await tracer.emit("run", "run_failed", str(exc), level=TraceLevel.error)
        _finish_run(run, source, dry_run=dry_run)
        await session.commit()
        return {**stats, "ok": False, "error": str(exc)}


async def _fetch_item(
    session: AsyncSession,
    client: httpx.Client,
    source: OpportunitySource,
    item: DiscoverItem,
    extract_config: dict[str, Any],
    need_detail: bool,
    delay_s: float,
    stats: dict[str, Any],
    *,
    tracer: IngestionTracer,
    use_browser: bool = False,
    dry_run: bool = False,
) -> FetchOutcome:
    """Fetch the detail page when required and extract structured fields."""
    extracted = extract_from_feed_item(item.title, item.summary, extract_config)
    raw_content = item.summary or item.title
    detail_fetched = False

    if need_detail and item.url:
        await asyncio.sleep(delay_s)
        extract_mode = extract_config.get("fetch_mode_override") or source.fetch_mode or "http"
        use_browser_fetch = extract_mode == "browser" and use_browser

        if use_browser_fetch:
            from app.ingestion.fetch.browser import fetch_page

            stats["fetched"] += 1
            _, _, raw_content = fetch_page(item.url, timeout_ms=int(delay_s * 1000) + 40000)
            detail_fetched = True
        else:
            headers: dict[str, str] = {}
            if source.etag:
                headers["If-None-Match"] = source.etag
            if source.last_modified:
                headers["If-Modified-Since"] = source.last_modified

            if extract_config.get("proxy_prefix") or extract_config.get("content_format") == "jina_markdown":
                raw_content = fetch_detail_text(client, item.url, extract_config, headers=headers)
                detail_fetched = True
            else:
                response = client.get(item.url, headers=headers)
                stats["fetched"] += 1

                if response.status_code == 304:
                    raw_content = item.summary or item.title
                else:
                    response.raise_for_status()
                    if not dry_run:
                        source.etag = response.headers.get("etag") or source.etag
                        source.last_modified = response.headers.get("last-modified") or source.last_modified
                    raw_content = response.text
                    detail_fetched = True

            if extract_config.get("proxy_prefix") or extract_config.get("content_format") == "jina_markdown":
                stats["fetched"] += 1

        await tracer.item_event(
            "extract",
            "detail_fetch",
            f"Fetched detail ({len(raw_content)} chars)",
            url=item.url,
            title=item.title,
            http_status=200,
        )

        if detail_fetched:
            extracted = extract_detail(
                raw_content,
                item.url,
                extract_config,
                fallback_title=item.title or title_from_url_slug(item.url or ""),
                fallback_summary=item.summary,
            )
    elif item.url:
        stats["fetched"] += 1

    return FetchOutcome(extracted=extracted, raw_content=raw_content, detail_fetched=detail_fetched)


async def _persist_item(
    session: AsyncSession,
    source: OpportunitySource,
    item: DiscoverItem,
    outcome: FetchOutcome,
    run: IngestionRun,
) -> Optional[bool]:
    """Store the raw document and upsert the opportunity. True if created."""
    detail_doc_id: Optional[str] = None

    if item.url:
        url_h = hash_url(item.url)
        content_h = hash_content(outcome.raw_content)
        fetch_kind = "detail" if outcome.detail_fetched else "index"

        existing_doc = await session.execute(
            select(RawDocument).where(
                RawDocument.url_hash == url_h,
                RawDocument.content_hash == content_h,
            )
        )
        doc = existing_doc.scalar_one_or_none()
        if doc is None:
            doc = RawDocument(
                source_id=source.id,
                url=item.url,
                url_hash=url_h,
                title=item.title[:500] if item.title else None,
                summary=item.summary,
                fetch_kind=fetch_kind,
                http_status=200 if outcome.detail_fetched else None,
                content_type="text/html" if outcome.detail_fetched else None,
                raw_content=outcome.raw_content,
                content_hash=content_h,
                processed=True,
            )
            session.add(doc)
            await session.flush()
        detail_doc_id = doc.id

    _, created = await upsert_opportunity(
        session,
        source,
        item.url,
        outcome.extracted,
        detail_doc_id,
        outcome.raw_content,
    )
    return created


def _finish_run(run: IngestionRun, source: OpportunitySource, *, dry_run: bool = False) -> None:
    run.finished_at = datetime.now(timezone.utc)
    interval = source.fetch_interval_minutes or 360
    run.meta = {
        **(run.meta or {}),
        "duration_s": (run.finished_at - run.started_at).total_seconds(),
    }
    if not dry_run:
        source.next_fetch_at = run.finished_at + timedelta(minutes=interval)


async def run_all_active_sources(session: AsyncSession, **kwargs: Any) -> list[dict[str, Any]]:
    result = await session.execute(
        select(OpportunitySource).where(OpportunitySource.is_active.is_(True))
    )
    sources = result.scalars().all()
    outcomes = []
    for source in sources:
        outcomes.append(await run_source_ingestion(session, source.id, **kwargs))
    return outcomes

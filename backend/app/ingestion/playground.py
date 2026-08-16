"""Admin playground — experiment with ingestors without affecting production catalog."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.contracts import DiscoverItem
from app.ingestion.discover.production import discover_items
from app.ingestion.envelope_store import get_platform_envelope
from app.ingestion.extract.heuristic import extract_detail, fetch_detail_text
from app.ingestion.discover.strategies import title_from_url_slug
from app.ingestion.http_client import make_client
from app.ingestion.pipeline import _parser_config, _serialize_probe, run_source_ingestion
from app.ingestion.registry_config import (
    get_registry_entry,
    merge_registry_fields,
    normalize_source_url,
    registry_by_id,
    registry_regions,
)
from app.ingestion.relevance import (
    Candidate,
    Decision,
    Verdict,
    evaluate,
    explain,
    get_relevance_config,
    profile_terms_from_envelope,
)
from app.ingestion.tracing import IngestionTracer
from app.models import OpportunitySource
from app.models.ingestion import IngestionRun, IngestionRunStatus, RejectedItem, RejectedStage, TraceLevel

# Detail fetches in the lab are interactive, so keep them bounded and quick.
RESOLVE_LIMIT = 10
RESOLVE_TIMEOUT = 20.0
RESOLVE_DELAY_S = 0.4


def _preview_row(item: DiscoverItem, decision: Decision, *, resolved: bool = False) -> dict[str, Any]:
    payload = decision.to_dict()
    return {
        "url": item.url,
        "title": item.title,
        "summary": (item.summary or "")[:300],
        "resolved": resolved,
        # Retained so previously stored runs and older clients keep rendering.
        "prefilter_pass": decision.ok,
        "prefilter_reason": None if decision.ok else decision.reason,
        **payload,
    }


async def _resolve_item(
    client: httpx.Client,
    item: DiscoverItem,
    extract_config: dict[str, Any],
    *,
    profile,
    config,
    source_regions: list[str],
) -> Decision:
    """Fetch the detail page and re-score with the full text."""
    raw_content = fetch_detail_text(client, item.url or "", extract_config)
    extracted = extract_detail(
        raw_content,
        item.url,
        extract_config,
        fallback_title=item.title or title_from_url_slug(item.url or ""),
        fallback_summary=item.summary,
    )
    return evaluate(
        Candidate(
            url=item.url or "",
            title=extracted.title or item.title or "",
            summary=item.summary or "",
            content=extracted.summary or "",
            source_regions=source_regions,
            detail_fetched=True,
        ),
        profile=profile,
        config=config,
        stage="post_extract",
    )


async def run_playground(
    session: AsyncSession,
    *,
    source_id: str | None = None,
    registry_id: str | None = None,
    mode: str = "discover",
    max_items: int = 15,
    include_browser: bool = False,
    resolve_investigate: bool = False,
) -> dict[str, Any]:
    """
    Modes:
      discover — discover + relevance triage preview only (no persistence)
      dry_run  — full pipeline without persisting opportunities/raw docs
      persist  — full pipeline with persistence (same as production fetch)

    With resolve_investigate, items the gate is unsure about get their detail
    page fetched and re-scored, so the preview shows the same verdict the
    production pipeline would reach.
    """
    source: OpportunitySource | None = None
    if source_id:
        source = await session.get(OpportunitySource, source_id)
        if not source:
            return {"ok": False, "error": "Source not found"}

    if mode in ("dry_run", "persist") and source:
        return await run_source_ingestion(
            session,
            source.id,
            max_items=max_items,
            skip_browser=not include_browser,
            dry_run=(mode == "dry_run"),
            mode=f"playground:{mode}",
        )

    # discover-only (or registry_id without DB source)
    entry: dict[str, Any] | None = None
    if source:
        entry = {
            "id": source.registry_id,
            "name": source.name,
            "url": source.url,
            "parser_config": source.parser_config,
            "fetch_mode": source.fetch_mode,
        }
    elif registry_id:
        entry = get_registry_entry(registry_id)
        if not entry:
            return {"ok": False, "error": f"Registry entry not found: {registry_id}"}

    if not entry:
        return {"ok": False, "error": "Provide source_id or registry_id"}

    enriched = merge_registry_fields(entry)
    parser_config = _parser_config(source) if source else enriched.get("parser_config") or {}
    if not source:
        from app.ingestion.registry_config import resolve_parser_config

        parser_config = resolve_parser_config(
            parser_config=parser_config,
            registry_id=registry_id,
            source_url=enriched.get("url"),
        )

    effective_registry_id = enriched.get("id") or registry_id or (source.registry_id if source else None)

    run = IngestionRun(
        source_id=source.id if source else None,
        status=IngestionRunStatus.running,
        meta={
            "mode": "playground:discover",
            "registry_id": effective_registry_id,
            "max_items": max_items,
            "use_browser": include_browser,
            "resolve_investigate": resolve_investigate,
        },
    )
    session.add(run)
    await session.flush()

    tracer = IngestionTracer(
        session,
        run_id=run.id,
        source_id=source.id if source else None,
        source_name=enriched.get("name"),
    )

    discover_cfg = parser_config.get("discover") or {}
    timeout_ms = discover_cfg.get("request_timeout_ms") or 35000
    timeout = max(30.0, float(timeout_ms) / 1000.0)

    envelope = await get_platform_envelope(session)
    profile = profile_terms_from_envelope(envelope)
    relevance_cfg = get_relevance_config()
    source_regions = registry_regions(effective_registry_id)
    extract_config = parser_config.get("extract") or {}

    await tracer.emit(
        "run",
        "playground_start",
        f"Playground discover for {enriched.get('name')}",
        mode="discover",
        registry_id=effective_registry_id,
    )

    try:
        async with tracer.stage("discover"):
            with make_client(timeout=timeout) as client:
                items, strategy, probes = await discover_items(
                    client,
                    parser_config,
                    use_browser=include_browser,
                    tracer=tracer,
                )

        run.discovered = len(items)

        preview: list[dict[str, Any]] = []
        counts = {"admit": 0, "investigate": 0, "reject": 0}
        pending: list[tuple[int, DiscoverItem]] = []

        async with tracer.stage("triage"):
            for item in items[:max_items]:
                decision = evaluate(
                    Candidate(
                        url=item.url or "",
                        title=item.title or title_from_url_slug(item.url or ""),
                        summary=item.summary or "",
                        source_regions=source_regions,
                    ),
                    profile=profile,
                    config=relevance_cfg,
                    stage="discover",
                )
                counts[decision.verdict.value] += 1
                preview.append(_preview_row(item, decision))
                if decision.verdict is Verdict.investigate:
                    pending.append((len(preview) - 1, item))

                await tracer.item_event(
                    "triage",
                    f"triage_{decision.verdict.value}",
                    explain(decision),
                    level=TraceLevel.debug if decision.ok else TraceLevel.info,
                    url=item.url,
                    title=item.title,
                    reason=decision.reason,
                    score=round(decision.score, 3),
                )

        resolved_count = 0
        resolve_errors = 0
        if resolve_investigate and pending:
            async with tracer.stage("resolve"):
                with make_client(timeout=RESOLVE_TIMEOUT) as client:
                    for index, item in pending[:RESOLVE_LIMIT]:
                        if not item.url:
                            continue
                        try:
                            await asyncio.sleep(RESOLVE_DELAY_S)
                            final = await _resolve_item(
                                client,
                                item,
                                extract_config,
                                profile=profile,
                                config=relevance_cfg,
                                source_regions=source_regions,
                            )
                        except Exception as exc:
                            resolve_errors += 1
                            preview[index]["resolve_error"] = f"{type(exc).__name__}: {exc}"[:200]
                            await tracer.item_event(
                                "resolve",
                                "resolve_error",
                                f"{type(exc).__name__}: {exc}"[:200],
                                level=TraceLevel.warn,
                                url=item.url,
                                title=item.title,
                            )
                            continue

                        resolved_count += 1
                        counts["investigate"] -= 1
                        counts[final.verdict.value] += 1
                        preview[index] = _preview_row(item, final, resolved=True)
                        await tracer.item_event(
                            "resolve",
                            f"resolved_{final.verdict.value}",
                            explain(final),
                            level=TraceLevel.info,
                            url=item.url,
                            title=item.title,
                            reason=final.reason,
                            score=round(final.score, 3),
                        )

        rejected_rows = [row for row in preview if row.get("verdict") == Verdict.reject.value]
        for row in rejected_rows:
            session.add(
                RejectedItem(
                    run_id=run.id,
                    source_id=source.id if source else None,
                    stage=RejectedStage.relevance,
                    reason=f"{row.get('stage')}:{row.get('reason')}"[:255],
                    url=row.get("url"),
                    title=(row.get("title") or "")[:500] or None,
                    snippet=(row.get("summary") or "")[:500],
                    meta={k: v for k, v in row.items() if k not in ("summary",)},
                )
            )

        run.meta = {
            **(run.meta or {}),
            "winning_strategy": strategy,
            "strategy_probes": [_serialize_probe(p) for p in probes],
            "preview_items": preview,
            "relevance": {
                **counts,
                "resolved": resolved_count,
                "resolve_errors": resolve_errors,
            },
        }

        run.prefilter_drop = counts["reject"]
        run.rejected = counts["reject"]
        run.status = IngestionRunStatus.completed if items else IngestionRunStatus.partial
        if not items:
            run.error_message = "No items discovered"
            session.add(
                RejectedItem(
                    run_id=run.id,
                    source_id=source.id if source else None,
                    stage=RejectedStage.discover,
                    reason="No items discovered",
                )
            )

        run.finished_at = datetime.now(timezone.utc)
        run.meta["duration_s"] = (run.finished_at - run.started_at).total_seconds()

        await tracer.emit(
            "run",
            "playground_complete",
            f"Preview ready: {len(items)} discovered, {counts['admit']} admit, "
            f"{counts['investigate']} investigate, {counts['reject']} reject",
            discovered=len(items),
            **counts,
        )
        await session.commit()

        return {
            "ok": bool(items),
            "run_id": run.id,
            "mode": "discover",
            "source_name": enriched.get("name"),
            "registry_id": effective_registry_id,
            "discovered": len(items),
            "prefilter_drop": counts["reject"],
            "admit": counts["admit"],
            "investigate": counts["investigate"],
            "reject": counts["reject"],
            "resolved": resolved_count,
            "winning_strategy": strategy,
            "strategy_probes": [_serialize_probe(p) for p in probes],
            "preview_items": preview,
            "error": run.error_message,
        }
    except Exception as exc:
        run.status = IngestionRunStatus.failed
        run.error_message = str(exc)
        run.finished_at = datetime.now(timezone.utc)
        await tracer.emit("run", "playground_failed", str(exc), level=TraceLevel.error)
        await session.commit()
        return {"ok": False, "run_id": run.id, "error": str(exc)}


def list_registry_aggregators() -> list[dict[str, Any]]:
    entries = [
        {
            "id": entry["id"],
            "name": entry["name"],
            "url": normalize_source_url(entry.get("url")) or None,
            "type": entry.get("type"),
            "fetch_mode": entry.get("fetch_mode"),
            "default_active": entry.get("default_active", True),
            "discover_kind": ((entry.get("parser_config") or {}).get("discover") or {}).get("kind"),
        }
        for entry in registry_by_id().values()
    ]
    return sorted(entries, key=lambda row: row["name"].lower())

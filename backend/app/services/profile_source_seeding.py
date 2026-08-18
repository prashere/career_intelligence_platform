"""Seed opportunity_sources from compiled ingestion_sources.json."""

from typing import Any

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.registry_config import merge_registry_fields, normalize_source_url
from app.models import OpportunitySource, SourceType
from app.services.profile_intake import compiled_dir
from app.services.profile_pipeline import load_source_registry


def _selection_keys(sources: list[dict[str, Any]]) -> tuple[set[str], set[str]]:
    """Registry ids and normalized URLs for profile-selected aggregators."""
    registry_ids: set[str] = set()
    urls: set[str] = set()
    for raw_entry in sources:
        entry = merge_registry_fields(raw_entry)
        rid = entry.get("id") or entry.get("registry_id")
        if rid:
            registry_ids.add(str(rid))
        url = entry.get("url")
        if url:
            urls.add(normalize_source_url(url))
    return registry_ids, urls


def _source_matches_selection(
    source: OpportunitySource,
    registry_ids: set[str],
    urls: set[str],
) -> bool:
    if source.registry_id and source.registry_id in registry_ids:
        return True
    return normalize_source_url(source.url) in urls


def _registry_catalog_ids() -> set[str]:
    registry = load_source_registry()
    return {str(e["id"]) for e in registry.get("aggregators", []) if e.get("id")}


async def _find_source_row(
    session: AsyncSession,
    entry: dict[str, Any],
    normalized_url: str,
) -> OpportunitySource | None:
    rid = entry.get("id") or entry.get("registry_id")
    if rid:
        by_id = await session.execute(
            select(OpportunitySource).where(OpportunitySource.registry_id == rid)
        )
        row = by_id.scalar_one_or_none()
        if row:
            return row
    by_url = await session.execute(
        select(OpportunitySource).where(OpportunitySource.url == normalized_url)
    )
    return by_url.scalar_one_or_none()


async def seed_sources_from_data(
    session: AsyncSession,
    data: dict[str, Any],
    *,
    commit: bool = True,
) -> tuple[int, int]:
    """Upsert opportunity_sources from ingestion_sources artifact dict.

    Only registry-catalog sources are deactivated when not in the profile selection.
    Legacy rows without registry_id are deactivated only when their URL is not selected.
    """
    sources = data.get("sources") or []
    registry_ids, selected_urls = _selection_keys(sources)
    catalog_ids = _registry_catalog_ids()

    added = 0
    updated = 0
    for raw_entry in sources:
        entry = merge_registry_fields(raw_entry)
        normalized_url = normalize_source_url(entry["url"])
        existing = await _find_source_row(session, entry, normalized_url)
        try:
            source_type = SourceType(entry.get("source_type", "rss"))
        except ValueError:
            source_type = SourceType.rss

        if existing:
            existing.name = entry["name"]
            existing.url = normalized_url
            existing.source_type = source_type
            existing.fetch_interval_minutes = entry.get("fetch_interval_minutes", 360)
            existing.is_active = entry.get("is_active", True)
            existing.registry_id = entry.get("id") or entry.get("registry_id") or existing.registry_id
            existing.adapter_id = entry.get("adapter_id") or existing.adapter_id
            existing.fetch_mode = entry.get("fetch_mode") or existing.fetch_mode or "http"
            existing.summary_completeness = (
                entry.get("summary_completeness") or existing.summary_completeness or "snippet_only"
            )
            existing.authority = float(entry.get("authority") or existing.authority or 0.5)
            existing.politeness_delay_ms = int(
                entry.get("politeness_delay_ms") or existing.politeness_delay_ms or 2500
            )
            existing.parser_config = {
                **(existing.parser_config or {}),
                **(entry.get("parser_config") or {}),
            }
            updated += 1
        else:
            parser_config = dict(entry.get("parser_config") or {})
            session.add(
                OpportunitySource(
                    name=entry["name"],
                    url=normalized_url,
                    source_type=source_type,
                    fetch_interval_minutes=entry.get("fetch_interval_minutes", 360),
                    is_active=entry.get("is_active", True),
                    registry_id=entry.get("id") or entry.get("registry_id"),
                    adapter_id=entry.get("adapter_id"),
                    fetch_mode=entry.get("fetch_mode") or "http",
                    summary_completeness=entry.get("summary_completeness") or "snippet_only",
                    authority=float(entry.get("authority") or 0.5),
                    politeness_delay_ms=int(entry.get("politeness_delay_ms") or 2500),
                    parser_config=parser_config,
                )
            )
            added += 1

    all_result = await session.execute(select(OpportunitySource))
    for row in all_result.scalars().all():
        if _source_matches_selection(row, registry_ids, selected_urls):
            continue
        if row.registry_id and row.registry_id in catalog_ids:
            row.is_active = False
        elif not row.registry_id and normalize_source_url(row.url) not in selected_urls:
            row.is_active = False

    if commit:
        await session.commit()
    else:
        await session.flush()
    return added, updated


async def load_profile_ingest_sources(
    session: AsyncSession,
    user_id: str,
) -> list[OpportunitySource]:
    """Active opportunity_sources that match the user's compiled ingestion selection."""
    from app.services.profile_storage import load_ingestion_sources

    ingestion_data = await load_ingestion_sources(session, user_id)
    selected = ingestion_data.get("sources") or []
    if not selected:
        return []

    registry_ids, selected_urls = _selection_keys(selected)
    active_result = await session.execute(
        select(OpportunitySource).where(OpportunitySource.is_active.is_(True))
    )
    return [
        s for s in active_result.scalars().all()
        if _source_matches_selection(s, registry_ids, selected_urls)
    ]


async def seed_sources_from_compiled(
    session: AsyncSession,
    path: Path | None = None,
) -> tuple[int, int]:
    """CLI fallback — read ingestion_sources.json from disk."""
    file_path = path or (compiled_dir() / "ingestion_sources.json")
    if not file_path.exists():
        raise FileNotFoundError(f"{file_path} not found — run compile_profile first")
    data = json.loads(file_path.read_text(encoding="utf-8"))
    return await seed_sources_from_data(session, data)

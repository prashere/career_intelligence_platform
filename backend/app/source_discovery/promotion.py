"""Promote approved candidate sources to YAML, DB, and profile artifacts."""

from __future__ import annotations

import copy
import os
import re
import tempfile
from datetime import datetime, timezone
from typing import Any

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.registry_config import merge_registry_fields, normalize_source_url, registry_by_id
from app.models.ingestion import CandidateSource, CandidateSourceStatus
from app.services.profile_source_seeding import seed_sources_from_data
from app.services.profile_storage import load_artifacts
from app.source_registry_paths import SOURCE_REGISTRY_PATH
from app.source_discovery.contracts import SourceApprovalPayload

_REGISTRY_LOCK = SOURCE_REGISTRY_PATH.with_suffix(".lock")
_promotion_lock = __import__("threading").Lock()


def _slug_registry_id(name: str, domain: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", (name or domain).lower()).strip("_")
    return base[:48] or "discovered_source"


def _validate_registry_entry(entry: dict[str, Any]) -> None:
    required = ("id", "name", "url", "type", "parser_config")
    for key in required:
        if not entry.get(key):
            raise ValueError(f"Registry entry missing {key}")
    discover = (entry.get("parser_config") or {}).get("discover") or {}
    if not discover.get("feed_urls") and not discover.get("entry_urls") and not discover.get("strategies"):
        raise ValueError("parser_config.discover must define feed_urls, entry_urls, or strategies")


def _append_registry_entry(entry: dict[str, Any]) -> None:
    _validate_registry_entry(entry)
    SOURCE_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)

    with _promotion_lock:
        backup = None
        try:
            if SOURCE_REGISTRY_PATH.exists():
                backup = SOURCE_REGISTRY_PATH.read_text(encoding="utf-8")
                data = yaml.safe_load(backup) or {}
            else:
                data = {"schema_version": "1.2", "aggregators": []}

            aggregators = data.get("aggregators") or []
            ids = {a.get("id") for a in aggregators}
            if entry["id"] in ids:
                raise ValueError(f"Registry id already exists: {entry['id']}")
            aggregators.append(entry)
            data["aggregators"] = aggregators

            fd, tmp_path = tempfile.mkstemp(
                suffix=".yaml",
                dir=str(SOURCE_REGISTRY_PATH.parent),
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as tmp:
                    yaml.safe_dump(data, tmp, sort_keys=False, allow_unicode=True)
                os.replace(tmp_path, SOURCE_REGISTRY_PATH)
            except Exception:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise

            registry_by_id.cache_clear()
        except Exception:
            if backup is not None:
                SOURCE_REGISTRY_PATH.write_text(backup, encoding="utf-8")
                registry_by_id.cache_clear()
            raise


def _build_registry_entry(payload: SourceApprovalPayload) -> dict[str, Any]:
    url = normalize_source_url(payload.url)
    entry: dict[str, Any] = {
        "id": payload.registry_id,
        "name": payload.name,
        "url": url,
        "type": payload.source_type,
        "regions": payload.regions or ["global"],
        "tags": payload.tags or ["scholarship"],
        "degree_levels": payload.degree_levels or ["Mixed"],
        "funding_signal": "medium",
        "fetch_interval_minutes": payload.fetch_interval_minutes,
        "chip_label": payload.name[:32],
        "confidence": "proposed",
        "adapter_id": payload.adapter_id,
        "summary_completeness": payload.summary_completeness,
        "authority": payload.authority,
        "politeness_delay_ms": payload.politeness_delay_ms,
        "fetch_mode": payload.fetch_mode,
        "parser_config": payload.parser_config,
        "notes": "Added via source discovery review",
    }
    return entry


def _build_seed_source(entry: dict[str, Any]) -> dict[str, Any]:
    merged = merge_registry_fields(entry)
    return {
        "id": merged["id"],
        "name": merged["name"],
        "url": normalize_source_url(merged["url"]),
        "source_type": merged.get("type", "rss"),
        "fetch_interval_minutes": merged.get("fetch_interval_minutes", 360),
        "is_active": True,
        "selection_reason": "source discovery approval",
        "adapter_id": merged.get("adapter_id"),
        "summary_completeness": merged.get("summary_completeness", "snippet_only"),
        "authority": merged.get("authority", 0.5),
        "politeness_delay_ms": merged.get("politeness_delay_ms", 2500),
        "fetch_mode": merged.get("fetch_mode", "http"),
        "parser_config": merged.get("parser_config") or {},
    }


async def promote_candidate_source(
    session: AsyncSession,
    candidate: CandidateSource,
    payload: SourceApprovalPayload,
    user_id: str,
) -> dict[str, Any]:
    if candidate.status == CandidateSourceStatus.approved:
        raise ValueError("Candidate already approved")
    if candidate.status == CandidateSourceStatus.rejected:
        raise ValueError("Rejected candidates cannot be approved")

    registry_id = payload.registry_id or _slug_registry_id(payload.name, candidate.domain)
    payload.registry_id = registry_id

    entry = _build_registry_entry(payload)
    seed_source = _build_seed_source(entry)

    # 1) YAML (with rollback on DB failure)
    _append_registry_entry(entry)

    try:
        artifacts = await load_artifacts(session, user_id)
        ingestion = copy.deepcopy(artifacts.ingestion_sources or {}) if artifacts else {}
        sources = list(ingestion.get("sources") or [])
        if not any(s.get("id") == registry_id for s in sources):
            sources.append(seed_source)
        ingestion["sources"] = sources
        ingestion.setdefault("schema_version", "1.0")
        ingestion["compiled_at"] = datetime.now(timezone.utc).isoformat()

        if artifacts:
            artifacts.ingestion_sources = ingestion

        await seed_sources_from_data(
            session,
            {"sources": sources},
            commit=False,
        )

        candidate.status = CandidateSourceStatus.approved
        candidate.reviewed_at = datetime.now(timezone.utc)
        candidate.guessed_parser_config = payload.parser_config

        await session.commit()
    except Exception:
        await session.rollback()
        raise

    return {
        "registry_id": registry_id,
        "name": payload.name,
        "url": seed_source["url"],
    }

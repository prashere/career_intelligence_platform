"""Resolve ingestion parser config from the git-tracked source registry."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from app.source_registry_paths import SOURCE_REGISTRY_PATH


@lru_cache(maxsize=1)
def registry_by_id() -> dict[str, dict[str, Any]]:
    if not SOURCE_REGISTRY_PATH.exists():
        return {}
    data = yaml.safe_load(SOURCE_REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    return {entry["id"]: entry for entry in data.get("aggregators") or [] if entry.get("id")}


def get_registry_entry(registry_id: str | None) -> dict[str, Any] | None:
    if not registry_id:
        return None
    return registry_by_id().get(registry_id)


def normalize_source_url(url: Any) -> str:
    """Registry entries may use a string URL or a one-item list."""
    if isinstance(url, list):
        return str(url[0]) if url else ""
    return str(url or "")


def registry_regions(registry_id: str | None) -> list[str]:
    """Regions the aggregator itself declares.

    Listing titles rarely name a country, so the source's own region metadata is
    usually the only region evidence available at discover time.
    """
    entry = get_registry_entry(registry_id) or {}
    regions = entry.get("regions") or []
    if isinstance(regions, str):
        return [regions]
    return [str(r) for r in regions if r]


def registry_tags(registry_id: str | None) -> list[str]:
    entry = get_registry_entry(registry_id) or {}
    tags = entry.get("tags") or []
    if isinstance(tags, str):
        return [tags]
    return [str(t) for t in tags if t]


def merge_registry_fields(entry: dict[str, Any]) -> dict[str, Any]:
    """Enrich a seed/JSON source entry with registry metadata when missing."""
    registry_id = entry.get("id") or entry.get("registry_id")
    reg = get_registry_entry(registry_id)
    if not reg:
        return entry

    out = dict(entry)
    for key in (
        "adapter_id",
        "fetch_mode",
        "summary_completeness",
        "authority",
        "politeness_delay_ms",
    ):
        if out.get(key) in (None, ""):
            if reg.get(key) is not None:
                out[key] = reg[key]

    reg_pc = reg.get("parser_config") or {}
    out_pc = dict(out.get("parser_config") or {})
    if not out_pc.get("discover") and reg_pc.get("discover"):
        out["parser_config"] = {**reg_pc, **out_pc}
    elif not out_pc:
        out["parser_config"] = reg_pc
    else:
        out["parser_config"] = out_pc

    return out


def resolve_parser_config(
    *,
    parser_config: dict[str, Any] | None,
    registry_id: str | None,
    source_url: str | None,
) -> dict[str, Any]:
    """Return effective parser_config for pipeline discover/extract."""
    pc = dict(parser_config or {})
    discover = pc.get("discover") or {}

    if not discover.get("feed_urls") and not discover.get("strategies"):
        reg = get_registry_entry(registry_id)
        if reg:
            reg_pc = reg.get("parser_config") or {}
            reg_discover = reg_pc.get("discover") or {}
            if reg_discover.get("feed_urls") or reg_discover.get("strategies"):
                pc = {**reg_pc, **pc}
                discover = pc.get("discover") or reg_discover

    if not discover.get("feed_urls") and not discover.get("strategies") and source_url:
        pc = {
            **pc,
            "discover": {
                **discover,
                "kind": discover.get("kind") or "rss",
                "feed_urls": [source_url],
                "max_entries": discover.get("max_entries") or 50,
            },
        }

    return pc

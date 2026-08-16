"""Shared ingestion contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DiscoverItem:
    url: str
    title: str = ""
    published: str = ""
    summary: str = ""
    source_strategy: str = ""


@dataclass
class StrategyProbeResult:
    kind: str
    ok: bool
    item_count: int = 0
    filtered_count: int = 0
    error: str | None = None
    skipped: bool = False
    skip_reason: str | None = None
    sample_urls: list[str] = field(default_factory=list)
    requires_browser: bool = False


@dataclass
class AggregatorProbeResult:
    aggregator_id: str
    name: str
    fetch_mode: str
    ok: bool
    winning_strategy: str | None = None
    total_items: int = 0
    filtered_items: int = 0
    strategies: list[StrategyProbeResult] = field(default_factory=list)
    sample_urls: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def discover_config(entry: dict[str, Any]) -> dict[str, Any]:
    return (entry.get("parser_config") or {}).get("discover") or {}

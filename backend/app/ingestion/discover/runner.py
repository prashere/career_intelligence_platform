"""Run discover probes for registry entries."""

from __future__ import annotations

from typing import Any

import httpx

from app.ingestion.contracts import (
    AggregatorProbeResult,
    DiscoverItem,
    StrategyProbeResult,
)
from app.ingestion.discover.strategies import (
    probe_collegeboard_scholarships,
    probe_html,
    probe_html_paginated,
    probe_jina_html,
    probe_rss,
    probe_sitemap,
    probe_wp_json,
    probe_youthop_api,
)
from app.ingestion.fetch.browser import make_browser_client, playwright_available
from app.ingestion.filters import apply_filters
from app.ingestion.http_client import make_client

STRATEGY_HANDLERS = {
    "rss": probe_rss,
    "html": probe_html,
    "html_paginated": probe_html_paginated,
    "wp_json": probe_wp_json,
    "sitemap": probe_sitemap,
    "youthop_api": probe_youthop_api,
    "jina_html": probe_jina_html,
    "collegeboard_scholarships": probe_collegeboard_scholarships,
}


def _probe_strategy(
    client: httpx.Client,
    kind: str,
    config: dict[str, Any],
    filters: dict[str, Any] | None,
    *,
    skip_browser: bool,
) -> StrategyProbeResult:
    requires_browser = bool(config.get("requires_browser"))
    if requires_browser and skip_browser:
        return StrategyProbeResult(
            kind=kind,
            ok=False,
            skipped=True,
            skip_reason="requires_browser",
            requires_browser=True,
        )

    try:
        handler = STRATEGY_HANDLERS.get(kind)
        if not handler:
            return StrategyProbeResult(kind=kind, ok=False, error=f"unknown strategy kind: {kind}")
        raw_items = handler(client, config)
        filtered = apply_filters(raw_items, filters)
        ok = len(filtered) > 0
        return StrategyProbeResult(
            kind=kind,
            ok=ok,
            item_count=len(raw_items),
            filtered_count=len(filtered),
            sample_urls=[i.url for i in filtered[:3]],
            requires_browser=requires_browser,
            error=None if ok else "no items after filters",
        )
    except Exception as exc:
        return StrategyProbeResult(
            kind=kind,
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
            requires_browser=requires_browser,
        )


def _probe_single_discover(
    client: httpx.Client,
    discover: dict[str, Any],
    filters: dict[str, Any] | None,
    *,
    skip_browser: bool,
    timeout: float = 45.0,
) -> tuple[list[StrategyProbeResult], list[DiscoverItem], str | None]:
    kind = discover.get("kind") or "rss"
    results: list[StrategyProbeResult] = []
    winning: list[DiscoverItem] = []
    winning_kind: str | None = None

    if kind == "hybrid":
        strategies = discover.get("strategies") or []
        stop_on_success = bool(discover.get("stop_on_first_success", True))
        for strat in strategies:
            skind = strat.get("kind") or ""
            if strat.get("requires_browser") and skip_browser:
                results.append(
                    StrategyProbeResult(
                        kind=skind,
                        ok=False,
                        skipped=True,
                        skip_reason="requires_browser",
                        requires_browser=True,
                    )
                )
                continue
            result = _probe_strategy(client, skind, strat, filters, skip_browser=skip_browser)
            results.append(result)
            if result.ok and not winning_kind:
                handler = STRATEGY_HANDLERS.get(skind)
                if handler and not result.skipped:
                    winning = apply_filters(handler(client, strat), filters)
                    winning_kind = skind
                if stop_on_success:
                    break

        if not winning and not skip_browser and playwright_available():
            browser_client = make_browser_client(timeout=timeout)
            for strat in strategies:
                if not strat.get("requires_browser"):
                    continue
                skind = strat.get("kind") or ""
                result = _probe_strategy(browser_client, skind, strat, filters, skip_browser=False)
                results.append(result)
                if result.ok and not winning_kind:
                    handler = STRATEGY_HANDLERS.get(skind)
                    if handler:
                        winning = apply_filters(handler(browser_client, strat), filters)
                        winning_kind = f"{skind}+browser"
                    if stop_on_success:
                        break
        return results, winning, winning_kind

    result = _probe_strategy(client, kind, discover, filters, skip_browser=skip_browser)
    results.append(result)
    if result.ok and not result.skipped:
        handler = STRATEGY_HANDLERS.get(kind)
        if handler:
            winning = apply_filters(handler(client, discover), filters)
            winning_kind = kind
    return results, winning, winning_kind


def validate_aggregator(
    entry: dict[str, Any],
    *,
    timeout: float = 30.0,
    skip_browser: bool = True,
) -> AggregatorProbeResult:
    entry_id = str(entry.get("id") or "")
    discover = (entry.get("parser_config") or {}).get("discover") or {}
    filters = (entry.get("parser_config") or {}).get("filters")
    fetch_mode = str(entry.get("fetch_mode") or "http")
    timeout_ms = discover.get("request_timeout_ms")
    if timeout_ms:
        timeout = max(timeout, float(timeout_ms) / 1000.0)

    errors: list[str] = []
    all_strategies: list[StrategyProbeResult] = []
    winning_items: list[DiscoverItem] = []
    winning_strategy: str | None = None

    with make_client(timeout=timeout) as client:
        all_strategies, winning_items, winning_strategy = _probe_single_discover(
            client, discover, filters, skip_browser=skip_browser, timeout=timeout
        )

    if fetch_mode == "browser" and skip_browser:
        http_attempts = [s for s in all_strategies if not s.skipped]
        if not winning_items and not any(s.ok for s in http_attempts):
            if playwright_available():
                errors.append(
                    "fetch_mode=browser — use --include-browser; may fail behind Cloudflare datacenter IP"
                )
            else:
                errors.append("fetch_mode=browser — install playwright (pip install playwright)")

    ok = len(winning_items) > 0 or (
        fetch_mode == "browser"
        and skip_browser
        and any(s.skipped and s.skip_reason == "requires_browser" for s in all_strategies)
        and not playwright_available()
    )

    discover_cfg = discover
    if not ok and discover_cfg.get("region_blocked_hint"):
        if all_strategies and all(
            (s.error or "").find("ConnectTimeout") >= 0 or (s.error or "").find("ERR_CONNECTION_TIMED_OUT") >= 0
            for s in all_strategies
            if not s.skipped
        ):
            ok = True
            errors.append(
                "region_blocked (degraded pass) — DAAD unreachable from this network; "
                "use Docker EU or YouthOp DAAD listings"
            )

    if not ok and discover_cfg.get("cloudflare") and skip_browser:
        if all_strategies and all(s.skipped for s in all_strategies):
            ok = True
            errors.append(
                "cloudflare (degraded pass) — ScholarshipTab optional (default_active: false); "
                "needs Playwright + non-datacenter IP to ingest"
            )

    if not ok and not errors:
        failed = [s for s in all_strategies if not s.ok and not s.skipped]
        if failed:
            errors.append("; ".join(f"{s.kind}: {s.error}" for s in failed[:3]))

    return AggregatorProbeResult(
        aggregator_id=entry_id,
        name=str(entry.get("name") or entry_id),
        fetch_mode=fetch_mode,
        ok=ok,
        winning_strategy=winning_strategy,
        total_items=sum(s.item_count for s in all_strategies),
        filtered_items=len(winning_items),
        strategies=all_strategies,
        sample_urls=[i.url for i in winning_items[:3]],
        errors=errors,
    )


def validate_all_aggregators(
    registry: dict[str, Any],
    *,
    timeout: float = 30.0,
    skip_browser: bool = True,
) -> list[AggregatorProbeResult]:
    return [
        validate_aggregator(entry, timeout=timeout, skip_browser=skip_browser)
        for entry in registry.get("aggregators") or []
    ]

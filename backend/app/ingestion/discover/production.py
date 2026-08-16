"""Production discover — validated strategy handlers + optional browser."""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from app.ingestion.contracts import DiscoverItem, StrategyProbeResult
from app.ingestion.discover.runner import STRATEGY_HANDLERS
from app.ingestion.fetch.browser import make_browser_client, playwright_available
from app.ingestion.filters import apply_filters


class TraceCallback(Protocol):
    async def strategy_attempt(
        self,
        kind: str,
        *,
        ok: bool,
        item_count: int = 0,
        filtered_count: int = 0,
        error: str | None = None,
        skipped: bool = False,
        skip_reason: str | None = None,
        requires_browser: bool = False,
        sample_urls: list[str] | None = None,
    ) -> None: ...


def _run_strategy(
    client: Any,
    kind: str,
    strat: dict[str, Any],
    filters: dict[str, Any] | None,
) -> list[DiscoverItem]:
    handler = STRATEGY_HANDLERS.get(kind)
    if not handler:
        return []
    raw = handler(client, strat)
    return apply_filters(raw, filters)


async def _record_attempt(
    tracer: TraceCallback | None,
    kind: str,
    filtered: list[DiscoverItem],
    *,
    error: str | None = None,
    skipped: bool = False,
    skip_reason: str | None = None,
    requires_browser: bool = False,
    raw_count: int = 0,
) -> None:
    if not tracer:
        return
    await tracer.strategy_attempt(
        kind,
        ok=len(filtered) > 0,
        item_count=raw_count or len(filtered),
        filtered_count=len(filtered),
        error=error,
        skipped=skipped,
        skip_reason=skip_reason,
        requires_browser=requires_browser,
        sample_urls=[i.url for i in filtered[:3]],
    )


async def _discover_hybrid(
    client: Any,
    discover: dict[str, Any],
    filters: dict[str, Any] | None,
    *,
    use_browser: bool,
    tracer: TraceCallback | None = None,
) -> tuple[list[DiscoverItem], str | None, list[StrategyProbeResult]]:
    strategies = discover.get("strategies") or []
    stop_on_success = bool(discover.get("stop_on_first_success", True))
    probe_results: list[StrategyProbeResult] = []

    for strat in strategies:
        if strat.get("requires_browser"):
            continue
        kind = strat.get("kind") or ""
        try:
            handler = STRATEGY_HANDLERS.get(kind)
            if not handler:
                probe_results.append(StrategyProbeResult(kind=kind, ok=False, error=f"unknown kind: {kind}"))
                await _record_attempt(tracer, kind, [], error=f"unknown kind: {kind}")
                continue
            raw = handler(client, strat)
            filtered = apply_filters(raw, filters)
            ok = len(filtered) > 0
            probe_results.append(
                StrategyProbeResult(
                    kind=kind,
                    ok=ok,
                    item_count=len(raw),
                    filtered_count=len(filtered),
                    sample_urls=[i.url for i in filtered[:3]],
                    error=None if ok else "no items after filters",
                )
            )
            await _record_attempt(tracer, kind, filtered, raw_count=len(raw))
            if filtered:
                return filtered, kind, probe_results
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"
            probe_results.append(StrategyProbeResult(kind=kind, ok=False, error=err))
            await _record_attempt(tracer, kind, [], error=err)
            if stop_on_success:
                continue

    if use_browser and playwright_available():
        browser_client = make_browser_client(
            timeout=max(30.0, float(discover.get("request_timeout_ms") or 45000) / 1000.0)
        )
        for strat in strategies:
            if not strat.get("requires_browser"):
                continue
            kind = strat.get("kind") or ""
            try:
                handler = STRATEGY_HANDLERS.get(kind)
                if not handler:
                    continue
                raw = handler(browser_client, strat)
                filtered = apply_filters(raw, filters)
                ok = len(filtered) > 0
                probe_results.append(
                    StrategyProbeResult(
                        kind=kind,
                        ok=ok,
                        item_count=len(raw),
                        filtered_count=len(filtered),
                        sample_urls=[i.url for i in filtered[:3]],
                        requires_browser=True,
                        error=None if ok else "no items after filters",
                    )
                )
                await _record_attempt(
                    tracer, kind, filtered, raw_count=len(raw), requires_browser=True
                )
                if filtered:
                    return filtered, f"{kind}+browser", probe_results
            except Exception as exc:
                err = f"{type(exc).__name__}: {exc}"
                probe_results.append(
                    StrategyProbeResult(kind=kind, ok=False, error=err, requires_browser=True)
                )
                await _record_attempt(tracer, kind, [], error=err, requires_browser=True)

    for strat in strategies:
        if not strat.get("requires_browser"):
            continue
        kind = strat.get("kind") or ""
        if not any(p.kind == kind and p.skipped for p in probe_results):
            if use_browser:
                continue
            probe_results.append(
                StrategyProbeResult(
                    kind=kind,
                    ok=False,
                    skipped=True,
                    skip_reason="requires_browser",
                    requires_browser=True,
                )
            )
            await _record_attempt(
                tracer,
                kind,
                [],
                skipped=True,
                skip_reason="requires_browser",
                requires_browser=True,
            )

    return [], None, probe_results


async def discover_items(
    client: httpx.Client,
    parser_config: dict[str, Any],
    *,
    use_browser: bool = False,
    tracer: TraceCallback | None = None,
) -> tuple[list[DiscoverItem], str | None, list[StrategyProbeResult]]:
    discover = parser_config.get("discover") or {}
    filters = parser_config.get("filters")
    kind = discover.get("kind") or "rss"
    probe_results: list[StrategyProbeResult] = []

    if kind == "hybrid":
        items, strategy, probes = await _discover_hybrid(
            client, discover, filters, use_browser=use_browser, tracer=tracer
        )
        return items, strategy, probes

    if discover.get("requires_browser") and not (use_browser and playwright_available()):
        probe_results.append(
            StrategyProbeResult(
                kind=kind,
                ok=False,
                skipped=True,
                skip_reason="requires_browser",
                requires_browser=True,
            )
        )
        await _record_attempt(
            tracer, kind, [], skipped=True, skip_reason="requires_browser", requires_browser=True
        )
        return [], None, probe_results

    fetch_client: Any = client
    if discover.get("requires_browser") and use_browser and playwright_available():
        fetch_client = make_browser_client()

    handler = STRATEGY_HANDLERS.get(kind)
    if not handler:
        probe_results.append(StrategyProbeResult(kind=kind, ok=False, error=f"unknown kind: {kind}"))
        await _record_attempt(tracer, kind, [], error=f"unknown kind: {kind}")
        return [], None, probe_results

    try:
        raw = handler(fetch_client, discover)
        filtered = apply_filters(raw, filters)
        ok = len(filtered) > 0
        probe_results.append(
            StrategyProbeResult(
                kind=kind,
                ok=ok,
                item_count=len(raw),
                filtered_count=len(filtered),
                sample_urls=[i.url for i in filtered[:3]],
                error=None if ok else "no items after filters",
            )
        )
        await _record_attempt(tracer, kind, filtered, raw_count=len(raw))
        return filtered, kind if ok else None, probe_results
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        probe_results.append(StrategyProbeResult(kind=kind, ok=False, error=err))
        await _record_attempt(tracer, kind, [], error=err)
        return [], None, probe_results

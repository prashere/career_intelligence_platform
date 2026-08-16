#!/usr/bin/env python3
"""Live-probe every aggregator discover strategy in source-registry.yaml.

Usage:
    python scripts/validate_discover_strategies.py
    python scripts/validate_discover_strategies.py --aggregator scholars4dev
    python scripts/validate_discover_strategies.py --timeout 45
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingestion.discover.runner import validate_aggregator, validate_all_aggregators
from app.services.profile_pipeline import load_source_registry
from app.source_registry_paths import load_ingestion_config


def _print_result(result) -> None:
    status = "PASS" if result.ok else "FAIL"
    print(f"\n[{status}] {result.aggregator_id} — {result.name} (fetch_mode={result.fetch_mode})")
    if result.winning_strategy:
        print(f"  winning strategy: {result.winning_strategy} ({result.filtered_items} items after filters)")
    for strat in result.strategies:
        if strat.skipped:
            print(f"  - {strat.kind}: SKIP ({strat.skip_reason})")
        elif strat.ok:
            print(
                f"  - {strat.kind}: OK raw={strat.item_count} filtered={strat.filtered_count}"
            )
        else:
            print(f"  - {strat.kind}: FAIL — {strat.error}")
    for url in result.sample_urls:
        print(f"    sample: {url}")
    for err in result.errors:
        print(f"  ! {err}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate discover strategies against live sources")
    parser.add_argument("--aggregator", help="Probe a single aggregator id")
    ingestion_cfg = load_ingestion_config()
    default_timeout = float((ingestion_cfg.get("validation") or {}).get("http_timeout_seconds") or 35)
    parser.add_argument("--timeout", type=float, default=default_timeout, help="HTTP timeout seconds")
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    parser.add_argument(
        "--include-browser",
        action="store_true",
        help="Attempt browser-required strategies over HTTP (default: skip them)",
    )
    args = parser.parse_args()

    registry = load_source_registry()
    entries = registry.get("aggregators") or []
    if args.aggregator:
        entries = [e for e in entries if e.get("id") == args.aggregator]
        if not entries:
            print(f"Unknown aggregator: {args.aggregator}")
            return 1

    results = [
        validate_aggregator(
            entry,
            timeout=args.timeout,
            skip_browser=not args.include_browser,
        )
        for entry in entries
    ]

    if args.json:
        payload = [
            {
                "id": r.aggregator_id,
                "ok": r.ok,
                "fetch_mode": r.fetch_mode,
                "winning_strategy": r.winning_strategy,
                "filtered_items": r.filtered_items,
                "sample_urls": r.sample_urls,
                "strategies": [
                    {
                        "kind": s.kind,
                        "ok": s.ok,
                        "skipped": s.skipped,
                        "skip_reason": s.skip_reason,
                        "item_count": s.item_count,
                        "filtered_count": s.filtered_count,
                        "error": s.error,
                    }
                    for s in r.strategies
                ],
                "errors": r.errors,
            }
            for r in results
        ]
        print(json.dumps(payload, indent=2))
    else:
        for result in results:
            _print_result(result)
        passed = sum(1 for r in results if r.ok)
        print(f"\nSummary: {passed}/{len(results)} aggregators passed")

    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

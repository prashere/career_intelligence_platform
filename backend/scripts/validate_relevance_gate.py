#!/usr/bin/env python3
"""Run live discover for each registry aggregator and score every item.

This is the offline equivalent of the Ingestion lab: it reports the verdict
distribution per aggregator so you can spot a source that is being over- or
under-admitted before wiring it into production.

Usage:
    python scripts/validate_relevance_gate.py
    python scripts/validate_relevance_gate.py --aggregator bold --show-items
    python scripts/validate_relevance_gate.py --max-items 30 --timeout 45
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingestion.discover.runner import _probe_single_discover
from app.ingestion.http_client import make_client
from app.ingestion.relevance import Candidate, Verdict, evaluate, profile_terms_from_envelope
from app.services.profile_pipeline import load_source_registry
from app.source_registry_paths import load_ingestion_config


def _score_aggregator(entry: dict, *, timeout: float, max_items: int, profile) -> dict:
    parser_config = entry.get("parser_config") or {}
    discover = parser_config.get("discover") or {}
    filters = parser_config.get("filters")
    regions = entry.get("regions") or []
    if isinstance(regions, str):
        regions = [regions]

    with make_client(timeout=timeout) as client:
        _, items, winning = _probe_single_discover(
            client, discover, filters, skip_browser=True, timeout=timeout
        )

    counts = {"admit": 0, "investigate": 0, "reject": 0}
    rows = []
    for item in items[:max_items]:
        decision = evaluate(
            Candidate(
                url=item.url or "",
                title=item.title or "",
                summary=item.summary or "",
                source_regions=[str(r) for r in regions],
            ),
            profile=profile,
        )
        counts[decision.verdict.value] += 1
        rows.append(
            {
                "title": item.title,
                "url": item.url,
                "verdict": decision.verdict.value,
                "score": round(decision.score, 3),
                "reason": decision.reason,
                "evidence": decision.evidence_summary(limit=4),
            }
        )

    return {
        "id": entry.get("id"),
        "name": entry.get("name"),
        "winning_strategy": winning,
        "discovered": len(items),
        "scored": len(rows),
        **counts,
        "items": rows,
    }


def main() -> int:
    ingestion_cfg = load_ingestion_config()
    default_timeout = float((ingestion_cfg.get("validation") or {}).get("http_timeout_seconds") or 35)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aggregator", help="Score a single aggregator id")
    parser.add_argument("--timeout", type=float, default=default_timeout)
    parser.add_argument("--max-items", type=int, default=20)
    parser.add_argument("--show-items", action="store_true", help="Print every scored item")
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    parser.add_argument(
        "--envelope",
        help="Path to a filter_config.json to score against (default: no profile terms)",
    )
    args = parser.parse_args()

    envelope = None
    if args.envelope:
        envelope = json.loads(Path(args.envelope).read_text(encoding="utf-8"))
    profile = profile_terms_from_envelope(envelope)

    registry = load_source_registry()
    entries = registry.get("aggregators") or []
    if args.aggregator:
        entries = [e for e in entries if e.get("id") == args.aggregator]
        if not entries:
            print(f"Unknown aggregator: {args.aggregator}")
            return 1

    reports = []
    for entry in entries:
        try:
            reports.append(
                _score_aggregator(entry, timeout=args.timeout, max_items=args.max_items, profile=profile)
            )
        except Exception as exc:
            reports.append(
                {
                    "id": entry.get("id"),
                    "name": entry.get("name"),
                    "error": f"{type(exc).__name__}: {exc}",
                    "discovered": 0,
                    "scored": 0,
                    "admit": 0,
                    "investigate": 0,
                    "reject": 0,
                    "items": [],
                }
            )

    if args.json:
        print(json.dumps(reports, indent=2))
        return 0

    print(f"{'AGGREGATOR':<22} {'FOUND':>6} {'ADMIT':>6} {'INVEST':>7} {'REJECT':>7}  STRATEGY")
    print("-" * 78)
    for report in reports:
        if report.get("error"):
            print(f"{str(report['id']):<22} {'ERROR':>6}  {report['error'][:40]}")
            continue
        print(
            f"{str(report['id']):<22} {report['discovered']:>6} {report['admit']:>6} "
            f"{report['investigate']:>7} {report['reject']:>7}  {report.get('winning_strategy') or 'none'}"
        )
        if args.show_items:
            for row in report["items"]:
                print(f"    [{row['verdict']:<11} {row['score']:.2f}] {(row['title'] or '')[:70]}")
                print(f"        {row['reason']} | {', '.join(row['evidence']) or 'no evidence'}")

    total_admit = sum(r["admit"] for r in reports)
    total_scored = sum(r["scored"] for r in reports)
    total_reject = sum(r["reject"] for r in reports)
    print(
        f"\nTotals: {total_scored} scored, {total_admit} admit, "
        f"{sum(r['investigate'] for r in reports)} investigate, {total_reject} reject"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

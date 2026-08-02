#!/usr/bin/env python3
"""Verify profile package is ready for Sprint 1 ingest.

Usage:
    python scripts/check_profile_ready.py
    python scripts/check_profile_ready.py --expected-sources 4
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.profile_pipeline import check_profile_ready


def main() -> int:
    parser = argparse.ArgumentParser(description="Check profile readiness for ingest")
    parser.add_argument(
        "--expected-sources",
        type=int,
        default=4,
        help="Expected number of RSS sources in ingestion_sources.json",
    )
    args = parser.parse_args()

    ok, messages = check_profile_ready(expected_sources=args.expected_sources)
    for msg in messages:
        prefix = "OK" if ok else "!"
        print(f"[{prefix}] {msg}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""List or validate the git-tracked aggregator catalog.

Usage:
    python scripts/list_source_registry.py
    python scripts/list_source_registry.py --validate
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.source_registry_paths import SOURCE_REGISTRY_PATH
from app.services.profile_pipeline import load_source_registry


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect backend/app/data/source-registry.yaml")
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Check required fields on each aggregator entry",
    )
    args = parser.parse_args()

    if not SOURCE_REGISTRY_PATH.exists():
        print(f"Error: registry not found at {SOURCE_REGISTRY_PATH}")
        return 1

    print(f"Registry: {SOURCE_REGISTRY_PATH}")
    registry = load_source_registry()
    aggregators = registry.get("aggregators") or []
    default_n = registry.get("default_selection_count", 4)
    print(f"  schema_version: {registry.get('schema_version', '?')}")
    print(f"  default_selection_count: {default_n}")
    print(f"  aggregators: {len(aggregators)}")
    print()

    errors: list[str] = []
    for entry in aggregators:
        entry_id = entry.get("id", "?")
        name = entry.get("name", "?")
        url = entry.get("url", "")
        rss = entry.get("type", "rss")
        print(f"  [{entry_id}] {name}")
        print(f"    url: {url}")
        print(f"    type: {rss}  regions: {entry.get('regions')}  chip: {entry.get('chip_label', '—')}")

        if args.validate:
            for field in ("id", "name", "url", "type"):
                if not entry.get(field):
                    errors.append(f"{entry_id}: missing {field}")
            if entry.get("type") == "rss" and not str(entry.get("url", "")).startswith("http"):
                errors.append(f"{entry_id}: invalid rss url")

    if args.validate:
        if errors:
            print("\nValidation errors:")
            for err in errors:
                print(f"  - {err}")
            return 1
        print("\nValidation passed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

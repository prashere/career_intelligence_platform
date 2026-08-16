#!/usr/bin/env python3
"""Compile L3 artifacts from structured-profile.json (deterministic, no LLM).

RSS URLs are resolved from config/sources/source-registry.yaml via profile.sources.aggregators.

Usage:
    python scripts/compile_profile.py
    python scripts/compile_profile.py path/to/structured-profile.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.profile_intake import load_structured_profile
from app.services.profile_pipeline import compile_profile


def main() -> int:
    if len(sys.argv) > 2:
        print("Usage: python scripts/compile_profile.py [structured-profile.json]")
        return 1

    if len(sys.argv) == 2:
        data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    else:
        data = load_structured_profile()
        if not data:
            print("Error: structured-profile.json not found.")
            return 1

    try:
        paths = compile_profile(data)
    except ValueError as exc:
        print(f"Compile failed: {exc}")
        return 1

    print("Compiled L3 artifacts:")
    for key, path in paths.items():
        print(f"  {key}: {path}")

    ing = json.loads(paths["ingestion_sources"].read_text(encoding="utf-8"))
    print(f"\nIngestion sources ({len(ing.get('sources', []))}):")
    for src in ing.get("sources", []):
        print(f"  - {src['name']}: {src['url']}")

    manual = ing.get("manual_channels") or []
    if manual:
        print(f"\nManual channels (not ingested): {', '.join(manual)}")

    rc_path = paths.get("ranking_config")
    if rc_path and rc_path.exists():
        rc = json.loads(rc_path.read_text(encoding="utf-8"))
        print(
            f"\nRanking: discovery_mode={rc.get('discovery_mode')}, "
            f"uni_weight={rc.get('university_match_weight')}"
        )

    print("\nNext: python scripts/check_profile_ready.py")
    print("       python scripts/seed_sources_from_profile.py")
    print("       python scripts/sync_profile_to_db.py")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

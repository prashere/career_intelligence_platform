#!/usr/bin/env python3
"""Build structured-profile.prefill.json from raw-submission.json (no LLM).

Aggregator selection reads config/sources/source-registry.yaml (git-tracked).

Usage:
    python scripts/prefill_structured.py
    python scripts/prefill_structured.py path/to/raw-submission.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.source_registry_paths import SOURCE_REGISTRY_PATH
from app.services.profile_pipeline import prefill_from_submission, save_prefill


def main() -> int:
    if len(sys.argv) > 2:
        print("Usage: python scripts/prefill_structured.py [raw-submission.json]")
        return 1

    if len(sys.argv) == 2:
        raw_path = Path(sys.argv[1])
        if not raw_path.exists():
            print(f"Error: file not found: {raw_path}")
            return 1
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        data = prefill_from_submission(raw)
    else:
        data = prefill_from_submission()

    path = save_prefill(data)
    print(f"Prefill saved to: {path}")
    print(f"  Registry: {SOURCE_REGISTRY_PATH}")
    print(f"  Discovery mode: {data.get('preferences', {}).get('discovery_mode', 'open')}")
    print(f"  Aggregators selected: {len(data.get('sources', {}).get('aggregators', []))}")
    for agg in data.get("sources", {}).get("aggregators", []):
        print(f"    - {agg['id']} (priority {agg['priority']})")
    manual = data.get("sources", {}).get("manual_channels") or []
    if manual:
        print(f"  Manual channels: {', '.join(manual)}")
    print("\nNext: run CV extraction, then merge_profile.py and compile_profile.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

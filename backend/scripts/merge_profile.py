#!/usr/bin/env python3
"""Merge prefill + CV extraction output into a full structured profile candidate.

Usage:
    python scripts/merge_profile.py
    python scripts/merge_profile.py path/to/extraction-output.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.profile_intake import intake_dir, validate_structured_profile
from app.services.profile_pipeline import load_extraction_json, load_prefill, merge_prefill_and_extraction


def main() -> int:
    prefill = load_prefill()
    if not prefill:
        print("Error: structured-profile.prefill.json not found. Run prefill_structured.py first.")
        return 1

    extract_path = intake_dir() / "extraction-output.json"
    if len(sys.argv) == 2:
        extract_path = Path(sys.argv[1])

    if not extract_path.exists():
        print(f"Error: extraction file not found: {extract_path}")
        return 1

    try:
        extraction = load_extraction_json(extract_path)
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON in {extract_path} — {exc}")
        print("Ensure the file contains valid JSON only (no markdown fences).")
        return 1
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1

    merged = merge_prefill_and_extraction(prefill, extraction)

    out_path = intake_dir() / "structured-profile.merged.json"
    out_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")

    profile, errors = validate_structured_profile(merged)
    if profile is None:
        print("Merge complete but validation failed:")
        for err in errors:
            print(f"  - {err}")
        print(f"\nMerged draft saved to: {out_path}")
        print("Fix extraction JSON or prefill, then re-run merge.")
        return 1

    print("Merge and validation passed.")
    print(f"  Name: {profile.identity.full_name}")
    print(f"  Keywords: {len(profile.search_keywords)}")
    print(f"  Experiences: {len(profile.experiences)}")
    print(f"  Aggregators: {len(profile.sources.aggregators)}")
    print(f"  Manual channels: {', '.join(profile.sources.manual_channels) or '—'}")
    print(f"  Discovery mode: {profile.preferences.discovery_mode.value}")
    if profile.extraction_meta.fields_needing_review:
        print("\nFields needing review:")
        for field in profile.extraction_meta.fields_needing_review:
            print(f"  - {field}")

    structured_path = intake_dir() / "structured-profile.json"
    structured_path.write_text(
        json.dumps(profile.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nSaved to: {structured_path}")
    print("Review the file, then run: python scripts/compile_profile.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

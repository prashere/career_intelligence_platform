#!/usr/bin/env python3
"""Validate profile extraction JSON against StructuredProfile schema.

Usage:
    python scripts/validate_extraction.py path/to/extraction-output.json
"""

import json
import sys
from pathlib import Path

# Allow running from backend/ directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError

from app.schemas.profile_intake import StructuredProfile


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/validate_extraction.py <json-file>")
        return 1

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"Error: file not found: {path}")
        return 1

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON — {exc}")
        return 1

    try:
        profile = StructuredProfile.model_validate(data)
    except ValidationError as exc:
        print("Validation failed:\n")
        print(exc)
        return 1

    print("Validation passed.")
    print(f"  Name: {profile.identity.full_name}")
    print(f"  Target: {profile.preferences.target_degree.value} — {profile.preferences.target_intake_term}")
    print(f"  Funding: {profile.preferences.funding_requirement.value}")
    print(f"  Keywords: {len(profile.search_keywords)} terms")
    print(f"  Confidence: {profile.extraction_meta.confidence.value}")

    if profile.extraction_meta.fields_needing_review:
        print("\nFields needing your review:")
        for field in profile.extraction_meta.fields_needing_review:
            print(f"  - {field}")

    if profile.extraction_meta.confidence.value == "low":
        print("\nWarning: confidence is LOW — review carefully before saving as structured-profile.json")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

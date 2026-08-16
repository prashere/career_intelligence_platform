#!/usr/bin/env python3
"""Score sample titles through the relevance gate.

Useful for tuning thresholds in config/sources/relevance-config.yaml without
running a full ingestion. Pass titles as arguments, or run with no arguments to
score the built-in regression set.

Usage:
    python scripts/probe_relevance.py
    python scripts/probe_relevance.py "Chevening Scholarship 2026" --url https://x.com/scholarships/a
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingestion.relevance import Candidate, evaluate, profile_terms_from_envelope

SAMPLES: list[tuple[str, str]] = [
    ("Endeavour Women in Tech Scholarship 2026 (up to $10,000)", "https://bold.org/scholarships/endeavour-women-in-tech/"),
    ("Fully Funded PhD Position in Machine Learning at TU Munich", "https://example.org/phd/tum-ml"),
    ("Chevening Scholarships 2026 for International Students", "https://example.org/scholarships/chevening"),
    ("DAAD Helmut Schmidt Programme", "https://example.org/scholarships/daad-helmut"),
    ("Summer Research Internship, Deadline 30 April", "https://example.org/internships/summer"),
    ("About Us", "https://bold.org/about/"),
    ("Privacy Policy", "https://bold.org/privacy/"),
    ("Contact", "https://example.org/contact/"),
    ("2025 Winners Announced for the Global Youth Prize", "https://example.org/news/winners-2025"),
    ("Read more", "https://example.org/scholarships/hidden-gem"),
    ("How I passed my IELTS exam in two weeks", "https://example.org/blog/ielts-tips"),
]

# Mirrors a compiled profile envelope: narrow disciplines, narrow regions.
DEMO_ENVELOPE = {
    "must_match_any": ["MSc", "master", "scholarship", "fellowship", "fully funded", "stipend", "tuition"],
    "profile_match_any": ["computer science", "machine learning", "data science", "artificial intelligence"],
    "region_match_any": ["Germany", "German", "DAAD", "Europe", "European", "EU"],
    "hard_drop_any": ["webinar only", "conference registration", "high school"],
    "target_degree_levels": ["MSc"],
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("titles", nargs="*", help="Titles to score")
    parser.add_argument("--url", default="", help="URL to attach to supplied titles")
    parser.add_argument("--summary", default="", help="Summary text to attach")
    parser.add_argument("--regions", default="", help="Comma separated source registry regions")
    parser.add_argument("--no-profile", action="store_true", help="Score without profile terms")
    args = parser.parse_args()

    profile = profile_terms_from_envelope(None if args.no_profile else DEMO_ENVELOPE)
    source_regions = [r.strip() for r in args.regions.split(",") if r.strip()]

    samples = [(t, args.url) for t in args.titles] if args.titles else SAMPLES

    width = max(len(t) for t, _ in samples) + 2
    print(f"{'TITLE'.ljust(width)} {'VERDICT':<13} {'SCORE':>6} {'SUFF':>5}  REASON / EVIDENCE")
    print("-" * (width + 60))

    for title, url in samples:
        decision = evaluate(
            Candidate(
                url=url,
                title=title,
                summary=args.summary,
                source_regions=source_regions,
            ),
            profile=profile,
        )
        evidence = ", ".join(decision.evidence_summary(limit=3)) or "none"
        print(
            f"{title.ljust(width)} {decision.verdict.value:<13} "
            f"{decision.score:>6.2f} {decision.sufficiency:>5.2f}  {decision.reason} [{evidence}]"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

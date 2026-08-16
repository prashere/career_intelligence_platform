"""Interest envelope — operator preferences fed into the relevance gate.

Historically this module also *applied* the envelope as a chain of pass/fail
keyword gates. That is gone: requiring a discipline, a region and a funding word
to all appear in a listing title rejected most valid opportunities. The envelope
is now scoring input only, consumed via
`app.ingestion.relevance.profile_terms_from_envelope`, where each key raises the
score instead of vetoing the item.
"""

from __future__ import annotations

from typing import Any

# Keys carried through from the compiled profile artifact (filter_config.json).
UNION_KEYS = (
    "must_match_any",
    "profile_match_any",
    "region_match_any",
    "institution_match_any",
)


def merge_envelopes(envelopes: list[dict[str, Any]]) -> dict[str, Any]:
    """Union the positive terms, intersect the drops.

    Intersecting `hard_drop_any` keeps one operator's exclusion from silently
    censoring the corpus for everyone else.
    """
    if not envelopes:
        return default_envelope()

    merged: dict[str, Any] = {key: [] for key in UNION_KEYS}
    merged["hard_drop_any"] = []

    for env in envelopes:
        for key in UNION_KEYS:
            merged[key].extend(env.get(key) or [])

    hard_sets = [{h.lower() for h in (env.get("hard_drop_any") or []) if h} for env in envelopes]
    if hard_sets:
        intersect = set.intersection(*hard_sets) if len(hard_sets) > 1 else hard_sets[0]
        merged["hard_drop_any"] = sorted(intersect)

    for key in UNION_KEYS + ("hard_drop_any",):
        merged[key] = list(dict.fromkeys(x for x in merged[key] if x))
    return merged


def default_envelope() -> dict[str, Any]:
    """Neutral envelope used before a profile has been compiled.

    Deliberately empty on discipline and region: with no operator preferences
    on file, every genuine opportunity belongs in the corpus.
    """
    return {
        "must_match_any": [],
        "profile_match_any": [],
        "region_match_any": [],
        "institution_match_any": [],
        "hard_drop_any": ["webinar only"],
    }

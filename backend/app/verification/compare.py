"""Compare aggregator claims against primary-source extraction."""

from __future__ import annotations

from datetime import datetime, timezone

from rapidfuzz import fuzz

from app.verification.contracts import (
    AggregatorClaims,
    ComparisonResult,
    FieldComparison,
    PrimaryFields,
)

DEADLINE_TOLERANCE_DAYS = 7
FUNDING_MATCH_THRESHOLD = 0.55
ELIGIBILITY_MATCH_THRESHOLD = 0.45


def _deadline_match(agg: datetime | None, primary: datetime | None) -> tuple[bool, float, str | None]:
    if agg is None and primary is None:
        return True, 1.0, "both_missing"
    if agg is None or primary is None:
        return False, 0.0, "one_missing"
    a = agg.replace(tzinfo=timezone.utc) if agg.tzinfo is None else agg
    p = primary.replace(tzinfo=timezone.utc) if primary.tzinfo is None else primary
    delta = abs((a - p).days)
    if delta <= DEADLINE_TOLERANCE_DAYS:
        return True, 1.0 - min(delta / DEADLINE_TOLERANCE_DAYS, 1.0) * 0.3, f"within_{delta}_days"
    return False, max(0.0, 1.0 - delta / 60), f"delta_{delta}_days"


def _text_similarity(a: str | None, b: str | None) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return fuzz.token_set_ratio(a.lower(), b.lower()) / 100.0


def compare_claims(aggregator: AggregatorClaims, primary: PrimaryFields) -> ComparisonResult:
    fields: list[FieldComparison] = []
    discrepancies: list[str] = []

    d_match, d_sim, d_note = _deadline_match(aggregator.deadline, primary.deadline)
    fields.append(
        FieldComparison(
            field="deadline",
            aggregator_value=aggregator.deadline.isoformat() if aggregator.deadline else None,
            primary_value=primary.deadline.isoformat() if primary.deadline else None,
            match=d_match,
            similarity=d_sim,
            note=d_note,
        )
    )
    if not d_match:
        discrepancies.append(f"deadline_mismatch:{d_note}")

    funding_text = aggregator.funding_type or ""
    if aggregator.summary and "fund" in (aggregator.summary or "").lower():
        funding_text = f"{funding_text} {aggregator.summary[:400]}"
    f_sim = _text_similarity(funding_text, primary.funding_summary)
    f_match = f_sim >= FUNDING_MATCH_THRESHOLD
    fields.append(
        FieldComparison(
            field="funding",
            aggregator_value=aggregator.funding_type,
            primary_value=primary.funding_summary,
            match=f_match,
            similarity=f_sim,
        )
    )
    if not f_match and primary.funding_summary:
        discrepancies.append("funding_mismatch")

    elig_agg = aggregator.eligibility_text or (aggregator.summary or "")[:600]
    e_sim = _text_similarity(elig_agg, primary.eligibility_summary)
    e_match = e_sim >= ELIGIBILITY_MATCH_THRESHOLD
    fields.append(
        FieldComparison(
            field="eligibility",
            aggregator_value=elig_agg[:200] if elig_agg else None,
            primary_value=(primary.eligibility_summary or "")[:200] or None,
            match=e_match,
            similarity=e_sim,
        )
    )
    if not e_match and primary.eligibility_summary:
        discrepancies.append("eligibility_mismatch")

    all_match = all(f.match for f in fields if f.primary_value is not None)
    partial = not all_match and any(f.similarity >= 0.4 for f in fields)

    return ComparisonResult(
        all_match=all_match,
        partial_match=partial,
        fields=fields,
        discrepancies=discrepancies,
    )

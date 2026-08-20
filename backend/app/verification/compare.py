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


def _has_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _text_similarity(a: str | None, b: str | None) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    # Aggregator blurbs are long and primary extracts are short, so measure how
    # well the shorter text is contained in the longer one instead of penalising
    # the length difference.
    return fuzz.partial_token_set_ratio(a.lower(), b.lower()) / 100.0


_FUNDING_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("self", ("self-funded", "self funded", "unfunded", "no funding", "not funded")),
    ("partial", ("partial", "partially funded", "co-funded", "tuition only")),
    (
        "full",
        (
            "fully funded",
            "fully-funded",
            "full funding",
            "full scholarship",
            "all expenses",
            "covers all",
            "full",
        ),
    ),
)


def funding_category(text: str | None) -> str | None:
    """Normalize funding wording to full/partial/self, or None when unstated.

    Free-text funding blurbs rarely align word for word even when they agree,
    so comparing categories avoids inventing conflicts from phrasing.
    """
    if not text:
        return None
    lowered = text.lower()
    for category, needles in _FUNDING_PATTERNS:
        if any(needle in lowered for needle in needles):
            return category
    return None


#: Objective, machine-comparable fields. Eligibility is free prose that rarely
#: aligns word for word, so it informs conflicts but never blocks confirmation.
HIGH_SIGNAL_FIELDS = ("deadline", "funding")


def confirms_listing(result: ComparisonResult) -> bool:
    """Whether the primary page positively confirms the aggregator's claims.

    Requires at least one objective field to be checkable and every checkable
    objective field to agree, with no material conflict anywhere.
    """
    if has_material_conflict(result):
        return False
    high_signal = [
        f for f in result.fields if f.field in HIGH_SIGNAL_FIELDS and f.comparable
    ]
    if not high_signal:
        return False
    return all(f.match for f in high_signal)


def has_material_conflict(result: ComparisonResult) -> bool:
    """Whether discrepancies are strong enough to call the listing contradicted.

    A conflict hides the opportunity from the feed, so a single fuzzy text
    mismatch is not enough. Either the deadline (an objective, comparable date)
    disagrees, or several fields disagree at once.
    """
    if any(d.startswith("deadline_mismatch") for d in result.discrepancies):
        return True
    return len(result.discrepancies) >= 2


def compare_claims(aggregator: AggregatorClaims, primary: PrimaryFields) -> ComparisonResult:
    fields: list[FieldComparison] = []
    discrepancies: list[str] = []

    d_match, d_sim, d_note = _deadline_match(aggregator.deadline, primary.deadline)
    deadline_comparable = aggregator.deadline is not None and primary.deadline is not None
    fields.append(
        FieldComparison(
            field="deadline",
            aggregator_value=aggregator.deadline.isoformat() if aggregator.deadline else None,
            primary_value=primary.deadline.isoformat() if primary.deadline else None,
            match=d_match,
            similarity=d_sim,
            note=d_note,
            comparable=deadline_comparable,
        )
    )
    if deadline_comparable and not d_match:
        discrepancies.append(f"deadline_mismatch:{d_note}")

    # Titles often carry the funding claim, e.g. "AMS School 2026 (Fully Funded)".
    funding_text = " ".join(
        part
        for part in (aggregator.funding_type, aggregator.title, aggregator.summary)
        if part
    )
    agg_funding = funding_category(funding_text)
    primary_funding = funding_category(primary.funding_summary)
    funding_comparable = agg_funding is not None and primary_funding is not None
    f_match = (not funding_comparable) or agg_funding == primary_funding
    f_sim = 1.0 if f_match else 0.0
    fields.append(
        FieldComparison(
            field="funding",
            aggregator_value=agg_funding or aggregator.funding_type,
            primary_value=primary_funding or primary.funding_summary,
            match=f_match,
            similarity=f_sim,
            comparable=funding_comparable,
            note=f"{agg_funding or 'unknown'}_vs_{primary_funding or 'unknown'}",
        )
    )
    if funding_comparable and not f_match:
        discrepancies.append("funding_mismatch")

    elig_agg = aggregator.eligibility_text or (aggregator.summary or "")[:600]
    e_sim = _text_similarity(elig_agg, primary.eligibility_summary)
    e_match = e_sim >= ELIGIBILITY_MATCH_THRESHOLD
    elig_comparable = _has_value(elig_agg) and _has_value(primary.eligibility_summary)
    fields.append(
        FieldComparison(
            field="eligibility",
            aggregator_value=elig_agg[:200] if elig_agg else None,
            primary_value=(primary.eligibility_summary or "")[:200] or None,
            match=e_match,
            similarity=e_sim,
            comparable=elig_comparable,
        )
    )
    if elig_comparable and not e_match:
        discrepancies.append("eligibility_mismatch")

    comparable_fields = [f for f in fields if f.comparable]
    # Without a single comparable field there is nothing to confirm, so the
    # caller should fall back to aggregator_only rather than claim a match.
    all_match = bool(comparable_fields) and all(f.match for f in comparable_fields)
    partial = not all_match and any(f.similarity >= 0.4 for f in comparable_fields)

    return ComparisonResult(
        all_match=all_match,
        partial_match=partial,
        fields=fields,
        discrepancies=discrepancies,
    )

"""Single source of truth for opportunity trust presentation in API and UI."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional, TypedDict

from app.models import Opportunity
from app.models.verification import VerificationStatus

TrustState = Literal["verified", "aggregator_only", "unchecked", "conflict"]

TRUST_LABELS: dict[TrustState, str] = {
    "verified": "Confirmed at source",
    "aggregator_only": "Aggregator only",
    "unchecked": "Not checked yet",
    "conflict": "Details differ",
}

TRUST_HINTS: dict[TrustState, str] = {
    "verified": "We matched this listing against the official source page.",
    "aggregator_only": "Listed on an aggregator. We did not confirm it on an official page.",
    "unchecked": "We have not checked this against an official source yet.",
    "conflict": "The official page disagrees with the aggregator listing on key details.",
}


class TrustPresentation(TypedDict):
    state: TrustState
    label: str
    hint: str
    checked_at: Optional[datetime]
    primary_url: Optional[str]


def derive_trust_state(verification_status: Optional[str]) -> TrustState:
    raw = verification_status or VerificationStatus.unverified.value
    if raw == VerificationStatus.primary_confirmed.value:
        return "verified"
    if raw == VerificationStatus.aggregator_only.value:
        return "aggregator_only"
    if raw == VerificationStatus.stale.value:
        return "conflict"
    return "unchecked"


def build_trust_presentation(opp: Opportunity) -> TrustPresentation:
    state = derive_trust_state(opp.verification_status)
    meta = opp.verification_meta or {}
    primary_url = meta.get("primary_url") or None
    if primary_url and not isinstance(primary_url, str):
        primary_url = None

    return TrustPresentation(
        state=state,
        label=TRUST_LABELS[state],
        hint=TRUST_HINTS[state],
        checked_at=opp.verified_at,
        primary_url=primary_url,
    )

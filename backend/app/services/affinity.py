"""User feedback signals for ranking affinity (Task 3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from app.models import Opportunity, UserOpportunity, UserOpportunityStatus

STATUS_SIGNAL: dict[UserOpportunityStatus, float] = {
    UserOpportunityStatus.new: 0.5,
    UserOpportunityStatus.saved: 0.72,
    UserOpportunityStatus.in_progress: 0.88,
    UserOpportunityStatus.applied: 0.92,
    UserOpportunityStatus.archived: 0.25,
    UserOpportunityStatus.dismissed: 0.15,
}

POSITIVE_STATUSES = (
    UserOpportunityStatus.saved,
    UserOpportunityStatus.in_progress,
    UserOpportunityStatus.applied,
)

NEGATIVE_STATUSES = (
    UserOpportunityStatus.archived,
    UserOpportunityStatus.dismissed,
)


@dataclass
class AffinityProfile:
    """Aggregated positive/negative signals from user status history."""

    positive_tags: dict[str, float] = field(default_factory=dict)
    negative_tags: dict[str, float] = field(default_factory=dict)
    positive_institutions: dict[str, float] = field(default_factory=dict)
    negative_institutions: dict[str, float] = field(default_factory=dict)


def _positive_weight(status: UserOpportunityStatus) -> float:
    if status == UserOpportunityStatus.saved:
        return 0.6
    if status in (UserOpportunityStatus.in_progress, UserOpportunityStatus.applied):
        return 1.0
    return 0.0


def _negative_weight(uo: UserOpportunity) -> float:
    if uo.status == UserOpportunityStatus.archived:
        return 0.5
    if uo.status == UserOpportunityStatus.dismissed:
        return 0.85 if uo.dismiss_reason else 0.5
    return 0.0


def build_affinity_profile(
    rows: list[tuple[UserOpportunity, Opportunity]],
) -> AffinityProfile:
    profile = AffinityProfile()
    for uo, opp in rows:
        if uo.status in POSITIVE_STATUSES:
            weight = _positive_weight(uo.status)
            for tag in opp.tags or []:
                key = tag.lower().strip()
                if key:
                    profile.positive_tags[key] = profile.positive_tags.get(key, 0) + weight
            if opp.institution:
                inst = opp.institution.lower().strip()
                profile.positive_institutions[inst] = profile.positive_institutions.get(inst, 0) + weight
        elif uo.status in NEGATIVE_STATUSES:
            neg_weight = _negative_weight(uo)
            for tag in opp.tags or []:
                key = tag.lower().strip()
                if key:
                    profile.negative_tags[key] = profile.negative_tags.get(key, 0) + neg_weight
            if opp.institution:
                inst = opp.institution.lower().strip()
                profile.negative_institutions[inst] = profile.negative_institutions.get(inst, 0) + neg_weight
    return profile


def affinity_score(
    opportunity: Opportunity,
    user_opp: Optional[UserOpportunity],
    affinity_profile: AffinityProfile,
) -> float:
    """0–1 affinity from current status + learned tag/institution preferences."""
    base = STATUS_SIGNAL.get(
        user_opp.status if user_opp else UserOpportunityStatus.new,
        0.5,
    )
    boost = 0.0
    for tag in opportunity.tags or []:
        key = tag.lower().strip()
        if key in affinity_profile.positive_tags:
            boost += min(0.08, affinity_profile.positive_tags[key] * 0.04)
        if key in affinity_profile.negative_tags:
            boost -= min(0.06, affinity_profile.negative_tags[key] * 0.03)

    if opportunity.institution:
        inst = opportunity.institution.lower().strip()
        if inst in affinity_profile.positive_institutions:
            boost += min(0.1, affinity_profile.positive_institutions[inst] * 0.05)
        if inst in affinity_profile.negative_institutions:
            boost -= min(0.08, affinity_profile.negative_institutions[inst] * 0.04)

    return max(0.0, min(1.0, base + boost))


def append_status_history(
    uo: UserOpportunity,
    new_status: UserOpportunityStatus,
    *,
    at: Optional[datetime] = None,
    dismiss_reason: Optional[str] = None,
) -> None:
    history: list[dict[str, Any]] = list(uo.status_history or [])
    prev = uo.status.value if uo.status else None
    if prev == new_status.value and not dismiss_reason:
        return
    entry: dict[str, Any] = {
        "from": prev,
        "to": new_status.value,
        "at": (at or datetime.now(timezone.utc)).isoformat(),
    }
    if dismiss_reason:
        entry["dismiss_reason"] = dismiss_reason
    history.append(entry)
    uo.status_history = history[-50:]

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
    UserOpportunityStatus.archived: 0.25,
}


@dataclass
class AffinityProfile:
    """Aggregated positive/negative signals from user status history."""

    positive_tags: dict[str, float] = field(default_factory=dict)
    negative_tags: dict[str, float] = field(default_factory=dict)
    positive_institutions: dict[str, float] = field(default_factory=dict)
    negative_institutions: dict[str, float] = field(default_factory=dict)


def build_affinity_profile(
    rows: list[tuple[UserOpportunity, Opportunity]],
) -> AffinityProfile:
    profile = AffinityProfile()
    for uo, opp in rows:
        if uo.status in (UserOpportunityStatus.saved, UserOpportunityStatus.in_progress):
            weight = 1.0 if uo.status == UserOpportunityStatus.in_progress else 0.6
            for tag in opp.tags or []:
                key = tag.lower().strip()
                if key:
                    profile.positive_tags[key] = profile.positive_tags.get(key, 0) + weight
            if opp.institution:
                inst = opp.institution.lower().strip()
                profile.positive_institutions[inst] = profile.positive_institutions.get(inst, 0) + weight
        elif uo.status == UserOpportunityStatus.archived:
            for tag in opp.tags or []:
                key = tag.lower().strip()
                if key:
                    profile.negative_tags[key] = profile.negative_tags.get(key, 0) + 0.5
            if opp.institution:
                inst = opp.institution.lower().strip()
                profile.negative_institutions[inst] = profile.negative_institutions.get(inst, 0) + 0.5
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
) -> None:
    history: list[dict[str, Any]] = list(uo.status_history or [])
    prev = uo.status.value if uo.status else None
    if prev == new_status.value:
        return
    history.append(
        {
            "from": prev,
            "to": new_status.value,
            "at": (at or datetime.now(timezone.utc)).isoformat(),
        }
    )
    uo.status_history = history[-50:]

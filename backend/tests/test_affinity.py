"""Tests for feedback affinity scoring (Task 3)."""

from app.models import Opportunity, UserOpportunity, UserOpportunityStatus
from app.services.affinity import (
    affinity_score,
    append_status_history,
    build_affinity_profile,
)


def test_affinity_boosts_saved_tags():
    opp = Opportunity(title="AI fellowship", tags=["machine learning", "Germany"])
    saved_opp = Opportunity(title="Other", tags=["machine learning"], institution="TU Dresden")
    uo_saved = UserOpportunity(status=UserOpportunityStatus.saved)
    profile = build_affinity_profile([(uo_saved, saved_opp)])

    target = Opportunity(title="ML grant", tags=["machine learning"])
    score = affinity_score(target, None, profile)
    assert score > 0.5


def test_status_history_append():
    uo = UserOpportunity(status=UserOpportunityStatus.new)
    append_status_history(uo, UserOpportunityStatus.saved)
    uo.status = UserOpportunityStatus.saved
    assert len(uo.status_history) == 1
    assert uo.status_history[0]["to"] == "saved"
    append_status_history(uo, UserOpportunityStatus.saved)
    assert len(uo.status_history) == 1

"""Tests for feedback affinity scoring (Task 3)."""

from app.models import Opportunity, UserOpportunity, UserOpportunityStatus
from app.services.affinity import (
    affinity_score,
    append_status_history,
    build_affinity_profile,
    STATUS_SIGNAL,
)


def test_affinity_boosts_saved_tags():
    opp = Opportunity(title="AI fellowship", tags=["machine learning", "Germany"])
    saved_opp = Opportunity(title="Other", tags=["machine learning"], institution="Harbor State University")
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


def test_status_signal_applied_highest():
    assert STATUS_SIGNAL[UserOpportunityStatus.applied] > STATUS_SIGNAL[UserOpportunityStatus.saved]
    assert STATUS_SIGNAL[UserOpportunityStatus.dismissed] < STATUS_SIGNAL[UserOpportunityStatus.archived]


def test_dismissed_with_reason_stronger_negative():
    opp = Opportunity(title="Media fellowship", tags=["media"], institution="BBC")
    dismissed_silent = UserOpportunity(status=UserOpportunityStatus.dismissed)
    dismissed_reason = UserOpportunity(
        status=UserOpportunityStatus.dismissed,
        dismiss_reason="wrong_field",
    )
    profile_silent = build_affinity_profile([(dismissed_silent, opp)])
    profile_reason = build_affinity_profile([(dismissed_reason, opp)])

    target = Opportunity(title="Journalism grant", tags=["media"], institution="BBC")
    score_silent = affinity_score(target, None, profile_silent)
    score_reason = affinity_score(target, None, profile_reason)
    assert score_reason < score_silent


def test_applied_counts_as_positive_signal():
    opp = Opportunity(title="AI grant", tags=["machine learning"])
    uo = UserOpportunity(status=UserOpportunityStatus.applied)
    profile = build_affinity_profile([(uo, opp)])
    target = Opportunity(title="ML fellowship", tags=["machine learning"])
    assert affinity_score(target, None, profile) > 0.5


def test_status_history_records_dismiss_reason():
    uo = UserOpportunity(status=UserOpportunityStatus.new)
    append_status_history(uo, UserOpportunityStatus.dismissed, dismiss_reason="not_funded")
    uo.status = UserOpportunityStatus.dismissed
    assert uo.status_history[-1]["dismiss_reason"] == "not_funded"

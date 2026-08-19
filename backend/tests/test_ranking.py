"""Ranking, composite scoring, and eligibility evaluation tests."""

from datetime import datetime, timedelta, timezone

from app.models import FitLevel, Opportunity, OpportunityType, UserProfile
from app.services.embeddings import calibrate_cosine_similarity, lexical_similarity
from app.services.eligibility_scoring import evaluate_eligibility
from app.services.ranking import (
    build_score_breakdown,
    compute_composite,
    cosine_similarity,
    fit_level_from_score,
    urgency_score,
    STRONG_FIT_THRESHOLD,
    MODERATE_FIT_THRESHOLD,
)
from app.services.opportunities import _to_response
from app.models import UserOpportunity, UserOpportunityStatus


def test_cosine_similarity():
    a = [1.0, 0.0, 0.0]
    b = [1.0, 0.0, 0.0]
    assert cosine_similarity(a, b) == 1.0


def test_calibrate_cosine_similarity():
    assert calibrate_cosine_similarity(0.55) == 1.0
    assert calibrate_cosine_similarity(0.15) == 0.0
    assert abs(calibrate_cosine_similarity(0.35) - 0.5) < 0.01


def test_lexical_similarity_nonzero():
    score = lexical_similarity("machine learning nlp", "fellowship in machine learning research")
    assert score > 0.15


def test_fit_level_thresholds():
    assert fit_level_from_score(STRONG_FIT_THRESHOLD) == FitLevel.strong
    assert fit_level_from_score(MODERATE_FIT_THRESHOLD) == FitLevel.moderate
    assert fit_level_from_score(0.3) == FitLevel.weak


def test_fit_level_hard_eligibility_caps_strong():
    assert fit_level_from_score(0.9, hard_eligibility_failed=True) == FitLevel.moderate
    assert fit_level_from_score(0.35, hard_eligibility_failed=True) == FitLevel.weak


def test_urgency_score_no_deadline():
    assert urgency_score(None) == 0.0


def test_urgency_score_soon():
    soon = datetime.now(timezone.utc) + timedelta(days=3)
    assert urgency_score(soon) == 1.0


def test_compute_composite_renormalizes_when_urgency_missing():
    composite, applied = compute_composite(
        {
            "semantic": (0.8, True),
            "eligibility": (0.7, True),
            "urgency": (0.0, False),
            "affinity": (0.6, True),
        }
    )
    assert "urgency" not in applied
    assert applied["semantic"] == 0.45
    expected = (0.8 * 0.45 + 0.7 * 0.30 + 0.6 * 0.10) / (0.45 + 0.30 + 0.10)
    assert abs(composite - expected) < 0.001


def test_compute_composite_excludes_missing_semantic():
    composite, applied = compute_composite(
        {
            "semantic": (0.0, False),
            "eligibility": (0.6, True),
            "urgency": (0.5, True),
            "affinity": (0.5, True),
        }
    )
    assert "semantic" not in applied
    assert composite > 0


def test_build_score_breakdown_records_components():
    bd = build_score_breakdown(
        0.6,
        0.7,
        0.8,
        0.65,
        0.62,
        semantic_raw=0.42,
        semantic_method="cosine",
        components_available=["semantic", "eligibility", "affinity"],
        weights_applied={"semantic": 0.45, "eligibility": 0.30, "affinity": 0.10},
        eligibility_reasons=[{"code": "degree_match", "label": "Open", "direction": "positive", "weight": 0.12}],
        hard_eligibility_failed=False,
    )
    assert bd["semantic_method"] == "cosine"
    assert "urgency" not in bd["components_available"]
    assert bd["eligibility_reasons"][0]["code"] == "degree_match"


def test_eligibility_phd_only_hard_fail_for_msc():
    profile = UserProfile(
        user_id="u1",
        name="Test",
        degree_level="MSc",
        research_interests=["AI"],
        target_regions=[],
        target_universities=[],
        constraints={"target_degree": "MSc"},
    )
    opp = Opportunity(
        title="PhD only fellowship",
        url="https://example.com/p",
        opportunity_type=OpportunityType.fellowship,
        degree_levels=["phd"],
        summary="PhD only doctoral program",
    )
    ev = evaluate_eligibility(profile, opp, {"require_funding": "full_only", "nationality": "Nepal"})
    assert ev.hard_failed
    assert any(r.code == "degree_mismatch" for r in ev.reasons)


def test_eligibility_us_citizens_hard_fail():
    profile = UserProfile(
        user_id="u1",
        name="Test",
        degree_level="MSc",
        research_interests=[],
        target_regions=[],
        target_universities=[],
        constraints={},
    )
    opp = Opportunity(
        title="Grant",
        url="https://example.com/g",
        opportunity_type=OpportunityType.scholarship,
        summary="US citizens only may apply",
    )
    ev = evaluate_eligibility(
        profile,
        opp,
        {"require_funding": "full_only", "nationality": "Nepal", "reject_if_text_contains": []},
    )
    assert ev.hard_failed
    assert any(r.code == "us_citizens_only" for r in ev.reasons)


def test_eligibility_positive_degree_match():
    profile = UserProfile(
        user_id="u1",
        name="Test",
        degree_level="MSc",
        research_interests=[],
        target_regions=[],
        target_universities=[],
        constraints={"target_degree": "MSc"},
    )
    opp = Opportunity(
        title="Masters scholarship",
        url="https://example.com/m",
        opportunity_type=OpportunityType.scholarship,
        degree_levels=["master"],
    )
    ev = evaluate_eligibility(profile, opp, {"require_funding": "full_only"})
    assert not ev.hard_failed
    assert any(r.code == "degree_match" for r in ev.reasons)


def test_fit_percent_in_response():
    opp = Opportunity(
        id="opp-test-1",
        title="Test",
        url="https://example.com/t",
        opportunity_type=OpportunityType.scholarship,
    )
    uo = UserOpportunity(
        user_id="p1",
        opportunity_id=opp.id,
        status=UserOpportunityStatus.new,
        fit_score=0.673,
    )
    resp = _to_response(opp, uo)
    assert resp.fit_percent == 67
    assert 0 <= resp.fit_percent <= 100
    assert resp.fit_percent == round(resp.fit_score * 100)

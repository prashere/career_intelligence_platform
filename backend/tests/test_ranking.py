"""Ranking, composite scoring, and eligibility evaluation tests."""

from datetime import datetime, timedelta, timezone

from app.models import FitLevel, Opportunity, OpportunityType, UserProfile
from app.services.embeddings import (
    calibrate_cosine_similarity,
    lexical_similarity,
    matched_terms,
)
from app.services.eligibility_scoring import EligibilityEvaluation, evaluate_eligibility
from app.services.opportunity_facts import apply_facts_to_opportunity, derive_facts
from app.services.ranking import (
    build_fit_reasons,
    build_score_breakdown,
    compute_composite,
    cosine_similarity,
    fit_level_from_score,
    NEUTRAL_FIT_REASON,
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
    ev = evaluate_eligibility(profile, opp, {"require_funding": "full_only", "nationality": "Canada"})
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
        {"require_funding": "full_only", "nationality": "Canada", "reject_if_text_contains": []},
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
        score_breakdown={
            "reasons": [{"code": "interest_match", "label": "Matches AI", "direction": "positive"}],
            "hide_match_percent": False,
        },
    )
    resp = _to_response(opp, uo)
    assert resp.fit_percent == 67
    assert resp.trust.state == "unchecked"
    assert resp.deadline_bucket == "unknown"
    assert 0 <= resp.fit_percent <= 100
    assert resp.fit_percent == round(resp.fit_score * 100)


def test_fit_percent_hidden_without_reasons():
    opp = Opportunity(
        id="opp-test-2",
        title="Test",
        url="https://example.com/t2",
        opportunity_type=OpportunityType.scholarship,
    )
    uo = UserOpportunity(
        user_id="p1",
        opportunity_id=opp.id,
        status=UserOpportunityStatus.new,
        fit_score=0.5,
        score_breakdown={"reasons": [], "hide_match_percent": True},
        fit_explanation="Not enough information to explain this match",
    )
    resp = _to_response(opp, uo)
    assert resp.fit_percent is None
    assert resp.fit_score is None


# --- Derived facts -------------------------------------------------------


def _opp(title="Test fellowship", summary="", **kwargs):
    return Opportunity(
        id=kwargs.pop("id", "opp-facts"),
        title=title,
        url=kwargs.pop("url", "https://example.com/f"),
        opportunity_type=kwargs.pop("opportunity_type", OpportunityType.fellowship),
        summary=summary,
        **kwargs,
    )


def test_derive_facts_parses_deadline_from_text():
    facts = derive_facts(_opp(summary="Deadline: August 24, 2026\nApplications are open."))
    assert facts.deadline is not None
    assert facts.deadline.year == 2026 and facts.deadline.month == 8
    assert facts.deadline_source == "text"


def test_derive_facts_detects_rolling_and_unspecified():
    assert derive_facts(_opp(summary="Deadline: On Rolling Basis")).deadline_note == "rolling"
    assert derive_facts(_opp(summary="Deadline: Unspecified")).deadline_note == "unspecified"


def test_derive_facts_detects_funding_and_themes():
    facts = derive_facts(
        _opp(summary="This is a fully funded fellowship in machine learning worth $30,000.")
    )
    assert facts.funding_type == "full"
    assert facts.funding_amount is not None
    assert "artificial intelligence" in facts.themes


def test_derive_facts_recovers_degree_and_region():
    facts = derive_facts(
        _opp(summary="Open to Master's students based in Germany and across Europe.")
    )
    assert "master" in facts.degree_levels
    assert "Europe" in facts.regions


def test_apply_facts_backfills_only_empty_columns():
    opp = _opp(summary="Deadline: March 3, 2027. A fully funded programme.", funding_type="partial")
    facts = derive_facts(opp)
    written = apply_facts_to_opportunity(opp, facts)
    assert "deadline" in written
    # An existing column value is never overwritten.
    assert "funding_type" not in written
    assert opp.funding_type == "partial"


def test_matched_terms_returns_evidence():
    hits = matched_terms(
        ["machine learning", "climate policy", "underwater basket weaving"],
        "A fellowship in machine learning and climate policy research",
    )
    assert "machine learning" in hits
    assert "underwater basket weaving" not in hits


# --- Reason floor --------------------------------------------------------


def _empty_eval():
    return EligibilityEvaluation(score=0.5, reasons=[], hard_failed=False)


def test_reasons_never_empty_for_a_listing_with_text():
    """A card must always carry at least one explanation."""
    profile = UserProfile(user_id="u1", name="T", research_interests=[], target_regions=[])
    opp = _opp(summary="A programme for early career professionals.")
    facts = derive_facts(opp)

    reasons, summary, hide = build_fit_reasons(
        profile, opp, 0.0, False, None, _empty_eval(), False, 0.5, facts=facts
    )

    assert reasons, "expected at least one reason"
    assert summary != NEUTRAL_FIT_REASON
    assert hide is False


def test_missing_deadline_is_stated_not_silently_dropped():
    profile = UserProfile(user_id="u1", name="T", research_interests=[], target_regions=[])
    opp = _opp(summary="A programme with no date given.")
    reasons, _, _ = build_fit_reasons(
        profile, opp, 0.2, True, "lexical", _empty_eval(), False, 0.5, facts=derive_facts(opp)
    )
    assert any(r["code"] == "deadline_missing" for r in reasons)


def test_lexical_method_is_not_reported_as_unavailable():
    """Keyword matching is a real signal and must not claim similarity is unavailable."""
    profile = UserProfile(user_id="u1", name="T", research_interests=[], target_regions=[])
    opp = _opp(summary="Machine learning fellowship.")
    reasons, _, _ = build_fit_reasons(
        profile, opp, 0.4, True, "lexical", _empty_eval(), False, 0.5, facts=derive_facts(opp)
    )
    codes = {r["code"] for r in reasons}
    assert "semantic_keyword_only" in codes
    assert "semantic_unavailable" not in codes


def test_evidence_terms_appear_in_reason_label():
    profile = UserProfile(user_id="u1", name="T", research_interests=[], target_regions=[])
    opp = _opp(summary="Machine learning fellowship.")
    reasons, _, _ = build_fit_reasons(
        profile,
        opp,
        0.6,
        True,
        "cosine",
        _empty_eval(),
        False,
        0.5,
        facts=derive_facts(opp),
        evidence_terms=["machine learning"],
    )
    semantic = next(r for r in reasons if r["code"] == "semantic_strong")
    assert "machine learning" in semantic["label"]


def test_unknown_fields_produce_neutral_reasons():
    profile = UserProfile(
        user_id="u1",
        name="T",
        degree_level="MSc",
        research_interests=[],
        target_regions=[],
        constraints={"target_degree": "MSc"},
    )
    opp = _opp(summary="A short listing with no stated requirements.")
    ev = evaluate_eligibility(profile, opp, {"require_funding": "full_only"})
    codes = {r.code for r in ev.reasons}
    assert "degree_unknown" in codes
    assert "funding_unknown" in codes

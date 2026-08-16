"""Tests for the evidence-based relevance gate."""

import pytest

from app.ingestion.relevance import Candidate, Verdict, evaluate, profile_terms_from_envelope
from app.ingestion.relevance.text import find_amounts, find_terms, normalize

# A compiled profile with narrow disciplines and regions — the exact shape that
# made the old conjunctive prefilter reject almost everything.
NARROW_ENVELOPE = {
    "must_match_any": ["MSc", "master", "scholarship", "fellowship", "fully funded", "stipend", "tuition"],
    "profile_match_any": ["computer science", "machine learning", "data science", "artificial intelligence"],
    "region_match_any": ["Germany", "German", "DAAD", "Europe", "European", "EU"],
    "hard_drop_any": ["webinar only", "conference registration", "high school"],
    "target_degree_levels": ["MSc"],
}


@pytest.fixture
def narrow_profile():
    return profile_terms_from_envelope(NARROW_ENVELOPE)


def verdict_for(title, *, url="", summary="", content="", regions=None, profile=None, detail=False):
    return evaluate(
        Candidate(
            url=url,
            title=title,
            summary=summary,
            content=content,
            source_regions=regions or [],
            detail_fetched=detail,
        ),
        profile=profile,
    )


class TestTextMatching:
    def test_normalize_strips_accents_and_punctuation(self):
        assert normalize("Fully-Funded Scholarship (2026)!") == "fully-funded scholarship 2026"

    def test_word_boundary_prevents_substring_false_positives(self):
        # The old filter matched "ai" inside "chair" and "ms" inside "programs".
        assert find_terms(["ai"], normalize("Department chair announcement")) == []
        assert find_terms(["ms"], normalize("Our programs are open")) == []

    def test_word_boundary_still_matches_real_terms(self):
        assert find_terms(["ai"], normalize("Advances in AI research")) == ["ai"]

    def test_multiword_terms_tolerate_hyphens(self):
        assert find_terms(["fully funded"], normalize("A fully-funded position")) == ["fully funded"]

    def test_amounts_are_detected(self):
        assert find_amounts("Award up to $10,000 per year") == ["$10,000"]
        assert find_amounts("Worth €5.000 annually") == ["€5.000"]


class TestRegressionCases:
    def test_endeavour_women_in_tech_is_admitted(self, narrow_profile):
        """The reported bug: a clearly valid scholarship was rejected.

        Its title names no discipline from the profile and no region, which the
        old conjunctive prefilter treated as two separate hard failures.
        """
        decision = verdict_for(
            "Endeavour Women in Tech Scholarship 2026 (up to $10,000)",
            url="https://bold.org/scholarships/endeavour-women-in-tech/",
            regions=["us"],
            profile=narrow_profile,
        )
        assert decision.verdict is Verdict.admit
        assert "opportunity_type" in decision.matched_signals()
        assert decision.signals["funding"].matched

    def test_title_without_region_is_never_rejected_for_region(self, narrow_profile):
        decision = verdict_for(
            "Rhodes Scholarship for Graduate Study",
            url="https://example.org/scholarships/rhodes",
            profile=narrow_profile,
        )
        assert decision.verdict is not Verdict.reject

    def test_title_without_discipline_is_never_rejected_for_discipline(self, narrow_profile):
        decision = verdict_for(
            "Fully Funded Fellowship for Emerging Leaders",
            url="https://example.org/fellowships/leaders",
            profile=narrow_profile,
        )
        assert decision.verdict is not Verdict.reject

    def test_registry_regions_supply_missing_region_evidence(self, narrow_profile):
        decision = verdict_for(
            "Postgraduate Funding Programme",
            url="https://example.org/x",
            regions=["Germany"],
            profile=narrow_profile,
        )
        assert decision.signals["region"].matched
        assert decision.signals["region"].found_in == "registry"

    def test_synonym_expansion_links_tech_to_technology(self, narrow_profile):
        profile = profile_terms_from_envelope({**NARROW_ENVELOPE, "profile_match_any": ["technology"]})
        decision = verdict_for("Women in Tech Scholarship", profile=profile)
        assert decision.signals["discipline"].matched


class TestDeferral:
    def test_sparse_unknown_title_is_investigated_not_rejected(self, narrow_profile):
        decision = verdict_for("Endeavour Award", url="https://example.org/e/12345", profile=narrow_profile)
        assert decision.verdict is Verdict.investigate
        assert decision.reason in ("needs_detail_for_application", "ambiguous_listing_title")

    def test_same_item_rejects_once_full_text_shows_nothing(self, narrow_profile):
        decision = verdict_for(
            "Endeavour Award",
            url="https://example.org/e/12345",
            content=(
                "Our company hands out an internal recognition badge to staff members "
                "each quarter. There is nothing to apply for and no money involved. " * 12
            ),
            detail=True,
            profile=narrow_profile,
        )
        assert decision.verdict is Verdict.reject
        assert decision.sufficiency == 1.0

    def test_detail_text_can_rescue_a_sparse_title(self, narrow_profile):
        decision = verdict_for(
            "Programme 2026",
            url="https://example.org/p/2026",
            content=(
                "This fully funded scholarship covers tuition and a monthly stipend "
                "for master students. Application deadline is 30 April 2026. "
                "Eligibility: open to international applicants."
            ),
            detail=True,
            profile=narrow_profile,
        )
        assert decision.verdict is Verdict.admit


class TestNegatives:
    def test_boilerplate_titles_are_rejected(self, narrow_profile):
        for title in ("About Us", "Privacy Policy", "Terms of Service"):
            decision = verdict_for(title, url="https://example.org/x", profile=narrow_profile)
            assert decision.verdict is Verdict.reject, title

    def test_closed_opportunity_is_rejected(self, narrow_profile):
        decision = verdict_for(
            "Global Youth Prize — winners announced",
            url="https://example.org/news/winners",
            profile=narrow_profile,
        )
        assert decision.verdict is Verdict.reject
        assert decision.reason.startswith("hard_negative")

    def test_footer_boilerplate_does_not_reject_a_real_opportunity(self, narrow_profile):
        """Negatives are scoped to title and summary for this reason."""
        decision = verdict_for(
            "Fully Funded MSc Scholarship in Computer Science",
            url="https://example.org/scholarships/msc-cs",
            content="Apply by 1 March. Read our privacy policy and terms of service. About us: we fund students.",
            detail=True,
            profile=narrow_profile,
        )
        assert decision.verdict is Verdict.admit

    def test_profile_hard_drop_still_applies(self, narrow_profile):
        decision = verdict_for(
            "High School Scholarship Program",
            url="https://example.org/scholarships/hs",
            profile=narrow_profile,
        )
        assert decision.verdict is Verdict.reject


class TestScoring:
    def test_no_profile_still_admits_clear_opportunities(self):
        decision = verdict_for(
            "Fully Funded PhD Scholarship, apply by 1 June",
            url="https://example.org/phd",
        )
        assert decision.verdict is Verdict.admit

    def test_fit_signals_raise_but_never_gate(self, narrow_profile):
        without_fit = verdict_for(
            "Scholarship Programme 2026",
            url="https://example.org/s",
            profile=narrow_profile,
        )
        with_fit = verdict_for(
            "Scholarship Programme 2026 in Machine Learning, Germany",
            url="https://example.org/s",
            profile=narrow_profile,
        )
        assert with_fit.score > without_fit.score
        assert without_fit.verdict is not Verdict.reject

    def test_decision_serializes_evidence(self, narrow_profile):
        decision = verdict_for(
            "Endeavour Women in Tech Scholarship 2026 (up to $10,000)",
            url="https://bold.org/scholarships/x",
            profile=narrow_profile,
        )
        payload = decision.to_dict()
        assert payload["verdict"] == "admit"
        assert payload["evidence"]
        assert payload["signals"]["opportunity_type"]["matched"] is True

    def test_type_label_is_detected(self, narrow_profile):
        decision = verdict_for("Chevening Scholarship 2026", profile=narrow_profile)
        assert decision.type_label == "scholarship"


class TestEditorialRejection:
    """Listicles, field roundups, and reviews must reject — not admit or investigate."""

    def test_civil_engineering_programs_roundup(self, narrow_profile):
        decision = verdict_for(
            "Fully Funded Master's Programs in Civil Engineering",
            url="https://www.profellow.com/fellowships/fully-funded-masters-programs-in-civil-engineering/",
            profile=narrow_profile,
        )
        assert decision.verdict is Verdict.reject
        assert decision.reason.startswith("editorial")

    def test_top_fellowships_listicle(self, narrow_profile):
        decision = verdict_for(
            "Top Technology Policy Fellowships in 2026 for Students, Professionals, and Scholars",
            url="https://www.profellow.com/fellowships/top-technology-policy-fellowships-in-2026-for-students-professionals-and-scholars/",
            profile=narrow_profile,
        )
        assert decision.verdict is Verdict.reject
        assert decision.signals["editorial"].matched

    def test_quick_apply_scholarships_hub(self, narrow_profile):
        decision = verdict_for(
            "Top 110 Quick Apply Scholarships from Scholarships360 in August 2026",
            url="https://scholarships360.org/scholarships/quick-apply-scholarships/",
            profile=narrow_profile,
        )
        assert decision.verdict is Verdict.reject

    def test_easy_scholarships_listicle(self, narrow_profile):
        decision = verdict_for(
            "Top 36 Easy Scholarships to Apply For in December 2025",
            url="https://scholarships360.org/?p=178435",
            profile=narrow_profile,
        )
        assert decision.verdict is Verdict.reject

    def test_test_page_rejected(self, narrow_profile):
        decision = verdict_for(
            "Test page",
            url="https://scholarships360.org/?p=181292",
            profile=narrow_profile,
        )
        assert decision.verdict is Verdict.reject

    def test_reviews_page_rejected(self, narrow_profile):
        decision = verdict_for(
            "Bold.org Reviews — What students say",
            url="https://bold.org/reviews/",
            profile=narrow_profile,
        )
        assert decision.verdict is Verdict.reject

    def test_application_only_without_opportunity_signal_rejects(self, narrow_profile):
        """Deadline language on non-opportunity pages should not trigger investigate."""
        decision = verdict_for(
            "Newsletter signup",
            summary="Applications are open for our monthly digest.",
            url="https://example.org/newsletter",
            profile=narrow_profile,
        )
        assert decision.verdict is Verdict.reject


class TestInvestigateOnlyWhenPlausible:
    def test_sparse_named_award_investigates(self, narrow_profile):
        decision = verdict_for("Endeavour Award", url="https://example.org/e/12345", profile=narrow_profile)
        assert decision.verdict is Verdict.investigate

    def test_named_program_with_application_in_feed_investigates(self, narrow_profile):
        decision = verdict_for(
            "Commonwealth Youth Council (CYC) One Country, One Project 2026",
            summary="Applications are open. Deadline 30 September.",
            url="https://example.org/cyc-project-2026/",
            profile=narrow_profile,
        )
        assert decision.verdict is Verdict.investigate
        assert decision.reason in ("needs_detail_for_application", "ambiguous_listing_title")

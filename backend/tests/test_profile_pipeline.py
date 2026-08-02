"""Tests for profile pipeline — prefill, merge, compile."""

from app.services.profile_intake import validate_structured_profile
from app.services.profile_pipeline import (
    merge_prefill_and_extraction,
    prefill_from_form,
    score_aggregators,
)

SAMPLE_FORM = {
    "full_name": "Test User",
    "nationality_code": "NP",
    "current_country_code": "NP",
    "linkedin_url": "https://linkedin.com/in/test",
    "github_url": "",
    "target_degree": "MSc",
    "program_style": "research_aligned",
    "target_intake_term": "Fall 2027",
    "funding_requirement": "full_only",
    "target_regions": ["Germany", "Europe", "UK"],
    "target_countries_priority": ["Germany"],
    "target_fields": ["robotics", "computer vision", "HRI"],
    "developing_country_scholarships": True,
    "search_sources": ["Scholars4Dev", "DAAD"],
    "degree_level": "BSc / BA / BE",
    "field_of_study": "Computer Science",
    "institution": "Test University",
    "graduation_month": "December",
    "graduation_year": "2025",
    "gpa": "85",
    "gpa_scale": "100",
    "honors": "First Class",
    "english_test": "IELTS",
    "english_score": "8.0",
    "english_test_date": "2025-11-19",
    "anti_goals": ["unpaid_internships", "non_stem"],
}

SAMPLE_EXTRACTION = {
    "experiences": [
        {
            "role": "ML Engineer",
            "organization": "Test Co",
            "highlights": ["Built APIs"],
            "is_technical": True,
            "is_research": False,
        }
    ],
    "search_keywords": [
        "msc",
        "robotics",
        "scholarship",
        "fellowship",
        "fully funded",
        "germany",
        "daad",
        "computer vision",
        "hri",
        "international",
        "graduate",
        "master",
        "stipend",
        "research",
        "europe",
    ],
    "extraction_meta": {"confidence": "high", "fields_needing_review": []},
}


def test_prefill_includes_identity_and_sources():
    data = prefill_from_form(SAMPLE_FORM)
    assert data["identity"]["full_name"] == "Test User"
    assert data["identity"]["nationality"] == "NP"
    assert data["preferences"]["target_degree"] == "MSc"
    assert len(data["sources"]["aggregators"]) == 4
    ids = [a["id"] for a in data["sources"]["aggregators"]]
    assert "scholars4dev" in ids
    assert "daad" in ids


def test_select_aggregators_prefers_user_chips():
    scored = score_aggregators(SAMPLE_FORM)
    top_ids = [s["id"] for s in scored[:4]]
    assert "scholars4dev" in top_ids
    assert "daad" in top_ids


def test_merge_prefill_and_extraction():
    prefill = prefill_from_form(SAMPLE_FORM)
    merged = merge_prefill_and_extraction(prefill, SAMPLE_EXTRACTION)
    assert merged["identity"]["full_name"] == "Test User"
    assert len(merged["experiences"]) == 1
    assert len(merged["search_keywords"]) >= 10
    profile, errors = validate_structured_profile(merged)
    assert profile is not None, errors

"""Tests for profile pipeline — prefill, merge, compile."""

from app.services.profile_intake import validate_structured_profile
from app.services.profile_pipeline import (
    compile_profile,
    merge_prefill_and_extraction,
    prefill_from_form,
    score_aggregators,
)

SAMPLE_FORM = {
    "full_name": "Test User",
    "nationality_code": "CA",
    "current_country_code": "CA",
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
    "search_sources": ["Opportunity Desk", "ProFellow", "LinkedIn"],
    "target_universities": "Harbor State University, Northhaven Institute",
    "discovery_mode": "target_list",
    "open_to_relocation": True,
    "other_languages": ["German"],
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
    assert data["identity"]["nationality"] == "CA"
    assert data["preferences"]["target_degree"] == "MSc"
    assert data["preferences"]["discovery_mode"] == "target_list"
    assert data["preferences"]["other_languages"] == ["German"]
    assert data["preferences"]["target_universities"] == ["Harbor State University", "Northhaven Institute"]
    assert len(data["sources"]["aggregators"]) == 4
    assert "LinkedIn" in data["sources"]["manual_channels"]
    ids = [a["id"] for a in data["sources"]["aggregators"]]
    assert "opportunitydesk" in ids
    assert "profellow" in ids


def test_select_aggregators_prefers_user_chips():
    scored = score_aggregators(SAMPLE_FORM)
    top_ids = [s["id"] for s in scored[:4]]
    assert "opportunitydesk" in top_ids
    assert "profellow" in top_ids


def test_fellowship_scoring_boosts_profellow():
    form = {**SAMPLE_FORM, "target_degree": "Fellowship", "search_sources": []}
    scored = score_aggregators(form)
    profellow = next(s for s in scored if s["id"] == "profellow")
    assert "fellowship_focus" in profellow["reasons"]


def test_merge_prefill_and_extraction():
    prefill = prefill_from_form(SAMPLE_FORM)
    merged = merge_prefill_and_extraction(prefill, SAMPLE_EXTRACTION)
    assert merged["identity"]["full_name"] == "Test User"
    assert len(merged["experiences"]) == 1
    assert len(merged["search_keywords"]) >= 10
    assert len(merged["sources"]["aggregators"]) == 4
    profile, errors = validate_structured_profile(merged)
    assert profile is not None, errors
    assert profile.sources.manual_channels == ["LinkedIn"]
    assert profile.preferences.discovery_mode.value == "target_list"


def test_normalize_extraction_coerces_string_list_items():
    from app.services.profile_pipeline import normalize_extraction_output

    raw = {
        "experiences": ["Research intern at AI Lab"],
        "awards": ["Dean's List 2024"],
        "certifications": ["IELTS 8.0"],
        "skills": ["Python", "PyTorch"],
        "search_keywords": ["phd", "robotics"],
        "extraction_meta": {"confidence": "medium", "fields_needing_review": []},
    }
    out = normalize_extraction_output(raw)
    assert out["awards"][0]["title"] == "Dean's List 2024"
    assert out["certifications"][0]["name"] == "IELTS 8.0"
    assert out["experiences"][0]["role"] == "Research intern at AI Lab"


def test_compile_profile_writes_l3_artifacts(tmp_path, monkeypatch):
    from app.services import profile_pipeline as pipeline

    prefill = prefill_from_form(SAMPLE_FORM)
    merged = merge_prefill_and_extraction(prefill, SAMPLE_EXTRACTION)
    profile, errors = validate_structured_profile(merged)
    assert profile is not None, errors

    out_dir = tmp_path / "compiled"
    truth_path = tmp_path / "profile-truth.md"

    monkeypatch.setattr(pipeline, "compiled_dir", lambda: out_dir)
    monkeypatch.setattr(pipeline, "_profile_truth_path", lambda: truth_path)

    paths = compile_profile(profile)

    ing = (out_dir / "ingestion_sources.json").read_text(encoding="utf-8")
    assert "opportunitydesk" in ing
    assert "profellow" in ing

    fc = __import__("json").loads((out_dir / "filter_config.json").read_text(encoding="utf-8"))
    assert fc["discovery_mode"] == "target_list"
    assert "Harbor State University" in fc["institution_match_any"]

    rc = __import__("json").loads((out_dir / "ranking_config.json").read_text(encoding="utf-8"))
    assert rc["university_match_weight"] == 0.35
    assert rc["manual_channels"] == ["LinkedIn"]

    assert paths["profile_truth"].exists()

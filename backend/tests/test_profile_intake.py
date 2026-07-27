"""Tests for profile intake prompt assembly."""

import json

from app.services.profile_intake import (
    build_extraction_prompt,
    form_answers_to_markdown,
    validate_structured_profile,
)


def test_form_answers_to_markdown_includes_goals():
    form = {
        "full_name": "Test User",
        "nationality": "NP",
        "target_degree": "MSc",
        "target_intake_term": "Fall 2027",
        "funding_requirement": "full_only",
        "target_regions": ["Germany", "UK"],
        "target_fields": ["robotics", "computer vision", "HRI"],
        "anti_goals": ["unpaid_internships"],
    }
    md = form_answers_to_markdown(form)
    assert "Test User" in md
    assert "Fall 2027" in md
    assert "robotics" in md


def test_build_extraction_prompt_substitutes_placeholders():
    form = {
        "full_name": "Test User",
        "nationality": "NP",
        "current_country": "Nepal",
        "linkedin_url": "https://linkedin.com/in/test",
        "target_degree": "MSc",
        "program_style": "research_aligned",
        "target_intake_term": "Fall 2027",
        "funding_requirement": "full_only",
        "target_regions": ["Germany"],
        "target_fields": ["robotics", "computer vision", "HRI"],
        "anti_goals": [],
    }
    cv = "Test User\nBSc Computer Science\nTellO robotics project"
    prompt = build_extraction_prompt(form, cv)
    assert "{{FORM_ANSWERS}}" not in prompt
    assert "{{CV_TEXT}}" not in prompt
    assert "TellO robotics project" in prompt
    assert "Test User" in prompt
    assert "Produce the JSON now" in prompt


def test_validate_example_structured_profile():
    path = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "docs"
        / "profile"
        / "intake"
        / "example-structured-profile.json"
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    profile, errors = validate_structured_profile(data)
    assert profile is not None
    assert not errors
    assert profile.identity.full_name == "Prashidika Tiwari"

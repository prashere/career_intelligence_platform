"""Tests for profile intake prompt assembly."""

from app.services.profile_intake import form_answers_to_markdown


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

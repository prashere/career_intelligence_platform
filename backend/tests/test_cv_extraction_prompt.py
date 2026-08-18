"""Tests for embedded CV extraction prompts."""

from app.prompts.cv_extraction import build_cv_extraction_user_prompt
from app.services.profile_pipeline import build_cv_extraction_prompt


def test_build_cv_extraction_prompt_without_markdown_file():
    prefill = {
        "identity": {"full_name": "Test"},
        "preferences": {"target_degree": "MSc", "target_fields": ["robotics"]},
    }
    prompt = build_cv_extraction_prompt(prefill, "Built ML systems at university lab.")
    assert "MSc" in prompt
    assert "robotics" in prompt
    assert "search_keywords" in prompt
    assert "llm-cv-extraction-prompt.md" not in prompt
    assert len(prompt) > 500


def test_build_cv_extraction_user_prompt_truncates_long_cv():
    prefill = {"identity": {"full_name": "A"}, "preferences": {"target_degree": "MSc"}}
    long_cv = "x" * 20000
    prompt = build_cv_extraction_user_prompt(prefill, long_cv)
    assert "truncated" in prompt.lower()
    assert len(prompt) < 12000


def test_prefill_summary_omits_heavy_prefill_fields():
    prefill = {
        "preferences": {"target_degree": "PhD", "target_fields": ["ml"]},
        "education": [{"degree_level": "BSc", "field": "CS", "institution": "Uni"}],
        "sources": {"aggregators": [{"id": "x", "name": "big", "enabled": True}]},
    }
    prompt = build_cv_extraction_user_prompt(prefill, "short cv")
    assert "aggregators" not in prompt
    assert "PhD" in prompt

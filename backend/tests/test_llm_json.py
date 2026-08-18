"""Tests for LLM JSON parsing and salvage."""

import json

from app.services.llm_json import parse_llm_json, salvage_json_object


def test_parse_llm_json_plain_object():
    data = parse_llm_json('{"skills": ["python"], "search_keywords": ["ml"]}')
    assert data["skills"] == ["python"]


def test_parse_llm_json_with_fences():
    raw = """```json
{"experiences": [], "search_keywords": ["phd"]}
```"""
    data = parse_llm_json(raw)
    assert "search_keywords" in data


def test_salvage_truncated_string():
    truncated = (
        '{"experiences": [{"role": "Engineer", "organization": "Lab", '
        '"highlights": ["Built systems for distributed'
    )
    salvaged = salvage_json_object(truncated)
    assert salvaged is not None
    assert salvaged["experiences"][0]["role"] == "Engineer"


def test_parse_llm_json_raises_on_garbage():
    try:
        parse_llm_json("not json at all")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "invalid json" in str(exc).lower()

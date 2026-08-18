"""CV extraction prompts — compact for Groq free-tier TPM limits."""

from __future__ import annotations

import json
from typing import Any

from app.config import settings

CV_EXTRACTION_SYSTEM = (
    "Extract CV facts into JSON only. No markdown. No invented employers or papers. "
    "Graduate opportunity matching (MSc/PhD/fellowships)."
)

CV_EXTRACTION_USER_TEMPLATE = """Extract CV-only fields as one JSON object. Form prefill already has identity, preferences, and highest education.

## Form context (do not copy into output)
{{PREFILL_SUMMARY}}

## CV
{{CV_TEXT}}

## Rules
- Output JSON only. Keys: experiences, publications, projects, skills, awards, certifications, connections, search_keywords, education, preferences, extraction_meta.
- Omit identity, sources, schema_version. No is_highest=true education entries.
- search_keywords: 15+ lowercase distinct terms (degree, field, regions, funding, skills).
- experiences: role, organization, optional dates/location, highlights (max 3 short strings), is_technical, is_research.
- extraction_meta: confidence (high|medium|low), fields_needing_review[], optional notes.
- preferences may only include long_term_direction (optional string).
- Empty arrays [] for missing sections. Keep strings short.

## Schema
{"experiences":[],"publications":[],"projects":[],"skills":[],"awards":[],"certifications":[],"connections":[],"search_keywords":[],"education":[],"preferences":{"long_term_direction":null},"extraction_meta":{"confidence":"medium","fields_needing_review":[],"notes":null}}"""


CV_REPAIR_SYSTEM = "Fix extraction JSON for schema validation. JSON only, no markdown."

CV_REPAIR_USER_TEMPLATE = """Fix this extraction JSON. CV-derived fields only (no identity/full preferences).

Errors:
{{ERRORS}}

Partial JSON:
{{PARTIAL_JSON}}

Form context:
{{PREFILL_SUMMARY}}

CV excerpt:
{{CV_TEXT}}

Return corrected JSON. search_keywords >= 15. education entries must have is_highest=false."""


def prefill_summary_for_extraction(prefill: dict[str, Any]) -> dict[str, Any]:
    """Minimal form context — avoids shipping aggregators/sources in the LLM prompt."""
    prefs = prefill.get("preferences") or {}
    edu_list = prefill.get("education") or []
    edu = edu_list[0] if edu_list else {}
    return {
        "target_degree": prefs.get("target_degree"),
        "target_fields": prefs.get("target_fields"),
        "target_regions": prefs.get("target_regions"),
        "target_countries": prefs.get("target_countries_priority"),
        "target_intake_term": prefs.get("target_intake_term"),
        "funding_requirement": prefs.get("funding_requirement"),
        "research_one_liner": prefs.get("research_direction_one_liner"),
        "highest_education": {
            "degree_level": edu.get("degree_level"),
            "field": edu.get("field"),
            "institution": edu.get("institution"),
        },
    }


def _trim_cv(cv_text: str, max_chars: int | None = None) -> str:
    limit = max_chars or settings.llm_extraction_max_cv_chars
    trimmed = (cv_text or "").strip()
    if len(trimmed) <= limit:
        return trimmed
    return trimmed[:limit] + "\n[CV truncated — prioritize recent roles, education, publications]"


def _compact_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def build_cv_extraction_user_prompt(prefill: dict[str, Any], cv_text: str) -> str:
    summary = _compact_json(prefill_summary_for_extraction(prefill))
    cv_trimmed = _trim_cv(cv_text)
    return (
        CV_EXTRACTION_USER_TEMPLATE.replace("{{PREFILL_SUMMARY}}", summary)
        .replace("{{CV_TEXT}}", cv_trimmed)
    )


def build_cv_repair_user_prompt(
    prefill: dict[str, Any],
    cv_text: str,
    errors: list[str],
    partial: dict[str, Any],
) -> str:
    return (
        CV_REPAIR_USER_TEMPLATE.replace("{{ERRORS}}", "\n".join(errors))
        .replace("{{PARTIAL_JSON}}", _compact_json(partial))
        .replace("{{PREFILL_SUMMARY}}", _compact_json(prefill_summary_for_extraction(prefill)))
        .replace("{{CV_TEXT}}", _trim_cv(cv_text, settings.llm_extraction_max_cv_chars // 2))
    )

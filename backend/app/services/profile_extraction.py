"""LLM-backed CV extraction for the profile pipeline (Groq via chat_completion)."""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.logging_config import get_logger
from app.prompts.cv_extraction import (
    CV_EXTRACTION_SYSTEM,
    CV_REPAIR_SYSTEM,
    build_cv_repair_user_prompt,
    build_cv_extraction_user_prompt,
)
from app.services.llm import chat_completion, _extract_content
from app.services.groq_models import groq_extraction_models_to_try
from app.services.llm_json import parse_llm_json, salvage_json_object, truncate_error_snippet
from app.services.profile_pipeline import normalize_extraction_output
from app.telemetry.langsmith import traceable

logger = get_logger(__name__)

_JSON_REPAIR_SYSTEM = (
    "You fix malformed JSON from a CV extraction step. "
    "Return ONLY one valid JSON object — no markdown, no commentary. "
    "Preserve all factual content; close truncated strings and arrays."
)


def _extraction_llm_kwargs() -> dict[str, Any]:
    return {
        "max_tokens": settings.llm_extraction_max_tokens,
        "temperature": settings.llm_extraction_temperature,
        "response_format": {"type": "json_object"},
        "model": settings.groq_extraction_model,
        "groq_models": groq_extraction_models_to_try(settings.groq_extraction_model),
    }


async def _call_extraction_llm(messages: list[dict[str, str]]) -> str:
    result = await chat_completion(messages, **_extraction_llm_kwargs())
    text = _extract_content(result)
    if not text:
        raise ValueError("Unexpected non-text response from LLM")
    return text


async def _parse_extraction_response(
    raw: str,
    *,
    prefill: dict[str, Any],
    cv_text: str,
    user_id: str | None = None,
    pipeline_run_id: str | None = None,
    submission_id: str | None = None,
) -> dict[str, Any]:
    try:
        return parse_llm_json(raw)
    except ValueError as parse_error:
        logger.warning("cv_extraction_json_parse_failed", error=str(parse_error))
        partial = salvage_json_object(raw) or {}
        repair_errors = [str(parse_error)]
        return await repair_extraction(
            prefill,
            cv_text,
            repair_errors,
            partial,
            user_id=user_id,
            pipeline_run_id=pipeline_run_id,
            submission_id=submission_id,
        )


def _process_extraction_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    prefill = inputs.get("prefill") or {}
    cv_text = inputs.get("cv_text") or ""
    # Build the actual messages that will be sent so the prompt is visible in LangSmith.
    from app.prompts.cv_extraction import build_cv_extraction_user_prompt, CV_EXTRACTION_SYSTEM
    user_prompt = build_cv_extraction_user_prompt(prefill, cv_text)
    return {
        "messages": [
            {"role": "system", "content": CV_EXTRACTION_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        "cv_char_count": len(cv_text),
        "prefill_summary": prefill,
        "user_id": inputs.get("user_id"),
        "pipeline_run_id": inputs.get("pipeline_run_id"),
        "submission_id": inputs.get("submission_id"),
    }


def _process_extraction_outputs(output: Any) -> Any:
    if isinstance(output, dict):
        return {
            "extraction": output,
            "top_level_keys": sorted(output.keys()),
            "field_count": len(output),
            "search_keyword_count": len(output.get("search_keywords") or []),
            "experience_count": len(output.get("experiences") or []),
            "education_count": len(output.get("education") or []),
            "confidence": (output.get("extraction_meta") or {}).get("confidence"),
        }
    return output


@traceable(
    run_type="chain",
    name="profile_cv_extraction",
    process_inputs=_process_extraction_inputs,
    process_outputs=_process_extraction_outputs,
    tags=["profile_setup", "cv_extraction"],
)
async def extract_cv_from_prefill(
    prefill: dict[str, Any],
    cv_text: str,
    *,
    user_id: str | None = None,
    pipeline_run_id: str | None = None,
    submission_id: str | None = None,
) -> dict[str, Any]:
    user_prompt = build_cv_extraction_user_prompt(prefill, cv_text)
    messages = [
        {"role": "system", "content": CV_EXTRACTION_SYSTEM},
        {"role": "user", "content": user_prompt},
    ]
    raw = await _call_extraction_llm(messages)
    data = await _parse_extraction_response(
        raw,
        prefill=prefill,
        cv_text=cv_text,
        user_id=user_id,
        pipeline_run_id=pipeline_run_id,
        submission_id=submission_id,
    )
    return normalize_extraction_output(data)


@traceable(
    run_type="llm",
    name="cv_json_fix",
    tags=["profile_setup", "cv_json_fix"],
)
async def _json_fix_call(broken_raw: str, validation_errors: list[str], parse_error: Exception) -> dict[str, Any]:
    """Third-attempt LLM call: pure JSON syntax fix on a broken repair response."""
    snippet = truncate_error_snippet(broken_raw)
    messages = [
        {"role": "system", "content": _JSON_REPAIR_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Parse error: {parse_error}\n\n"
                f"Validation errors: {validation_errors}\n\n"
                f"Broken JSON to fix:\n{snippet}\n\n"
                "Return the corrected full JSON object."
            ),
        },
    ]
    raw = await _call_extraction_llm(messages)
    return parse_llm_json(raw)


def _process_repair_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    from app.prompts.cv_extraction import build_cv_repair_user_prompt, CV_REPAIR_SYSTEM
    prefill = inputs.get("prefill") or {}
    cv_text = inputs.get("cv_text") or ""
    errors = inputs.get("errors") or []
    partial = inputs.get("partial") or {}
    user_prompt = build_cv_repair_user_prompt(prefill, cv_text, errors, partial)
    return {
        "messages": [
            {"role": "system", "content": CV_REPAIR_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        "validation_errors": errors,
        "partial_keys": sorted(partial.keys()),
        "cv_char_count": len(cv_text),
        "user_id": inputs.get("user_id"),
        "pipeline_run_id": inputs.get("pipeline_run_id"),
        "submission_id": inputs.get("submission_id"),
    }


@traceable(
    run_type="chain",
    name="profile_cv_repair",
    process_inputs=_process_repair_inputs,
    process_outputs=_process_extraction_outputs,
    tags=["profile_setup", "cv_repair"],
)
async def repair_extraction(
    prefill: dict[str, Any],
    cv_text: str,
    errors: list[str],
    partial: dict[str, Any],
    *,
    user_id: str | None = None,
    pipeline_run_id: str | None = None,
    submission_id: str | None = None,
) -> dict[str, Any]:
    user_prompt = build_cv_repair_user_prompt(prefill, cv_text, errors, partial)
    messages = [
        {"role": "system", "content": CV_REPAIR_SYSTEM},
        {"role": "user", "content": user_prompt},
    ]
    raw = await _call_extraction_llm(messages)
    try:
        data = parse_llm_json(raw)
    except ValueError as parse_error:
        logger.warning("cv_repair_json_parse_failed", error=str(parse_error))
        data = await _json_fix_call(raw, errors, parse_error)
    return normalize_extraction_output(data)

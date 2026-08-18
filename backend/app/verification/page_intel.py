"""Shared fetch + LLM extract for verification and staleness checks (Task 2 / Task 6)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from dateutil import parser as date_parser

from app.ingestion.extract.heuristic import extract_detail, fetch_detail_text
from app.ingestion.http_client import make_client
from app.logging_config import get_logger
from app.services.llm import chat_completion, _extract_content
from app.services.llm_json import parse_llm_json
from app.telemetry.langsmith import traceable
from app.verification.contracts import PrimaryFields

logger = get_logger(__name__)

_EXTRACTION_SYSTEM = (
    "Extract opportunity facts from web page text into JSON only. "
    "No markdown. Use null for unknown fields. Do not invent deadlines or funding."
)

_EXTRACTION_USER_TEMPLATE = """Extract from this page for opportunity verification.

URL: {{URL}}
Organization hint: {{ORG}}
Title hint: {{TITLE}}

Page text:
{{TEXT}}

Return JSON with keys:
deadline (ISO date string or null),
funding_summary (short string),
eligibility_summary (short string),
institution (string or null),
confidence_per_field (object mapping field names to high|medium|low).

Schema example:
{"deadline":"2026-10-15","funding_summary":"fully funded stipend","eligibility_summary":"international MSc applicants","institution":"DAAD","confidence_per_field":{"deadline":"high","funding_summary":"medium","eligibility_summary":"low"}}"""


def fetch_page_text_sync(url: str, extract_config: dict[str, Any] | None = None) -> str:
    """Fetch raw page text using ingestion HTTP client (sync for worker compatibility)."""
    cfg = extract_config or {}
    with make_client(timeout=35.0) as client:
        return fetch_detail_text(client, url, cfg)


def heuristic_extract_page(
    html_or_text: str,
    url: str,
    extract_config: dict[str, Any] | None = None,
    *,
    fallback_title: str = "",
    fallback_summary: str = "",
) -> PrimaryFields:
    """Heuristic extraction ladder (no LLM) — fast fallback."""
    cfg = extract_config or {}
    extracted = extract_detail(
        html_or_text,
        url,
        cfg,
        fallback_title=fallback_title,
        fallback_summary=fallback_summary,
    )
    elig = " ".join(extracted.requirements or [])[:800] or None
    funding = extracted.funding_type
    if extracted.summary and "fund" in extracted.summary.lower():
        funding = f"{funding or ''} {extracted.summary[:300]}".strip()
    return PrimaryFields(
        deadline=extracted.deadline,
        funding_summary=funding,
        eligibility_summary=elig,
        institution=extracted.institution,
        confidence_per_field={
            "deadline": extracted.extraction_confidence,
            "funding_summary": extracted.extraction_confidence,
            "eligibility_summary": extracted.extraction_confidence,
        },
        source_url=url,
        raw_extraction={"method": "heuristic"},
    )


@traceable(run_type="chain", name="verification_llm_extract", tags=["verification", "llm_extract"])
async def llm_extract_page(
    page_text: str,
    url: str,
    *,
    org_hint: str = "",
    title_hint: str = "",
    max_chars: int = 6000,
) -> PrimaryFields:
    trimmed = page_text[:max_chars]
    if len(page_text) > max_chars:
        trimmed += "\n[truncated]"

    user = (
        _EXTRACTION_USER_TEMPLATE.replace("{{URL}}", url)
        .replace("{{ORG}}", org_hint)
        .replace("{{TITLE}}", title_hint)
        .replace("{{TEXT}}", trimmed)
    )
    messages = [
        {"role": "system", "content": _EXTRACTION_SYSTEM},
        {"role": "user", "content": user},
    ]
    result = await chat_completion(
        messages,
        max_tokens=1024,
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    raw = _extract_content(result)
    try:
        data = parse_llm_json(raw)
    except ValueError:
        logger.warning("verification_llm_json_failed", url=url)
        return heuristic_extract_page(page_text, url, fallback_title=title_hint)

    deadline = None
    raw_deadline = data.get("deadline")
    if raw_deadline:
        try:
            deadline = date_parser.parse(str(raw_deadline))
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
        except (ValueError, OverflowError):
            deadline = None

    conf = data.get("confidence_per_field") or {}
    if not isinstance(conf, dict):
        conf = {}

    return PrimaryFields(
        deadline=deadline,
        funding_summary=str(data.get("funding_summary") or "")[:500] or None,
        eligibility_summary=str(data.get("eligibility_summary") or "")[:800] or None,
        institution=data.get("institution"),
        confidence_per_field={k: str(v) for k, v in conf.items()},
        source_url=url,
        raw_extraction=data,
    )


async def fetch_and_extract(
    url: str,
    *,
    org_hint: str = "",
    title_hint: str = "",
    extract_config: dict[str, Any] | None = None,
    use_llm: bool = True,
) -> PrimaryFields:
    """Fetch a URL and extract structured fields (shared by verification + staleness)."""
    text = fetch_page_text_sync(url, extract_config)
    if not text or len(text.strip()) < 50:
        return PrimaryFields(source_url=url, raw_extraction={"error": "empty_page"})
    if use_llm:
        return await llm_extract_page(text, url, org_hint=org_hint, title_hint=title_hint)
    return heuristic_extract_page(text, url, extract_config, fallback_title=title_hint)

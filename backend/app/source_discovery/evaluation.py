"""LLM evaluation and legitimacy checks for candidate sources."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.logging_config import get_logger
from app.services.llm import chat_completion, _extract_content
from app.services.llm_json import parse_llm_json
from app.source_discovery.contracts import CandidateEvaluation, DomainCandidate, StructureEvidence
from app.source_discovery.fetch import fetch_page_text
from app.source_discovery.structure import analyze_page_structure, has_recurring_structure
from app.verification.cache import refresh_domain_legitimacy
from app.verification.domain_utils import is_institutional_domain
from app.verification.prescreen import scan_scam_phrases

logger = get_logger(__name__)

_EVAL_SYSTEM = (
    "You evaluate whether a website is a RECURRING SOURCE of opportunity listings "
    "(RSS feed or revisitable HTML listing with multiple entries), not a single fellowship page. "
    "Return JSON only with: evaluation_verdict (recurring_source|one_off_page|unclear), "
    "relevance_notes, legitimacy_notes, confidence (0-1), structure_type (rss|html_listing|unclear), "
    "guessed_parser_config (object), recurring_evidence_summary. "
    "If evidence shows a single article or one-off announcement, verdict must be one_off_page."
)

_EVAL_USER = """Domain: {domain}
URL: {url}
Search snippet: {snippet}

Profile context: {profile}

Structure evidence:
{structure}

Page text excerpt:
{text}
"""


def _default_parser_config(
    evidence: StructureEvidence,
    url: str,
    structure_type: str,
) -> dict[str, Any]:
    if structure_type == "rss" and evidence.rss_urls:
        feed = evidence.rss_urls[0]
        return {
            "version": 1,
            "discover": {
                "kind": "rss",
                "feed_urls": evidence.rss_urls[:3],
                "max_entries": 50,
                "dedupe_by": "link",
            },
            "extract": {
                "detail_fetch": "required",
                "ladder": {"structured": True, "adapter": True, "heuristic": True},
                "feed": {"strip_html": True, "use_content_encoded": True},
                "detail": {
                    "title": "h1, article h1",
                    "content": "article .entry-content, main article, .post-content",
                },
            },
            "notes": f"Discovered via source discovery; primary feed {feed}",
        }

    entry_url = url
    selector = evidence.suggested_link_selector or "article h2 a, main a"
    return {
        "version": 1,
        "discover": {
            "kind": "html",
            "entry_urls": [entry_url],
            "link_selector": selector,
            "max_entries": 50,
        },
        "extract": {
            "detail_fetch": "required",
            "ladder": {"structured": True, "adapter": True, "heuristic": True},
            "detail": {
                "title": "h1, article h1",
                "content": "article .entry-content, main, .post-content",
            },
        },
        "notes": "Discovered via source discovery; HTML listing pattern",
    }


async def evaluate_candidate(
    session: AsyncSession,
    candidate: DomainCandidate,
    profile_ctx: dict[str, Any],
) -> CandidateEvaluation:
    page_text = ""
    final_url = candidate.discovered_url
    try:
        final_url, page_text = fetch_page_text(candidate.discovered_url)
    except Exception as exc:
        logger.warning("discovery_fetch_failed", domain=candidate.domain, error=str(exc))
        return CandidateEvaluation(
            evaluation_verdict="unclear",
            relevance_notes=f"Could not fetch page: {exc}",
            legitimacy_notes="Fetch failed before evaluation",
            confidence=0.15,
            structure_type="unclear",
            guessed_parser_config={},
            recurring_evidence_summary="fetch_failed",
        )

    evidence = analyze_page_structure(final_url, page_text)
    scam_hits = scan_scam_phrases(f"{candidate.title} {candidate.snippet} {page_text[:3000]}")
    legitimacy = await refresh_domain_legitimacy(
        session,
        candidate.domain,
        page_text=page_text[:8000],
        commit=False,
    )
    legit_notes = []
    if legitimacy.flags:
        legit_notes.append(f"Signals: {', '.join(legitimacy.flags[:5])}")
    if legitimacy.registered_at:
        legit_notes.append(f"Domain registered {legitimacy.registered_at.date().isoformat()}")
    if is_institutional_domain(candidate.domain):
        legit_notes.append("Institutional TLD pattern")
    if scam_hits:
        legit_notes.append(f"Red flags: {', '.join(scam_hits[:3])}")

    structure_json = evidence.model_dump()
    profile_json = json.dumps(
        {
            "fields": profile_ctx.get("target_fields")[:8],
            "regions": profile_ctx.get("target_regions"),
            "degree": profile_ctx.get("target_degree"),
        },
        ensure_ascii=False,
    )

    messages = [
        {"role": "system", "content": _EVAL_SYSTEM},
        {
            "role": "user",
            "content": _EVAL_USER.format(
                domain=candidate.domain,
                url=final_url,
                snippet=candidate.snippet[:800],
                profile=profile_json,
                structure=json.dumps(structure_json, ensure_ascii=False),
                text=page_text[:6000],
            ),
        },
    ]

    try:
        result = await chat_completion(
            messages,
            max_tokens=1400,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        raw = _extract_content(result)
        evaluation = CandidateEvaluation.model_validate(parse_llm_json(raw))
    except Exception as exc:
        logger.warning("discovery_eval_llm_failed", domain=candidate.domain, error=str(exc))
        recurring = has_recurring_structure(evidence)
        evaluation = CandidateEvaluation(
            evaluation_verdict="recurring_source" if recurring else "unclear",
            relevance_notes=candidate.snippet[:400] or "Heuristic structure analysis only",
            confidence=0.4 if recurring else 0.25,
            structure_type="rss" if evidence.has_rss_feed else ("html_listing" if recurring else "unclear"),
            guessed_parser_config=_default_parser_config(
                evidence,
                final_url,
                "rss" if evidence.has_rss_feed else "html_listing",
            ),
            recurring_evidence_summary="heuristic_fallback",
        )

    evaluation.legitimacy_notes = "; ".join(legit_notes) or evaluation.legitimacy_notes

    if evaluation.evaluation_verdict == "recurring_source" and not has_recurring_structure(evidence):
        evaluation.evaluation_verdict = "unclear"
        evaluation.confidence = min(evaluation.confidence, 0.45)
        evaluation.recurring_evidence_summary = (
            evaluation.recurring_evidence_summary + "; downgraded_no_structure"
        )

    if not evaluation.guessed_parser_config:
        evaluation.guessed_parser_config = _default_parser_config(
            evidence,
            final_url,
            evaluation.structure_type,
        )

    return evaluation

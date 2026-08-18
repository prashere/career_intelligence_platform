"""Groq model IDs, deprecation aliases, tier limits, and fallback resolution.

Groq retires models periodically; see https://console.groq.com/docs/deprecations
Rate limits: https://console.groq.com/docs/rate-limits

Free-tier TPM (tokens per minute) is a hard ceiling on request size for many models.
A single CV extraction call must keep (input tokens + max_output_tokens) under that cap.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# General chat default (fast, cheap). Not suitable for large CV extraction on free tier.
GROQ_DEFAULT_CHAT_MODEL = "openai/gpt-oss-20b"

# CV extraction: higher free-tier TPM (70K) — fits full prompt + completion budget.
GROQ_DEFAULT_EXTRACTION_MODEL = "groq/compound-mini"

# Free-tier TPM limits (input + reserved output must fit — see Groq rate-limit errors).
GROQ_MODEL_FREE_TPM: dict[str, int] = {
    "openai/gpt-oss-20b": 8000,
    "openai/gpt-oss-120b": 8000,
    "openai/gpt-oss-safeguard-20b": 8000,
    "qwen/qwen3-32b": 6000,
    "qwen/qwen3.6-27b": 8000,
    "meta-llama/llama-4-scout-17b-16e-instruct": 30000,
    "groq/compound-mini": 70000,
    "groq/compound": 70000,
}

GROQ_FREE_TPM_DEFAULT = 8000

# Retired or renamed model IDs → current replacement.
GROQ_MODEL_ALIASES: dict[str, str] = {
    "llama-3.1-8b-instant": GROQ_DEFAULT_CHAT_MODEL,
    "llama-3.3-70b-versatile": "openai/gpt-oss-120b",
    "llama3-8b-8192": GROQ_DEFAULT_CHAT_MODEL,
    "llama3-70b-8192": "openai/gpt-oss-120b",
    "gemma2-9b-it": GROQ_DEFAULT_CHAT_MODEL,
    "mixtral-8x7b-32768": "openai/gpt-oss-120b",
}

# General chat fallbacks when configured model 404s.
GROQ_CHAT_FALLBACK_CHAIN: tuple[str, ...] = (
    GROQ_DEFAULT_CHAT_MODEL,
    "openai/gpt-oss-120b",
)

# Extraction fallbacks — prefer high-TPM models first.
GROQ_EXTRACTION_FALLBACK_CHAIN: tuple[str, ...] = (
    GROQ_DEFAULT_EXTRACTION_MODEL,
    "groq/compound",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    GROQ_DEFAULT_CHAT_MODEL,
)


def resolve_groq_model(model_id: str) -> str:
    """Map deprecated Groq model IDs to their replacements."""
    trimmed = (model_id or "").strip()
    if not trimmed:
        return GROQ_DEFAULT_CHAT_MODEL
    alias = GROQ_MODEL_ALIASES.get(trimmed)
    if alias and alias != trimmed:
        logger.warning(
            "Groq model %s is deprecated/retired; using %s instead. "
            "Update GROQ_CHAT_MODEL in .env.",
            trimmed,
            alias,
        )
        return alias
    return trimmed


def groq_models_to_try(configured: str, *, chain: tuple[str, ...] = GROQ_CHAT_FALLBACK_CHAIN) -> list[str]:
    """Ordered unique model IDs to attempt for chat completions."""
    primary = resolve_groq_model(configured)
    seen: set[str] = set()
    ordered: list[str] = []
    for model_id in (primary, *chain):
        if model_id and model_id not in seen:
            seen.add(model_id)
            ordered.append(model_id)
    return ordered


def groq_extraction_models_to_try(configured: str | None = None) -> list[str]:
    primary = resolve_groq_model(configured or GROQ_DEFAULT_EXTRACTION_MODEL)
    return groq_models_to_try(primary, chain=GROQ_EXTRACTION_FALLBACK_CHAIN)


def groq_free_tpm_for_model(model_id: str) -> int:
    return GROQ_MODEL_FREE_TPM.get(model_id, GROQ_FREE_TPM_DEFAULT)


def is_groq_model_not_found(exc: BaseException) -> bool:
    from openai import APIStatusError

    if isinstance(exc, APIStatusError) and exc.status_code == 404:
        return True
    msg = str(exc).lower()
    return "model_not_found" in msg or "does not exist" in msg


def is_groq_request_too_large(exc: BaseException) -> bool:
    from openai import APIStatusError

    if isinstance(exc, APIStatusError) and exc.status_code in (413, 429):
        msg = str(exc).lower()
        if "too large" in msg or "tokens per minute" in msg or "rate_limit" in msg:
            return True
    msg = str(exc).lower()
    return (
        "request too large" in msg
        or "tokens per minute" in msg
        or ("rate_limit_exceeded" in msg and "tpm" in msg)
    )

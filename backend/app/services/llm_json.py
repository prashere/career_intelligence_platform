"""Parse and salvage JSON from LLM chat responses."""

from __future__ import annotations

import json
import re
from typing import Any

from app.services.profile_pipeline import _strip_json_fences
from app.logging_config import get_logger

logger = get_logger(__name__)


def _loads_object(text: str) -> dict[str, Any]:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("LLM response must be a JSON object")
    return data


def _extract_json_object_span(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


def _close_truncated_json(text: str) -> str:
    """Close truncated JSON using bracket stack (ignores braces inside strings)."""
    snippet = text.rstrip()
    if not snippet:
        return snippet

    if snippet.endswith(","):
        snippet = snippet[:-1].rstrip()

    in_string = False
    escape = False
    stack: list[str] = []
    for ch in snippet:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in "}]" and stack and stack[-1] == ch:
            stack.pop()

    if in_string:
        snippet += '"'
    snippet += "".join(reversed(stack))
    return snippet


def salvage_json_object(text: str) -> dict[str, Any] | None:
    """Try progressively more aggressive repairs until JSON parses."""
    cleaned = _strip_json_fences((text or "").strip())
    if not cleaned:
        return None

    attempts: list[str] = []
    span = _extract_json_object_span(cleaned)
    if span:
        attempts.append(span)
    attempts.append(cleaned)
    if span:
        attempts.append(_close_truncated_json(span))

    # Trim from end — fixes trailing garbage after valid JSON prefix.
    if span and len(span) > 200:
        for trim in range(len(span), max(len(span) - 800, 200), -50):
            attempts.append(_close_truncated_json(span[:trim]))

    seen: set[str] = set()
    for candidate in attempts:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            return _loads_object(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def parse_llm_json(text: str) -> dict[str, Any]:
    """Parse LLM output as a JSON object; salvage truncated or fenced responses."""
    cleaned = _strip_json_fences((text or "").strip())
    if not cleaned:
        raise ValueError("Empty LLM response")

    try:
        return _loads_object(cleaned)
    except (json.JSONDecodeError, ValueError) as first_error:
        salvaged = salvage_json_object(text)
        if salvaged is not None:
            logger.warning(
                "llm_json_salvaged",
                original_error=str(first_error),
                salvaged_keys=sorted(salvaged.keys()),
            )
            return salvaged
        preview = cleaned[:500] + ("…" if len(cleaned) > 500 else "")
        raise ValueError(
            f"LLM returned invalid JSON: {first_error}. Preview: {preview}"
        ) from first_error


def truncate_error_snippet(text: str, max_len: int = 1200) -> str:
    cleaned = re.sub(r"\s+", " ", _strip_json_fences(text or ""))
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[:max_len] + "…"

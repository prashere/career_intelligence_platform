"""LangSmith tracing configuration and helpers.

Traces profile pipeline LLM calls (CV extraction/repair), agent chat, and embeddings.
Docs: https://docs.smith.langchain.com/
"""

from __future__ import annotations

import os
from typing import Any, Callable, TypeVar

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)

_configured = False

F = TypeVar("F", bound=Callable[..., Any])


def langsmith_enabled() -> bool:
    """Tracing is on when explicitly enabled and an API key is set."""
    if not settings.langsmith_api_key:
        return False
    if settings.langsmith_tracing:
        return True
    # Honor LANGSMITH_TRACING env if set directly (e.g. docker override).
    return os.environ.get("LANGSMITH_TRACING", "").lower() in ("1", "true", "yes")


def configure_langsmith() -> bool:
    """Apply LangSmith env vars from app settings. Safe to call multiple times."""
    global _configured
    if _configured:
        return langsmith_enabled()

    if not settings.langsmith_api_key:
        logger.info("langsmith_disabled", reason="LANGSMITH_API_KEY not set")
        _configured = True
        return False

    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGSMITH_TRACING"] = "true" if settings.langsmith_tracing else "false"

    if settings.langsmith_project:
        os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    if settings.langsmith_endpoint:
        os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint
    if settings.langsmith_workspace_id:
        os.environ["LANGSMITH_WORKSPACE_ID"] = settings.langsmith_workspace_id

    _configured = True
    enabled = langsmith_enabled()
    if enabled:
        logger.info(
            "langsmith_enabled",
            project=settings.langsmith_project,
            endpoint=settings.langsmith_endpoint or "default",
        )
    else:
        logger.info("langsmith_disabled", reason="LANGSMITH_TRACING is false")
    return enabled


def wrap_openai_client(client: Any, *, chat_name: str = "ChatCompletion") -> Any:
    """Wrap an OpenAI-compatible async client for automatic LLM child spans."""
    if not langsmith_enabled():
        return client
    try:
        from langsmith.wrappers import wrap_openai

        return wrap_openai(client, chat_name=chat_name)
    except Exception as exc:
        logger.warning("langsmith_wrap_openai_failed", error=str(exc))
        return client


def traceable(*decorator_args: Any, **decorator_kwargs: Any) -> Callable[[F], F]:
    """Apply @traceable when LangSmith is enabled; otherwise return function unchanged."""
    def _decorator(func: F) -> F:
        if not langsmith_enabled():
            return func
        try:
            from langsmith import traceable as _traceable

            return _traceable(*decorator_args, **decorator_kwargs)(func)
        except Exception as exc:
            logger.warning("langsmith_traceable_failed", error=str(exc))
            return func

    if decorator_args and callable(decorator_args[0]) and len(decorator_args) == 1 and not decorator_kwargs:
        return _decorator(decorator_args[0])

    return _decorator


def profile_trace_metadata(
    *,
    user_id: str | None = None,
    pipeline_run_id: str | None = None,
    submission_id: str | None = None,
    step: str | None = None,
) -> dict[str, str]:
    """Standard metadata for profile-setup traces in LangSmith."""
    meta: dict[str, str] = {"feature": "profile_setup"}
    if user_id:
        meta["user_id"] = user_id
    if pipeline_run_id:
        meta["pipeline_run_id"] = pipeline_run_id
    if submission_id:
        meta["submission_id"] = submission_id
    if step:
        meta["pipeline_step"] = step
    return meta


def process_chat_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """Shape chat inputs for LangSmith — full messages so prompts are visible."""
    messages = inputs.get("messages") or []
    return {
        "messages": messages,
        "message_count": len(messages),
        "model": inputs.get("model"),
        "provider": inputs.get("provider"),
        "max_tokens": inputs.get("max_tokens"),
        "temperature": inputs.get("temperature"),
        "response_format": inputs.get("response_format"),
        "stream": inputs.get("stream", False),
    }


def process_chat_outputs(output: Any) -> Any:
    """Shape chat outputs — surface content, token usage, model, and finish_reason."""
    if isinstance(output, dict) and "content" in output:
        return output
    if isinstance(output, str):
        return {"content": output, "char_count": len(output)}
    return output

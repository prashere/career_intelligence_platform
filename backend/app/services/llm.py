"""Chat completions via OpenAI-compatible providers (OpenAI, Groq)."""

from __future__ import annotations

from typing import Any, AsyncIterator, Optional

from openai import AsyncOpenAI

from app.config import settings
from app.logging_config import get_logger
from app.services.groq_models import (
    groq_extraction_models_to_try,
    groq_models_to_try,
    is_groq_model_not_found,
    is_groq_request_too_large,
    resolve_groq_model,
)
from app.telemetry.langsmith import (
    configure_langsmith,
    langsmith_enabled,
    process_chat_inputs,
    process_chat_outputs,
    traceable,
    wrap_openai_client,
)

configure_langsmith()

logger = get_logger(__name__)

_chat_client: Optional[AsyncOpenAI] = None


def _use_groq() -> bool:
    provider = (settings.llm_provider or "").strip().lower()
    if provider == "groq":
        return bool(settings.groq_api_key)
    if provider == "openai":
        return False
    return bool(settings.groq_api_key)


def get_chat_client() -> Optional[AsyncOpenAI]:
    global _chat_client
    if _use_groq():
        if not settings.groq_api_key:
            return None
        if _chat_client is None:
            raw = AsyncOpenAI(
                api_key=settings.groq_api_key,
                base_url=settings.groq_base_url,
            )
            _chat_client = wrap_openai_client(raw, chat_name="GroqChatCompletion")
        return _chat_client

    if not settings.openai_api_key:
        return None
    if _chat_client is None:
        raw = AsyncOpenAI(api_key=settings.openai_api_key)
        _chat_client = wrap_openai_client(raw, chat_name="OpenAIChatCompletion")
    return _chat_client


def get_chat_model() -> str:
    if _use_groq():
        return resolve_groq_model(settings.groq_chat_model)
    return settings.chat_model


def chat_configured() -> bool:
    if _use_groq():
        return bool(settings.groq_api_key)
    return bool(settings.openai_api_key)


def active_provider() -> str:
    if _use_groq() and settings.groq_api_key:
        return "groq"
    if settings.openai_api_key:
        return "openai"
    return "none"


def _completion_kwargs(
    max_tokens: int | None,
    response_format: dict[str, Any] | None,
    temperature: float | None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if response_format is not None:
        kwargs["response_format"] = response_format
    if temperature is not None:
        kwargs["temperature"] = temperature
    return kwargs


async def _groq_create_with_fallback(
    client: AsyncOpenAI,
    messages: list[dict],
    stream: bool,
    completion_kwargs: dict[str, Any],
    models: list[str],
):
    last_error: Optional[BaseException] = None
    kwargs = dict(completion_kwargs)

    for model in models:
        try:
            return await client.chat.completions.create(
                model=model,
                messages=messages,
                stream=stream,
                **kwargs,
            )
        except Exception as exc:
            if kwargs.get("response_format") and _is_response_format_error(exc):
                logger.warning("Groq model %s rejected response_format; retrying without", model)
                kwargs = {k: v for k, v in kwargs.items() if k != "response_format"}
                try:
                    return await client.chat.completions.create(
                        model=model,
                        messages=messages,
                        stream=stream,
                        **kwargs,
                    )
                except Exception as inner_exc:
                    exc = inner_exc
            if is_groq_model_not_found(exc):
                logger.warning("Groq model %s not available: %s", model, exc)
                last_error = exc
                continue
            if is_groq_request_too_large(exc):
                logger.warning("Groq model %s request too large: %s", model, exc)
                last_error = exc
                continue
            raise

    if last_error:
        raise last_error
    raise RuntimeError("No Groq models configured")


def _is_response_format_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "response_format" in msg or "json_object" in msg


def _extract_content(result: Any) -> str:
    """Extract plain text from a chat_completion return value (dict or str)."""
    if isinstance(result, dict):
        return result.get("content") or ""
    return result or ""


def _build_llm_output(content: str, response: Any, provider: str) -> dict[str, Any]:
    """Build a structured output dict for LangSmith from a completed chat response."""
    choice = response.choices[0]
    usage = response.usage
    out: dict[str, Any] = {
        "content": content,
        "char_count": len(content),
        "model": response.model,
        "provider": provider,
        "finish_reason": choice.finish_reason,
    }
    if usage:
        out["token_usage"] = {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
        }
    return out


@traceable(
    run_type="llm",
    name="chat_completion",
    process_inputs=process_chat_inputs,
    process_outputs=process_chat_outputs,
)
async def chat_completion(
    messages: list[dict],
    stream: bool = False,
    *,
    max_tokens: int | None = None,
    response_format: dict[str, Any] | None = None,
    temperature: float | None = None,
    model: str | None = None,
    groq_models: list[str] | None = None,
):
    client = get_chat_client()
    provider = active_provider()
    effective_model = model or get_chat_model()
    completion_kwargs = _completion_kwargs(max_tokens, response_format, temperature)

    if not client:
        hint = "Set GROQ_API_KEY (and LLM_PROVIDER=groq) or OPENAI_API_KEY in .env."
        if stream:
            async def _gen() -> AsyncIterator[str]:
                yield hint
            return _gen()
        return hint

    if _use_groq():
        models = groq_models or groq_models_to_try(model or settings.groq_chat_model)
        if stream:
            return await _groq_create_with_fallback(
                client, messages, stream=True, completion_kwargs=completion_kwargs, models=models,
            )

        response = await _groq_create_with_fallback(
            client, messages, stream=False, completion_kwargs=completion_kwargs, models=models,
        )
        choice = response.choices[0]
        content = choice.message.content or ""
        if choice.finish_reason == "length":
            logger.warning(
                "llm_output_truncated",
                provider=provider,
                model=response.model,
                max_tokens=max_tokens,
            )
        # Return structured dict so LangSmith captures model/usage/finish_reason.
        # Callers that need the plain string must read ["content"].
        return _build_llm_output(content, response, provider)

    openai_model = model or settings.chat_model
    if stream:
        return await client.chat.completions.create(
            model=openai_model,
            messages=messages,
            stream=True,
            **completion_kwargs,
        )

    response = await client.chat.completions.create(
        model=openai_model,
        messages=messages,
        **completion_kwargs,
    )
    choice = response.choices[0]
    content = choice.message.content or ""
    if choice.finish_reason == "length":
        logger.warning(
            "llm_output_truncated",
            provider=provider,
            model=openai_model,
            max_tokens=max_tokens,
        )
    return _build_llm_output(content, response, provider)


async def chat_completion_text(
    messages: list[dict],
    stream: bool = False,
    **kwargs: Any,
) -> str:
    """Convenience wrapper — calls chat_completion and returns only the text.

    Use this in callers that need a plain string (agent, RAG, scripts).
    chat_completion itself returns a structured dict for LangSmith visibility.
    Streaming callers still get the raw stream object.
    """
    result = await chat_completion(messages, stream=stream, **kwargs)
    if stream:
        return result  # type: ignore[return-value]
    return _extract_content(result)

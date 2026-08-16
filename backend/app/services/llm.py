"""Chat completions via OpenAI-compatible providers (OpenAI, Groq)."""

from __future__ import annotations

from typing import AsyncIterator, Optional

from openai import AsyncOpenAI

from app.config import settings

_chat_client: Optional[AsyncOpenAI] = None


def _use_groq() -> bool:
    provider = (settings.llm_provider or "").strip().lower()
    if provider == "groq":
        return bool(settings.groq_api_key)
    if provider == "openai":
        return False
    # Default: Groq when configured, otherwise OpenAI.
    return bool(settings.groq_api_key)


def get_chat_client() -> Optional[AsyncOpenAI]:
    global _chat_client
    if _use_groq():
        if not settings.groq_api_key:
            return None
        if _chat_client is None:
            _chat_client = AsyncOpenAI(
                api_key=settings.groq_api_key,
                base_url=settings.groq_base_url,
            )
        return _chat_client

    if not settings.openai_api_key:
        return None
    if _chat_client is None:
        _chat_client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _chat_client


def get_chat_model() -> str:
    if _use_groq():
        return settings.groq_chat_model
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


async def chat_completion(messages: list[dict], stream: bool = False):
    client = get_chat_client()
    model = get_chat_model()

    if not client:
        hint = (
            "Set GROQ_API_KEY (and LLM_PROVIDER=groq) or OPENAI_API_KEY in .env."
        )
        if stream:
            async def _gen() -> AsyncIterator[str]:
                yield hint

            return _gen()
        return hint

    if stream:
        return client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
        )

    response = await client.chat.completions.create(
        model=model,
        messages=messages,
    )
    return response.choices[0].message.content or ""

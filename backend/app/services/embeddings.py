from typing import Optional

from openai import AsyncOpenAI

from app.config import settings

_client: Optional[AsyncOpenAI] = None


def get_openai_client() -> Optional[AsyncOpenAI]:
    global _client
    if not settings.openai_api_key:
        return None
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


async def embed_text(text: str) -> Optional[list[float]]:
    client = get_openai_client()
    if not client or not text.strip():
        return None
    try:
        response = await client.embeddings.create(
            model=settings.embedding_model,
            input=text[:8000],
        )
        return response.data[0].embedding
    except Exception:
        return None


async def chat_completion(messages: list[dict], stream: bool = False):
    client = get_openai_client()
    if not client:
        fallback = "AI features require OPENAI_API_KEY to be configured."
        if stream:
            async def _gen():
                yield fallback
            return _gen()
        return fallback

    if stream:
        return client.chat.completions.create(
            model=settings.chat_model,
            messages=messages,
            stream=True,
        )
    response = await client.chat.completions.create(
        model=settings.chat_model,
        messages=messages,
    )
    return response.choices[0].message.content or ""

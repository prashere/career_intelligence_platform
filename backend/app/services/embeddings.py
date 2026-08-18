from typing import Optional

from openai import AsyncOpenAI

from app.config import settings
from app.telemetry.langsmith import configure_langsmith, traceable, wrap_openai_client

configure_langsmith()

_embedding_client: Optional[AsyncOpenAI] = None


def get_embedding_client() -> Optional[AsyncOpenAI]:
    """Embeddings still use OpenAI (or a future Gemini provider). Groq has no embed API."""
    global _embedding_client
    if not settings.openai_api_key:
        return None
    if _embedding_client is None:
        raw = AsyncOpenAI(api_key=settings.openai_api_key)
        _embedding_client = wrap_openai_client(raw, chat_name="OpenAIEmbeddings")
    return _embedding_client


# Backward-compatible alias used by older code paths.
def get_openai_client() -> Optional[AsyncOpenAI]:
    return get_embedding_client()


@traceable(run_type="embedding", name="embed_text", tags=["embeddings"])
async def embed_text(text: str) -> Optional[list[float]]:
    client = get_embedding_client()
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


# Re-export chat helpers so existing imports keep working.
from app.services.llm import chat_completion, chat_completion_text, chat_configured, get_chat_client, get_chat_model

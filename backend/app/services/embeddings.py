"""Embedding providers with API, local, and lexical fallbacks."""

from __future__ import annotations

import asyncio
import logging
import math
import re
from abc import ABC, abstractmethod
from collections import Counter
from typing import Optional

import httpx
from openai import AsyncOpenAI

from app.config import settings
from app.telemetry.langsmith import configure_langsmith, traceable, wrap_openai_client

configure_langsmith()
logger = logging.getLogger(__name__)

_openai_client: Optional[AsyncOpenAI] = None
_fastembed_model: Optional[object] = None


class EmbeddingProvider(ABC):
    name: str
    # Raw-cosine band for merely-related text. Each model has its own similarity
    # floor, so a single affine rescale cannot serve all of them.
    cosine_floor: float = 0.15
    cosine_ceiling: float = 0.55

    @abstractmethod
    async def embed(self, text: str) -> Optional[list[float]]:
        ...


class OpenAIEmbeddingProvider(EmbeddingProvider):
    name = "openai"
    cosine_floor = 0.15
    cosine_ceiling = 0.55

    def __init__(self) -> None:
        self._client: Optional[AsyncOpenAI] = None

    def _client_or_none(self) -> Optional[AsyncOpenAI]:
        global _openai_client
        if not settings.openai_api_key:
            return None
        if _openai_client is None:
            raw = AsyncOpenAI(api_key=settings.openai_api_key)
            _openai_client = wrap_openai_client(raw, chat_name="OpenAIEmbeddings")
        return _openai_client

    async def embed(self, text: str) -> Optional[list[float]]:
        client = self._client_or_none()
        if not client or not text.strip():
            return None
        try:
            response = await client.embeddings.create(
                model=settings.embedding_model,
                input=text[:8000],
            )
            return response.data[0].embedding
        except Exception as exc:
            logger.warning("openai_embedding_failed", extra={"error": str(exc)})
            return None


class GeminiEmbeddingProvider(EmbeddingProvider):
    name = "gemini"
    cosine_floor = 0.50
    cosine_ceiling = 0.88

    async def embed(self, text: str) -> Optional[list[float]]:
        key = settings.gemini_api_key
        if not key or not text.strip():
            return None
        model = settings.gemini_embedding_model
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:embedContent?key={key}"
        )
        body = {"content": {"parts": [{"text": text[:8000]}]}}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=body)
                resp.raise_for_status()
                data = resp.json()
            embedding = data.get("embedding", {}).get("values")
            if embedding and isinstance(embedding, list):
                return [float(x) for x in embedding]
        except Exception as exc:
            logger.warning("gemini_embedding_failed", extra={"error": str(exc)})
        return None


class FastEmbedProvider(EmbeddingProvider):
    name = "fastembed"
    # BGE-family vectors are normalized and sit high: unrelated text still
    # scores ~0.4, so the usable band is narrow and offset upward.
    cosine_floor = 0.42
    cosine_ceiling = 0.75

    def _model(self) -> Optional[object]:
        global _fastembed_model
        if _fastembed_model is not None:
            return _fastembed_model
        try:
            from fastembed import TextEmbedding

            _fastembed_model = TextEmbedding(model_name=settings.fastembed_model)
            return _fastembed_model
        except Exception as exc:
            logger.warning("fastembed_unavailable", extra={"error": str(exc)})
            return None

    async def embed(self, text: str) -> Optional[list[float]]:
        model = self._model()
        if not model or not text.strip():
            return None
        try:
            loop = asyncio.get_event_loop()
            vectors = await loop.run_in_executor(None, lambda: list(model.embed([text[:8000]])))
            if vectors:
                return [float(x) for x in vectors[0]]
        except Exception as exc:
            logger.warning("fastembed_embed_failed", extra={"error": str(exc)})
        return None


_STOPWORDS = {
    "the", "and", "for", "with", "you", "your", "are", "was", "were", "this", "that",
    "from", "have", "has", "had", "will", "can", "all", "any", "our", "their", "its",
    "who", "which", "what", "when", "where", "how", "not", "but", "out", "off", "than",
    "then", "them", "they", "she", "his", "her", "him", "one", "two", "new", "also",
    "more", "most", "other", "such", "into", "over", "under", "about", "after", "before",
    "open", "applications", "opportunity", "programme", "program", "apply", "applicants",
}


def _tokenize(text: str) -> list[str]:
    return [
        w
        for w in re.findall(r"[a-z0-9]+", text.lower())
        if len(w) > 2 and w not in _STOPWORDS
    ]


def matched_terms(profile_terms: list[str], opportunity_text: str, limit: int = 4) -> list[str]:
    """Profile phrases (interests, skills, regions) that literally appear in the listing."""
    text_low = (opportunity_text or "").lower()
    hits: list[str] = []
    seen: set[str] = set()
    for term in profile_terms:
        cleaned = (term or "").strip()
        if len(cleaned) < 3:
            continue
        key = cleaned.lower()
        if key in seen or key in _STOPWORDS:
            continue
        if key in text_low:
            seen.add(key)
            hits.append(cleaned)
        if len(hits) >= limit:
            break
    return hits


def embedding_dimensions(vector: Optional[list[float]]) -> int:
    return len(vector) if vector else 0


def lexical_similarity(profile_text: str, opportunity_text: str) -> float:
    """Deterministic BM25-style similarity mapped to 0–1 (no API)."""
    ta = _tokenize(profile_text)
    tb = _tokenize(opportunity_text)
    if not ta or not tb:
        return 0.0

    doc_freq: Counter[str] = Counter()
    for token in set(ta):
        if token in tb:
            doc_freq[token] += 1

    k1, b = 1.2, 0.75
    avg_dl = max(len(tb), 1)
    score = 0.0
    tf_counter = Counter(tb)
    for token in set(ta):
        if token not in tf_counter:
            continue
        tf = tf_counter[token]
        dl = len(tb)
        idf = math.log(1 + (1 - 0.5) / (0.5 + doc_freq[token] / max(len(set(ta)), 1)))
        denom = tf + k1 * (1 - b + b * dl / avg_dl)
        score += idf * (tf * (k1 + 1)) / denom

    # Normalize — typical scores are small; scale into usable band
    normalized = score / (score + 4.0)
    return max(0.0, min(1.0, normalized))


def calibrate_cosine_similarity(raw_cosine: float, provider: Optional[str] = None) -> float:
    """Rescale a raw cosine into 0–1 using the band that matches the source model."""
    floor, ceiling = PROVIDER_COSINE_BANDS.get(
        (provider or "").lower(), (DEFAULT_COSINE_FLOOR, DEFAULT_COSINE_CEILING)
    )
    span = ceiling - floor
    if span <= 0:
        return 0.0
    return max(0.0, min(1.0, (raw_cosine - floor) / span))


def cosine_similarity_vectors(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def build_provider_chain() -> list[EmbeddingProvider]:
    explicit = (settings.embedding_provider or "").strip().lower()
    all_providers: dict[str, EmbeddingProvider] = {
        "openai": OpenAIEmbeddingProvider(),
        "gemini": GeminiEmbeddingProvider(),
        "fastembed": FastEmbedProvider(),
    }
    if explicit and explicit in all_providers:
        return [all_providers[explicit]]
    chain: list[EmbeddingProvider] = []
    if settings.openai_api_key:
        chain.append(all_providers["openai"])
    if settings.gemini_api_key:
        chain.append(all_providers["gemini"])
    chain.append(all_providers["fastembed"])
    return chain


# Backward-compatible aliases
def get_embedding_client() -> Optional[AsyncOpenAI]:
    return OpenAIEmbeddingProvider()._client_or_none()


def get_openai_client() -> Optional[AsyncOpenAI]:
    return get_embedding_client()


DEFAULT_COSINE_FLOOR = 0.15
DEFAULT_COSINE_CEILING = 0.55

PROVIDER_COSINE_BANDS: dict[str, tuple[float, float]] = {
    p.name: (p.cosine_floor, p.cosine_ceiling)
    for p in (OpenAIEmbeddingProvider(), GeminiEmbeddingProvider(), FastEmbedProvider())
}


@traceable(run_type="embedding", name="embed_text", tags=["embeddings"])
async def embed_text_with_provider(text: str) -> tuple[Optional[list[float]], Optional[str]]:
    """Embed text, also reporting which provider produced the vector."""
    if not text.strip():
        return None, None
    for provider in build_provider_chain():
        vector = await provider.embed(text)
        if vector:
            return vector, provider.name
    return None, None


async def embed_text(text: str) -> Optional[list[float]]:
    vector, _ = await embed_text_with_provider(text)
    return vector


# Re-export chat helpers so existing imports keep working.
from app.services.llm import chat_completion, chat_completion_text, chat_configured, get_chat_client, get_chat_model

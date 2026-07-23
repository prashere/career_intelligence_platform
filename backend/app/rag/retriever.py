import math
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DocumentChunk, Opportunity
from app.services.embeddings import embed_text


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


async def index_opportunity(session: AsyncSession, opportunity_id: str) -> int:
    opp = await session.get(Opportunity, opportunity_id)
    if not opp:
        return 0

    text_parts = [
        f"Title: {opp.title}",
        f"Institution: {opp.institution or 'Unknown'}",
        f"Program: {opp.program or 'N/A'}",
        f"Summary: {opp.summary or ''}",
        f"Requirements: {', '.join(opp.requirements or [])}",
        f"Tags: {', '.join(opp.tags or [])}",
    ]
    full_text = "\n".join(text_parts)
    chunks = _chunk_text(full_text, chunk_size=800, overlap=100)

    existing = await session.execute(
        select(DocumentChunk).where(DocumentChunk.opportunity_id == opportunity_id)
    )
    for chunk in existing.scalars().all():
        await session.delete(chunk)

    created = 0
    for idx, content in enumerate(chunks):
        embedding = await embed_text(content)
        session.add(
            DocumentChunk(
                opportunity_id=opportunity_id,
                content=content,
                chunk_index=idx,
                source_url=opp.url,
                embedding=embedding,
            )
        )
        created += 1

    if not opp.embedding:
        opp.embedding = await embed_text(full_text)

    await session.commit()
    return created


def _chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + chunk_size])
        start += chunk_size - overlap
    return chunks


async def retrieve_context(
    session: AsyncSession,
    opportunity_id: str,
    query: str,
    top_k: int = 5,
) -> tuple[str, list[str]]:
    query_embedding = await embed_text(query)
    result = await session.execute(
        select(DocumentChunk).where(DocumentChunk.opportunity_id == opportunity_id)
    )
    chunks = result.scalars().all()

    if not chunks:
        opp = await session.get(Opportunity, opportunity_id)
        if opp:
            await index_opportunity(session, opportunity_id)
            result = await session.execute(
                select(DocumentChunk).where(DocumentChunk.opportunity_id == opportunity_id)
            )
            chunks = result.scalars().all()

    if not query_embedding:
        selected = chunks[:top_k]
    else:
        scored = []
        for chunk in chunks:
            if chunk.embedding:
                scored.append((_cosine(query_embedding, chunk.embedding), chunk))
            else:
                scored.append((0.0, chunk))
        scored.sort(key=lambda x: x[0], reverse=True)
        selected = [c for _, c in scored[:top_k]]

    context_parts = [c.content for c in selected]
    citations = list({c.source_url for c in selected if c.source_url})
    return "\n\n---\n\n".join(context_parts), citations


async def answer_question(
    session: AsyncSession,
    opportunity_id: str,
    question: str,
    profile_context: str = "",
) -> tuple[str, list[str]]:
    context, citations = await retrieve_context(session, opportunity_id, question)
    if not context.strip():
        return (
            "I don't have enough indexed context about this opportunity yet. "
            "Try re-indexing or ask after ingestion completes.",
            [],
        )

    from app.services.embeddings import chat_completion

    system = (
        "You are a career intelligence assistant. Answer using ONLY the provided context. "
        "If the answer is not in the context, say you don't have enough information. "
        "Never fabricate deadlines or requirements."
    )
    user = f"Profile context:\n{profile_context}\n\nOpportunity context:\n{context}\n\nQuestion: {question}"
    reply = await chat_completion(
        [{"role": "system", "content": system}, {"role": "user", "content": user}]
    )
    return reply, citations

"""RAG evaluation harness."""

import pytest

from app.rag.retriever import _chunk_text


def test_chunk_text_single():
    assert _chunk_text("short") == ["short"]


def test_chunk_text_multiple():
    text = "a" * 1000
    chunks = _chunk_text(text, chunk_size=400, overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 400 for c in chunks)

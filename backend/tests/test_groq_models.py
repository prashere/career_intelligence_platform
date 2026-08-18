"""Groq model tier and extraction defaults."""

from app.services.groq_models import (
    GROQ_DEFAULT_CHAT_MODEL,
    GROQ_DEFAULT_EXTRACTION_MODEL,
    groq_extraction_models_to_try,
    groq_free_tpm_for_model,
    groq_models_to_try,
    is_groq_request_too_large,
    resolve_groq_model,
)


def test_resolve_deprecated_llama_8b():
    assert resolve_groq_model("llama-3.1-8b-instant") == GROQ_DEFAULT_CHAT_MODEL


def test_resolve_current_model_passthrough():
    assert resolve_groq_model("openai/gpt-oss-20b") == "openai/gpt-oss-20b"


def test_groq_models_to_try_includes_fallbacks():
    models = groq_models_to_try("llama-3.1-8b-instant")
    assert models[0] == GROQ_DEFAULT_CHAT_MODEL


def test_extraction_default_is_high_tpm_model():
    assert GROQ_DEFAULT_EXTRACTION_MODEL == "groq/compound-mini"
    assert groq_free_tpm_for_model(GROQ_DEFAULT_EXTRACTION_MODEL) >= 70000


def test_gpt_oss_20b_free_tpm_is_8000():
    assert groq_free_tpm_for_model("openai/gpt-oss-20b") == 8000


def test_extraction_model_chain_starts_with_configured():
    models = groq_extraction_models_to_try("groq/compound-mini")
    assert models[0] == "groq/compound-mini"
    assert len(models) >= 2


def test_request_too_large_detection():
    class FakeExc(Exception):
        pass

    exc = FakeExc("Request too large for model Limit 8000, Requested 10986")
    assert is_groq_request_too_large(exc)

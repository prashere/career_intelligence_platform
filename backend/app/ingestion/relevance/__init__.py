"""Evidence-based relevance gating for the ingestion pipeline."""

from app.ingestion.relevance.config import RelevanceConfig, get_relevance_config
from app.ingestion.relevance.gate import Decision, Verdict, evaluate, explain
from app.ingestion.relevance.signals import (
    Candidate,
    ProfileTerms,
    Signal,
    profile_terms_from_envelope,
)

__all__ = [
    "Candidate",
    "Decision",
    "ProfileTerms",
    "RelevanceConfig",
    "Signal",
    "Verdict",
    "evaluate",
    "explain",
    "get_relevance_config",
    "profile_terms_from_envelope",
]

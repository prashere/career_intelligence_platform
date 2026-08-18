"""Tier 0 eligibility — gate survivors only."""

from __future__ import annotations

from app.models import Opportunity


def is_eligible_for_verification(opportunity: Opportunity) -> bool:
    meta = opportunity.ingestion_meta or {}
    if not meta.get("gate"):
        return False
    verdict = (meta.get("gate") or {}).get("verdict")
    return verdict in ("admit", "investigate")

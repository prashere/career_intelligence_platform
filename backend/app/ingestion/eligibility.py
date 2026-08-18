"""Read-time eligibility filtering (Stage 7)."""

from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Opportunity, UserProfile
from app.services.profile_intake import compiled_dir
from app.services.profile_storage import load_eligibility_rules as load_eligibility_rules_db


def load_eligibility_rules() -> dict[str, Any]:
    """CLI fallback — read eligibility_rules.json from disk."""
    path = compiled_dir() / "eligibility_rules.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


async def load_eligibility_rules_for_user(session: AsyncSession, user_id: str) -> dict[str, Any]:
    rules = await load_eligibility_rules_db(session, user_id)
    if rules:
        return rules
    return load_eligibility_rules()


def passes_eligibility(opp: Opportunity, rules: dict[str, Any], profile: Optional[UserProfile] = None) -> bool:
    text = f"{opp.title} {opp.summary or ''} {opp.institution or ''}".lower()

    for phrase in rules.get("reject_if_text_contains") or []:
        if phrase and phrase.lower() in text:
            return False

    require_funding = rules.get("require_funding")
    if require_funding == "full_only" and opp.funding_type not in ("full", None):
        if opp.funding_type in ("partial", "self"):
            return False

    return True

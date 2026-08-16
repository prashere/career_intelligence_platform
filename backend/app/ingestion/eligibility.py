"""Read-time eligibility filtering (Stage 7)."""

from __future__ import annotations

import json
from typing import Any, Optional

from app.models import Opportunity, UserProfile
from app.services.profile_intake import compiled_dir


def load_eligibility_rules() -> dict[str, Any]:
    path = compiled_dir() / "eligibility_rules.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


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

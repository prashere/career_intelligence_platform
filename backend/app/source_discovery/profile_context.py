"""Load compiled profile context for discovery queries."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.profile_storage import load_artifacts, load_structured_profile


async def load_discovery_profile_context(session: AsyncSession, user_id: str) -> dict[str, Any]:
    artifacts = await load_artifacts(session, user_id)
    structured = await load_structured_profile(session, user_id)

    filter_config = (artifacts.filter_config or {}) if artifacts else {}
    ingestion = (artifacts.ingestion_sources or {}) if artifacts else {}

    prefs: dict[str, Any] = {}
    identity: dict[str, Any] = {}
    if structured:
        prefs = structured.get("preferences") or {}
        identity = structured.get("identity") or {}

    return {
        "filter_config": filter_config,
        "must_match_any": filter_config.get("must_match_any") or [],
        "profile_match_any": filter_config.get("profile_match_any") or [],
        "region_match_any": filter_config.get("region_match_any") or [],
        "target_degree_levels": filter_config.get("target_degree_levels") or [],
        "target_fields": prefs.get("target_fields") or [],
        "target_regions": prefs.get("target_regions") or [],
        "target_degree": prefs.get("target_degree") or "Mixed",
        "nationality": identity.get("nationality") or "",
        "discovery_mode": ingestion.get("discovery_mode") or prefs.get("discovery_mode") or "open",
        "manual_channels": ingestion.get("manual_channels") or [],
    }

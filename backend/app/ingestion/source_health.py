"""Source health — consecutive failure tracking and auto-deactivate (Task 5)."""

from __future__ import annotations

from app.config import settings
from app.models import OpportunitySource


def record_source_failure(source: OpportunitySource, error: str) -> bool:
    """Increment failure counter; deactivate when threshold reached. Returns True if deactivated."""
    source.last_error = error
    source.consecutive_failures = (source.consecutive_failures or 0) + 1
    if source.consecutive_failures >= settings.source_failure_deactivate_threshold:
        source.is_active = False
        source.last_error = (
            f"{error} [auto-deactivated after {source.consecutive_failures} consecutive failures]"
        )
        return True
    return False


def deactivate_over_threshold_sources(sources: list[OpportunitySource]) -> list[str]:
    """Deactivate any active sources already above threshold (safety sweep)."""
    deactivated: list[str] = []
    threshold = settings.source_failure_deactivate_threshold
    for source in sources:
        if source.is_active and (source.consecutive_failures or 0) >= threshold:
            source.is_active = False
            source.last_error = (
                f"[auto-deactivated: {source.consecutive_failures} consecutive failures]"
            )
            deactivated.append(source.name)
    return deactivated

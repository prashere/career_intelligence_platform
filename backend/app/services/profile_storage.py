"""Per-user profile data in the database (replaces docs/profile/ for runtime)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ProfileIntakeDraft,
    ProfilePipelineRun,
    ProfileSubmission,
    UserOpportunity,
    UserProfile,
    UserProfileArtifacts,
    UserStructuredProfile,
)
from app.schemas.profile_intake import StructuredProfile


async def _get_or_create_draft(session: AsyncSession, user_id: str) -> ProfileIntakeDraft:
    result = await session.execute(
        select(ProfileIntakeDraft).where(ProfileIntakeDraft.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row:
        return row
    row = ProfileIntakeDraft(user_id=user_id)
    session.add(row)
    await session.flush()
    return row


async def _get_or_create_structured(session: AsyncSession, user_id: str) -> UserStructuredProfile:
    result = await session.execute(
        select(UserStructuredProfile).where(UserStructuredProfile.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row:
        return row
    row = UserStructuredProfile(user_id=user_id)
    session.add(row)
    await session.flush()
    return row


async def _get_or_create_artifacts(session: AsyncSession, user_id: str) -> UserProfileArtifacts:
    result = await session.execute(
        select(UserProfileArtifacts).where(UserProfileArtifacts.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row:
        return row
    row = UserProfileArtifacts(user_id=user_id)
    session.add(row)
    await session.flush()
    return row


async def load_draft(session: AsyncSession, user_id: str) -> dict[str, Any] | None:
    result = await session.execute(
        select(ProfileIntakeDraft).where(ProfileIntakeDraft.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if not row or not row.form and not row.cv_text and row.step == 0:
        return None
    return {
        "step": row.step,
        "form": row.form or {},
        "cv_text": row.cv_text or "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def save_draft(
    session: AsyncSession,
    user_id: str,
    form: dict[str, Any],
    step: int,
    cv_text: str | None = None,
) -> dict[str, Any]:
    row = await _get_or_create_draft(session, user_id)
    row.step = step
    row.form = form
    if cv_text is not None:
        row.cv_text = cv_text
    row.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(row)
    return {
        "step": row.step,
        "form": row.form,
        "cv_text": row.cv_text,
        "updated_at": row.updated_at.isoformat(),
    }


async def load_cv_text(session: AsyncSession, user_id: str) -> str:
    result = await session.execute(
        select(ProfileIntakeDraft).where(ProfileIntakeDraft.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    return row.cv_text if row else ""


async def save_cv_text(session: AsyncSession, user_id: str, text: str) -> None:
    row = await _get_or_create_draft(session, user_id)
    row.cv_text = text
    row.updated_at = datetime.now(timezone.utc)
    await session.commit()


async def save_submission(
    session: AsyncSession,
    user_id: str,
    form: dict[str, Any],
    cv_text: str,
) -> str:
    now = datetime.now(timezone.utc)
    submission_id = now.strftime("%Y%m%dT%H%M%SZ")
    session.add(
        ProfileSubmission(
            user_id=user_id,
            submission_id=submission_id,
            form=form,
            cv_text=cv_text,
        )
    )
    await session.commit()
    return submission_id


async def get_submission(
    session: AsyncSession,
    user_id: str,
    submission_id: str,
) -> dict[str, Any] | None:
    result = await session.execute(
        select(ProfileSubmission).where(
            ProfileSubmission.user_id == user_id,
            ProfileSubmission.submission_id == submission_id,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        return None
    return {
        "schema_version": "1.0",
        "submission_id": row.submission_id,
        "submitted_at": row.created_at.isoformat(),
        "source": "web_ui",
        "form": row.form,
        "cv_text": row.cv_text,
        "cv_char_count": len(row.cv_text or ""),
    }


async def get_latest_submission(session: AsyncSession, user_id: str) -> dict[str, Any] | None:
    result = await session.execute(
        select(ProfileSubmission)
        .where(ProfileSubmission.user_id == user_id)
        .order_by(ProfileSubmission.created_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if not row:
        return None
    return {
        "schema_version": "1.0",
        "submission_id": row.submission_id,
        "submitted_at": row.created_at.isoformat(),
        "source": "web_ui",
        "form": row.form,
        "cv_text": row.cv_text,
        "cv_char_count": len(row.cv_text or ""),
    }


async def save_prefill(session: AsyncSession, user_id: str, data: dict[str, Any], *, commit: bool = True) -> None:
    row = await _get_or_create_structured(session, user_id)
    row.prefill = data
    row.updated_at = datetime.now(timezone.utc)
    if commit:
        await session.commit()
    else:
        await session.flush()


async def load_prefill(session: AsyncSession, user_id: str) -> dict[str, Any] | None:
    result = await session.execute(
        select(UserStructuredProfile).where(UserStructuredProfile.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    return row.prefill if row and row.prefill else None


async def save_extraction(session: AsyncSession, user_id: str, data: dict[str, Any], *, commit: bool = True) -> None:
    row = await _get_or_create_structured(session, user_id)
    row.extraction = data
    row.updated_at = datetime.now(timezone.utc)
    if commit:
        await session.commit()
    else:
        await session.flush()


async def load_extraction(session: AsyncSession, user_id: str) -> dict[str, Any] | None:
    result = await session.execute(
        select(UserStructuredProfile).where(UserStructuredProfile.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    return row.extraction if row and row.extraction else None


async def save_structured_profile(
    session: AsyncSession,
    user_id: str,
    profile: StructuredProfile | dict[str, Any],
    *,
    commit: bool = True,
) -> None:
    data = profile.model_dump(mode="json") if isinstance(profile, StructuredProfile) else profile
    row = await _get_or_create_structured(session, user_id)
    row.data = data
    row.schema_version = data.get("schema_version", "1.0")
    row.updated_at = datetime.now(timezone.utc)
    if commit:
        await session.commit()
    else:
        await session.flush()


async def load_structured_profile(session: AsyncSession, user_id: str) -> dict[str, Any] | None:
    result = await session.execute(
        select(UserStructuredProfile).where(UserStructuredProfile.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    return row.data if row and row.data else None


async def save_artifacts(session: AsyncSession, user_id: str, artifacts: dict[str, Any], *, commit: bool = True) -> None:
    row = await _get_or_create_artifacts(session, user_id)
    row.filter_config = artifacts.get("filter_config")
    row.eligibility_rules = artifacts.get("eligibility_rules")
    row.ranking_config = artifacts.get("ranking_config")
    row.ingestion_sources = artifacts.get("ingestion_sources")
    row.profile_truth = artifacts.get("profile_truth")
    row.compiled_at = datetime.now(timezone.utc)
    if commit:
        await session.commit()
    else:
        await session.flush()


async def load_artifacts(session: AsyncSession, user_id: str) -> UserProfileArtifacts | None:
    result = await session.execute(
        select(UserProfileArtifacts).where(UserProfileArtifacts.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def load_filter_config(session: AsyncSession, user_id: str) -> dict[str, Any]:
    row = await load_artifacts(session, user_id)
    return row.filter_config if row and row.filter_config else {}


async def load_eligibility_rules(session: AsyncSession, user_id: str) -> dict[str, Any]:
    row = await load_artifacts(session, user_id)
    return row.eligibility_rules if row and row.eligibility_rules else {}


async def load_ranking_config(session: AsyncSession, user_id: str) -> dict[str, Any]:
    row = await load_artifacts(session, user_id)
    if row and row.ranking_config:
        return row.ranking_config
    return {
        "discovery_mode": "open",
        "university_match_weight": 0.2,
        "region_match_weight": 0.1,
        "interest_match_weight": 0.15,
        "language_match_weight": 0.08,
        "open_to_relocation": True,
        "manual_channels": [],
    }


async def load_ingestion_sources(session: AsyncSession, user_id: str) -> dict[str, Any]:
    row = await load_artifacts(session, user_id)
    return row.ingestion_sources if row and row.ingestion_sources else {}


async def intake_status(session: AsyncSession, user_id: str) -> dict[str, Any]:
    draft = await load_draft(session, user_id)
    structured = await load_structured_profile(session, user_id)
    artifacts = await load_artifacts(session, user_id)
    has_submission = await session.execute(
        select(ProfileSubmission.id)
        .where(ProfileSubmission.user_id == user_id)
        .limit(1)
    )
    structured_row = await session.execute(
        select(UserStructuredProfile).where(UserStructuredProfile.user_id == user_id)
    )
    structured_db = structured_row.scalar_one_or_none()

    has_compiled = bool(
        artifacts
        and artifacts.filter_config
        and artifacts.eligibility_rules
        and artifacts.ranking_config
        and artifacts.ingestion_sources
    )

    return {
        "has_draft": draft is not None,
        "current_step": (draft or {}).get("step", 0),
        "has_cv": bool((draft or {}).get("cv_text")),
        "has_form_answers": has_submission.scalar_one_or_none() is not None,
        "has_extraction_output": bool(structured_db and structured_db.extraction),
        "has_structured_profile": structured is not None,
        "has_compiled_artifacts": has_compiled,
        "has_profile_truth": bool(artifacts and artifacts.profile_truth),
        "updated_at": (draft or {}).get("updated_at"),
    }


async def delete_user_profile_data(session: AsyncSession, user_id: str) -> None:
    """Remove all profile intake, structured data, artifacts, and pipeline runs for a user."""
    profile_result = await session.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    profile = profile_result.scalar_one_or_none()
    if profile:
        await session.execute(
            delete(UserOpportunity).where(UserOpportunity.user_id == profile.id)
        )
        profile.name = ""
        profile.long_term_goals = ""
        profile.research_interests = []
        profile.skills = []
        profile.target_regions = []
        profile.target_universities = []
        profile.degree_level = None
        profile.constraints = {}
        profile.projects = []
        profile.connections = []
        profile.embedding = None

    await session.execute(delete(ProfileIntakeDraft).where(ProfileIntakeDraft.user_id == user_id))
    await session.execute(delete(ProfileSubmission).where(ProfileSubmission.user_id == user_id))
    await session.execute(delete(UserStructuredProfile).where(UserStructuredProfile.user_id == user_id))
    await session.execute(delete(UserProfileArtifacts).where(UserProfileArtifacts.user_id == user_id))
    await session.execute(delete(ProfilePipelineRun).where(ProfilePipelineRun.user_id == user_id))
    await session.commit()

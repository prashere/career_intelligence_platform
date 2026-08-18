"""Orchestrate automated profile pipeline stages after intake submit."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.envelope_store import sync_platform_envelope
from app.models import ProfilePipelineRun, ProfilePipelineRunStatus, User
from app.schemas.profile_intake import StructuredProfile
from app.services.profile_extraction import extract_cv_from_prefill, repair_extraction
from app.services.profile_intake import validate_structured_profile
from app.services.profile_pipeline import (
    compile_profile_artifacts,
    merge_prefill_and_extraction,
    prefill_from_form,
)
from app.services.profile_source_seeding import seed_sources_from_data
from app.services.profile_storage import (
    get_submission,
    load_cv_text,
    load_structured_profile,
    save_artifacts,
    save_extraction,
    save_prefill,
    save_structured_profile,
)
from app.services.profile_sync import sync_user_profile_from_structured
from app.telemetry.langsmith import traceable

PIPELINE_STEP_NAMES = [
    "prefill",
    "extract_cv",
    "merge",
    "repair",
    "compile",
    "activate",
    "ingest",
]


def init_pipeline_steps() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "status": "pending",
            "started_at": None,
            "finished_at": None,
            "error": None,
            "logs": [],
        }
        for name in PIPELINE_STEP_NAMES
    ]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_step_log(steps: list[dict[str, Any]], name: str, message: str) -> list[dict[str, Any]]:
    updated: list[dict[str, Any]] = []
    for step in steps:
        row = dict(step)
        if row["name"] == name:
            logs = list(row.get("logs") or [])
            logs.append(f"{_now_iso()} | {message}")
            row["logs"] = logs
        updated.append(row)
    return updated


def set_step_status(
    steps: list[dict[str, Any]],
    name: str,
    status: str,
    error: str | None = None,
    log: str | None = None,
) -> list[dict[str, Any]]:
    updated: list[dict[str, Any]] = []
    for step in steps:
        row = dict(step)
        if row["name"] == name:
            if log:
                logs = list(row.get("logs") or [])
                logs.append(f"{_now_iso()} | {log}")
                row["logs"] = logs
            if status == "running" and not row.get("started_at"):
                row["started_at"] = _now_iso()
            if status in ("completed", "failed", "skipped"):
                row["finished_at"] = _now_iso()
            row["status"] = status
            row["error"] = error
        updated.append(row)
    return updated


async def create_profile_pipeline_run(
    session: AsyncSession,
    user_id: str,
    submission_id: str,
) -> ProfilePipelineRun:
    run = ProfilePipelineRun(
        user_id=user_id,
        submission_id=submission_id,
        status=ProfilePipelineRunStatus.queued,
        steps=init_pipeline_steps(),
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def get_latest_pipeline_run(
    session: AsyncSession,
    user_id: str,
) -> ProfilePipelineRun | None:
    result = await session.execute(
        select(ProfilePipelineRun)
        .where(ProfilePipelineRun.user_id == user_id)
        .order_by(ProfilePipelineRun.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def update_pipeline_step(
    session: AsyncSession,
    run_id: str,
    step_name: str,
    status: str,
    error: str | None = None,
    log: str | None = None,
) -> ProfilePipelineRun | None:
    run = await session.get(ProfilePipelineRun, run_id)
    if not run:
        return None
    steps = run.steps or init_pipeline_steps()
    if log:
        steps = append_step_log(steps, step_name, log)
    steps = set_step_status(steps, step_name, status, error)
    run.steps = steps
    if status == "running":
        run.current_step = step_name
    await session.commit()
    await session.refresh(run)
    return run


async def finalize_pipeline_run(
    session: AsyncSession,
    run_id: str,
    *,
    success: bool,
    error: str | None = None,
) -> ProfilePipelineRun | None:
    """Mark pipeline run completed/failed after ingest (or on ingest failure)."""
    run = await session.get(ProfilePipelineRun, run_id)
    if not run:
        return None
    run.status = ProfilePipelineRunStatus.completed if success else ProfilePipelineRunStatus.failed
    run.finished_at = datetime.now(timezone.utc)
    run.current_step = None
    if error:
        run.error_message = error
    await session.commit()
    await session.refresh(run)
    return run


def pipeline_run_to_dict(run: ProfilePipelineRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "status": run.status.value,
        "current_step": run.current_step,
        "steps": run.steps or [],
        "error": run.error_message,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


async def build_profile_summary(session: AsyncSession, user_id: str) -> dict[str, Any] | None:
    structured = await load_structured_profile(session, user_id)
    if not structured:
        return None

    from app.services.profile_storage import load_artifacts

    prefs = structured.get("preferences") or {}
    sources = structured.get("sources") or {}
    aggregators = [
        a.get("name") or a.get("id")
        for a in (sources.get("aggregators") or [])
        if a.get("enabled")
    ]
    artifacts = await load_artifacts(session, user_id)
    excerpt = None
    if artifacts and artifacts.profile_truth:
        text = artifacts.profile_truth.strip()
        excerpt = text[:600] + ("…" if len(text) > 600 else "")

    return {
        "full_name": (structured.get("identity") or {}).get("full_name"),
        "discovery_mode": prefs.get("discovery_mode"),
        "aggregator_names": aggregators,
        "profile_truth_excerpt": excerpt,
    }


async def _persist_run(session: AsyncSession, run: ProfilePipelineRun, **kwargs: Any) -> None:
    for key, value in kwargs.items():
        setattr(run, key, value)
    await session.commit()
    await session.refresh(run)


async def _merge_and_validate(
    prefill: dict[str, Any],
    extraction: dict[str, Any],
) -> tuple[StructuredProfile | None, list[str], dict[str, Any]]:
    merged = merge_prefill_and_extraction(prefill, extraction)
    profile, errors = validate_structured_profile(merged)
    return profile, errors, extraction


def _process_pipeline_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": inputs.get("run_id"),
        "user_id": inputs.get("user_id"),
        "submission_id": inputs.get("submission_id"),
    }


def _process_pipeline_outputs(output: Any) -> dict[str, Any]:
    if output is None:
        return {"status": "unknown"}
    return {
        "status": getattr(output, "status", None) and output.status.value,
        "current_step": getattr(output, "current_step", None),
        "run_id": getattr(output, "id", None),
    }


@traceable(
    run_type="chain",
    name="profile_pipeline",
    process_inputs=_process_pipeline_inputs,
    process_outputs=_process_pipeline_outputs,
    tags=["profile_setup", "profile_pipeline"],
)
async def run_profile_pipeline(
    session: AsyncSession,
    run_id: str,
    user_id: str,
    submission_id: str,
) -> ProfilePipelineRun:
    run = await session.get(ProfilePipelineRun, run_id)
    if not run:
        raise ValueError(f"Pipeline run {run_id} not found")

    user = await session.get(User, user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")

    steps = list(run.steps or init_pipeline_steps())
    await _persist_run(
        session,
        run,
        status=ProfilePipelineRunStatus.running,
        started_at=datetime.now(timezone.utc),
        steps=steps,
        error_message=None,
        finished_at=None,
    )

    current_step = "prefill"

    try:
        steps = set_step_status(
            steps, "prefill", "running", log="Reading your form answers and CV reference"
        )
        current_step = "prefill"
        await _persist_run(session, run, current_step=current_step, steps=steps)

        raw = await get_submission(session, user_id, submission_id)
        if not raw:
            raise RuntimeError(f"Submission {submission_id} not found for user")

        from app.services.source_outcomes import load_registry_outcome_stats

        source_outcomes = await load_registry_outcome_stats(session)
        prefill = prefill_from_form(raw.get("form") or {}, source_outcomes=source_outcomes)
        await save_prefill(session, user_id, prefill, commit=False)
        steps = set_step_status(steps, "prefill", "completed", log="Prefill rules saved")
        await _persist_run(session, run, steps=steps)

        steps = set_step_status(
            steps, "extract_cv", "running", log="Sending CV to extraction model (Groq)"
        )
        current_step = "extract_cv"
        await _persist_run(session, run, current_step=current_step, steps=steps)

        cv_text = await load_cv_text(session, user_id) or raw.get("cv_text") or ""
        if not cv_text.strip():
            raise RuntimeError("CV text missing")

        # LLM call does not use the DB session — keep one commit boundary after it returns.
        extraction = await extract_cv_from_prefill(
            prefill,
            cv_text,
            user_id=user_id,
            pipeline_run_id=run_id,
            submission_id=submission_id,
        )
        await save_extraction(session, user_id, extraction, commit=False)
        steps = set_step_status(
            steps,
            "extract_cv",
            "completed",
            log=f"CV parsed ({len(cv_text):,} characters of source text)",
        )
        await _persist_run(session, run, steps=steps)

        steps = set_step_status(steps, "merge", "running", log="Merging form answers with CV extraction")
        current_step = "merge"
        await _persist_run(session, run, current_step=current_step, steps=steps)

        profile, errors, extraction = await _merge_and_validate(prefill, extraction)
        if profile is None:
            steps = set_step_status(
                steps, "repair", "running", log=f"Repairing extraction ({len(errors)} validation issues)"
            )
            current_step = "repair"
            await _persist_run(session, run, current_step=current_step, steps=steps)

            extraction = await repair_extraction(
                prefill,
                cv_text,
                errors,
                extraction,
                user_id=user_id,
                pipeline_run_id=run_id,
                submission_id=submission_id,
            )
            await save_extraction(session, user_id, extraction, commit=False)
            profile, errors, extraction = await _merge_and_validate(prefill, extraction)
            if profile is None:
                error_text = "; ".join(errors)
                steps = set_step_status(steps, "repair", "failed", error_text)
                steps = set_step_status(steps, "merge", "failed", error_text)
                raise RuntimeError(f"Merge validation failed after repair: {error_text}")

            steps = set_step_status(steps, "repair", "completed", log="Extraction repaired successfully")
        else:
            steps = set_step_status(steps, "repair", "skipped", log="No repair needed")

        await save_structured_profile(session, user_id, profile, commit=False)
        steps = set_step_status(steps, "merge", "completed", log="Structured profile validated and saved")
        await _persist_run(session, run, steps=steps)

        steps = set_step_status(
            steps, "compile", "running", log="Building filter rules, eligibility, and ranking config"
        )
        current_step = "compile"
        await _persist_run(session, run, current_step=current_step, steps=steps)

        artifacts = compile_profile_artifacts(profile)
        await save_artifacts(session, user_id, artifacts, commit=False)
        steps = set_step_status(steps, "compile", "completed", log="Matching preferences compiled")
        await _persist_run(session, run, steps=steps)

        steps = set_step_status(
            steps, "activate", "running", log="Activating profile for discovery and syncing account"
        )
        current_step = "activate"
        await _persist_run(session, run, current_step=current_step, steps=steps)

        envelope = artifacts.get("filter_config") or {}
        await sync_platform_envelope(session, envelope, commit=False)
        ingestion_data = artifacts.get("ingestion_sources") or {}
        await seed_sources_from_data(session, ingestion_data, commit=False)
        await sync_user_profile_from_structured(
            session,
            profile.model_dump(mode="json"),
            user=user,
            commit=False,
        )
        agg_count = len(
            [a for a in (profile.sources.aggregators or []) if a.enabled]
        )
        steps = set_step_status(
            steps,
            "activate",
            "completed",
            log=f"Profile activated ({agg_count} discovery sources enabled)",
        )
        steps = set_step_status(
            steps, "ingest", "pending", log="Queued: fetch opportunities and rank matches"
        )
        await _persist_run(
            session,
            run,
            status=ProfilePipelineRunStatus.running,
            current_step="ingest",
            finished_at=None,
            steps=steps,
        )
        return run

    except Exception as exc:
        await session.rollback()
        error_text = str(exc)
        run = await session.get(ProfilePipelineRun, run_id)
        if not run:
            raise
        steps = run.steps or init_pipeline_steps()
        steps = set_step_status(steps, current_step, "failed", error_text)
        await _persist_run(
            session,
            run,
            status=ProfilePipelineRunStatus.failed,
            finished_at=datetime.now(timezone.utc),
            steps=steps,
            error_message=error_text,
        )
        raise

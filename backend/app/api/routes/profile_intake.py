"""Profile intake API — form draft, CV, prompt generation, validation."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models import ProfilePipelineRunStatus, User
from app.schemas.profile_intake_api import (
    IntakeCvUpdate,
    IntakeCvUploadResponse,
    IntakeDraftResponse,
    IntakeDraftUpdate,
    IntakePromptResponse,
    IntakeStatusResponse,
    IntakeStructuredResponse,
    IntakeSubmitResponse,
    IntakeValidateRequest,
    IntakeValidateResponse,
    PipelineStatus,
    PipelineStepStatus,
    ProfileSummary,
)
from app.services import profile_intake as intake
from app.services.cv_extract import extract_text_from_cv_file
from app.services.profile_orchestrator import (
    build_profile_summary,
    create_profile_pipeline_run,
    get_latest_pipeline_run,
    init_pipeline_steps,
    pipeline_run_to_dict,
)
from app.services.profile_storage import (
    delete_user_profile_data,
    intake_status as db_intake_status,
    load_draft,
    load_cv_text as db_load_cv_text,
    load_structured_profile as db_load_structured,
    load_artifacts,
    save_cv_text as db_save_cv_text,
    save_draft as db_save_draft,
    save_extraction,
    save_structured_profile as db_save_structured,
    save_submission,
)
from app.workers.profile.tasks import profile_pipeline_task

router = APIRouter(prefix="/profile/intake", tags=["profile-intake"])


async def _build_status_response(db: AsyncSession, user: User) -> IntakeStatusResponse:
    base = await db_intake_status(db, user.id)
    run = await get_latest_pipeline_run(db, user.id)
    pipeline = None
    summary = None

    if run:
        payload = pipeline_run_to_dict(run)
        pipeline = PipelineStatus(
            id=payload["id"],
            status=payload["status"],
            current_step=payload["current_step"],
            steps=[PipelineStepStatus(**step) for step in payload["steps"]],
            error=payload["error"],
            started_at=payload["started_at"],
            finished_at=payload["finished_at"],
        )

    if base.get("has_structured_profile") or (
        run and run.status == ProfilePipelineRunStatus.completed
    ):
        raw_summary = await build_profile_summary(db, user.id)
        if raw_summary:
            summary = ProfileSummary(**raw_summary)

    return IntakeStatusResponse(
        **base,
        pipeline=pipeline,
        summary=summary,
    )


@router.get("/status", response_model=IntakeStatusResponse)
async def get_intake_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _build_status_response(db, user)


@router.get("/structured", response_model=IntakeStructuredResponse)
async def get_structured_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    structured = await db_load_structured(db, user.id)
    if not structured:
        raise HTTPException(status_code=404, detail="No structured profile yet")

    artifacts = await load_artifacts(db, user.id)
    meta = structured.get("extraction_meta") or {}
    return IntakeStructuredResponse(
        profile=structured,
        profile_truth=artifacts.profile_truth if artifacts else None,
        confidence=meta.get("confidence"),
        fields_needing_review=meta.get("fields_needing_review") or [],
    )


@router.get("/draft", response_model=IntakeDraftResponse)
async def get_draft(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    draft = await load_draft(db, user.id)
    if not draft:
        return IntakeDraftResponse()
    return IntakeDraftResponse(
        step=draft.get("step", 0),
        form=draft.get("form", {}),
        cv_text=draft.get("cv_text") or await db_load_cv_text(db, user.id),
        updated_at=draft.get("updated_at"),
    )


@router.put("/draft", response_model=IntakeDraftResponse)
async def update_draft(
    body: IntakeDraftUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    payload = await db_save_draft(db, user.id, body.form, body.step, body.cv_text)
    return IntakeDraftResponse(
        step=payload["step"],
        form=payload["form"],
        cv_text=payload["cv_text"],
        updated_at=payload["updated_at"],
    )


@router.put("/cv")
async def update_cv(
    body: IntakeCvUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not body.cv_text.strip():
        raise HTTPException(status_code=400, detail="CV text cannot be empty")
    await db_save_cv_text(db, user.id, body.cv_text)
    return {"ok": True, "length": len(body.cv_text)}


@router.post("/cv/upload", response_model=IntakeCvUploadResponse)
async def upload_cv(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    data = await file.read()
    try:
        text = extract_text_from_cv_file(file.filename, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db_save_cv_text(db, user.id, text)
    return IntakeCvUploadResponse(text=text, length=len(text), filename=file.filename)


@router.post("/submit", response_model=IntakeSubmitResponse)
async def submit_intake(
    body: IntakeDraftUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cv_text = body.cv_text if body.cv_text is not None else await db_load_cv_text(db, user.id)
    if not cv_text.strip():
        raise HTTPException(status_code=400, detail="Add CV text before submitting")
    required = ["full_name", "target_degree", "target_intake_term", "funding_requirement"]
    missing = [f for f in required if not body.form.get(f)]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Complete required fields first: {', '.join(missing)}",
        )
    await db_save_draft(db, user.id, body.form, body.step, cv_text)
    sub_id = await save_submission(db, user.id, body.form, cv_text)

    run = await create_profile_pipeline_run(db, user.id, sub_id)
    profile_pipeline_task.delay(user.id, sub_id, run.id)

    return IntakeSubmitResponse(
        submission_id=sub_id,
        saved_to=f"profile_submissions/{sub_id}",
        pipeline_run_id=run.id,
        status="queued",
    )


@router.delete("")
async def delete_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await delete_user_profile_data(db, user.id)
    return {"ok": True}


@router.post("/pipeline/retry", response_model=IntakeSubmitResponse)
async def retry_pipeline(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await get_latest_pipeline_run(db, user.id)
    if not run:
        raise HTTPException(status_code=400, detail="No failed pipeline run to retry")

    ingest_failed = any(
        s.get("name") == "ingest" and s.get("status") == "failed" for s in (run.steps or [])
    )
    pipeline_failed = run.status == ProfilePipelineRunStatus.failed
    if not pipeline_failed and not ingest_failed:
        raise HTTPException(status_code=400, detail="No failed pipeline run to retry")

    ingest_only = ingest_failed and not pipeline_failed
    if ingest_only:
        from app.services.profile_orchestrator import append_step_log, set_step_status

        steps = list(run.steps or init_pipeline_steps())
        steps = set_step_status(steps, "ingest", "pending")
        steps = append_step_log(steps, "ingest", "Retrying discovery and ranking")
        run.steps = steps
    else:
        run.steps = init_pipeline_steps()

    run.status = ProfilePipelineRunStatus.queued
    run.current_step = None
    run.error_message = None
    if not ingest_only:
        run.started_at = None
    run.finished_at = None
    await db.commit()
    await db.refresh(run)

    profile_pipeline_task.delay(user.id, run.submission_id, run.id, ingest_only=ingest_only)

    return IntakeSubmitResponse(
        submission_id=run.submission_id,
        saved_to=f"profile_submissions/{run.submission_id}",
        pipeline_run_id=run.id,
        status="queued",
    )


@router.post("/prompts/extraction", response_model=IntakePromptResponse)
async def generate_extraction_prompt(
    body: IntakeDraftUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cv_text = body.cv_text if body.cv_text is not None else await db_load_cv_text(db, user.id)
    if not cv_text.strip():
        raise HTTPException(status_code=400, detail="Add CV text before generating the extraction prompt")
    required = ["full_name", "target_degree", "target_intake_term", "funding_requirement"]
    missing = [f for f in required if not body.form.get(f)]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Complete required fields first: {', '.join(missing)}",
        )
    await db_save_draft(db, user.id, body.form, body.step, cv_text)
    prompt = intake.build_extraction_prompt(body.form, cv_text)
    return IntakePromptResponse(
        prompt=prompt,
        instructions=(
            "Profile extraction is automated after submit. "
            "This prompt is for manual debugging only."
        ),
        save_path="user_structured_profiles.extraction",
    )


@router.post("/validate", response_model=IntakeValidateResponse)
async def validate_extraction(
    body: IntakeValidateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile, errors = intake.validate_structured_profile(body.data)
    if profile is None:
        return IntakeValidateResponse(valid=False, errors=errors)
    await save_extraction(db, user.id, body.data)
    return IntakeValidateResponse(
        valid=True,
        profile=profile.model_dump(mode="json"),
        fields_needing_review=profile.extraction_meta.fields_needing_review,
        confidence=profile.extraction_meta.confidence.value,
    )


@router.post("/structured")
async def confirm_structured_profile(
    body: IntakeValidateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile, errors = intake.validate_structured_profile(body.data)
    if profile is None:
        raise HTTPException(status_code=422, detail={"errors": errors})
    await db_save_structured(db, user.id, profile)
    return {
        "ok": True,
        "saved_to": "user_structured_profiles",
        "confidence": profile.extraction_meta.confidence.value,
        "fields_needing_review": profile.extraction_meta.fields_needing_review,
    }


@router.post("/prompts/compile", response_model=IntakePromptResponse)
async def generate_compile_prompt(
    body: IntakeValidateRequest | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    structured = None
    if body and body.data:
        profile, errors = intake.validate_structured_profile(body.data)
        if profile is None:
            raise HTTPException(status_code=422, detail={"errors": errors})
        await db_save_structured(db, user.id, profile)
        structured = profile.model_dump(mode="json")
    else:
        structured = await db_load_structured(db, user.id)

    if not structured:
        raise HTTPException(
            status_code=400,
            detail="No structured profile. Validate and save extraction JSON first.",
        )

    prompt = intake.build_compile_prompt(structured)
    return IntakePromptResponse(
        prompt=prompt,
        instructions=(
            "Profile compile runs automatically in the pipeline after submit. "
            "Run scripts/compile_profile.py only for manual debugging."
        ),
        save_path="user_profile_artifacts",
    )

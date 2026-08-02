"""Profile intake API — form draft, CV, prompt generation, validation."""

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.schemas.profile_intake_api import (
    IntakeCvUpdate,
    IntakeCvUploadResponse,
    IntakeDraftResponse,
    IntakeDraftUpdate,
    IntakePromptResponse,
    IntakeStatusResponse,
    IntakeSubmitResponse,
    IntakeValidateRequest,
    IntakeValidateResponse,
)
from app.services import profile_intake as intake
from app.services.cv_extract import extract_text_from_cv_file

router = APIRouter(prefix="/profile/intake", tags=["profile-intake"])


@router.get("/status", response_model=IntakeStatusResponse)
async def get_intake_status():
    return intake.intake_status()


@router.get("/draft", response_model=IntakeDraftResponse)
async def get_draft():
    draft = intake.load_draft()
    if not draft:
        return IntakeDraftResponse()
    return IntakeDraftResponse(
        step=draft.get("step", 0),
        form=draft.get("form", {}),
        cv_text=draft.get("cv_text") or intake.load_cv_text(),
        updated_at=draft.get("updated_at"),
    )


@router.put("/draft", response_model=IntakeDraftResponse)
async def update_draft(body: IntakeDraftUpdate):
    payload = intake.save_draft(body.form, body.step, body.cv_text)
    return IntakeDraftResponse(
        step=payload["step"],
        form=payload["form"],
        cv_text=payload["cv_text"],
        updated_at=payload["updated_at"],
    )


@router.put("/cv")
async def update_cv(body: IntakeCvUpdate):
    if not body.cv_text.strip():
        raise HTTPException(status_code=400, detail="CV text cannot be empty")
    intake.save_cv_text(body.cv_text)
    return {"ok": True, "length": len(body.cv_text)}


@router.post("/cv/upload", response_model=IntakeCvUploadResponse)
async def upload_cv(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    data = await file.read()
    try:
        text = extract_text_from_cv_file(file.filename, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    intake.save_cv_text(text)
    return IntakeCvUploadResponse(text=text, length=len(text), filename=file.filename)


@router.post("/submit", response_model=IntakeSubmitResponse)
async def submit_intake(body: IntakeDraftUpdate):
    cv_text = body.cv_text if body.cv_text is not None else intake.load_cv_text()
    if not cv_text.strip():
        raise HTTPException(status_code=400, detail="Add CV text before submitting")
    required = ["full_name", "target_degree", "target_intake_term", "funding_requirement"]
    missing = [f for f in required if not body.form.get(f)]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Complete required fields first: {', '.join(missing)}",
        )
    intake.save_draft(body.form, body.step, cv_text)
    intake.save_form_answers_markdown(body.form)
    path, sub_id = intake.save_raw_submission(body.form, cv_text)
    rel = path.relative_to(intake.project_root())
    return IntakeSubmitResponse(submission_id=sub_id, saved_to=str(rel))


@router.post("/prompts/extraction", response_model=IntakePromptResponse)
async def generate_extraction_prompt(body: IntakeDraftUpdate):
    cv_text = body.cv_text if body.cv_text is not None else intake.load_cv_text()
    if not cv_text.strip():
        raise HTTPException(status_code=400, detail="Add CV text before generating the extraction prompt")
    required = ["full_name", "target_degree", "target_intake_term", "funding_requirement"]
    missing = [f for f in required if not body.form.get(f)]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Complete required fields first: {', '.join(missing)}",
        )
    intake.save_draft(body.form, body.step, cv_text)
    prompt = intake.build_extraction_prompt(body.form, cv_text)
    return IntakePromptResponse(
        prompt=prompt,
        instructions=(
            "Copy this prompt into ChatGPT or Claude. "
            "Save the JSON-only response to docs/profile/intake/extraction-output.json"
        ),
        save_path="docs/profile/intake/extraction-output.json",
    )


@router.post("/validate", response_model=IntakeValidateResponse)
async def validate_extraction(body: IntakeValidateRequest):
    profile, errors = intake.validate_structured_profile(body.data)
    if profile is None:
        return IntakeValidateResponse(valid=False, errors=errors)
    intake.save_extraction_output(body.data)
    return IntakeValidateResponse(
        valid=True,
        profile=profile.model_dump(mode="json"),
        fields_needing_review=profile.extraction_meta.fields_needing_review,
        confidence=profile.extraction_meta.confidence.value,
    )


@router.post("/structured")
async def confirm_structured_profile(body: IntakeValidateRequest):
    profile, errors = intake.validate_structured_profile(body.data)
    if profile is None:
        raise HTTPException(status_code=422, detail={"errors": errors})
    path = intake.save_structured_profile(profile)
    rel = path.relative_to(intake.project_root())
    return {
        "ok": True,
        "saved_to": str(rel),
        "confidence": profile.extraction_meta.confidence.value,
        "fields_needing_review": profile.extraction_meta.fields_needing_review,
    }


@router.post("/prompts/compile", response_model=IntakePromptResponse)
async def generate_compile_prompt(body: IntakeValidateRequest | None = None):
    structured = None
    if body and body.data:
        profile, errors = intake.validate_structured_profile(body.data)
        if profile is None:
            raise HTTPException(status_code=422, detail={"errors": errors})
        intake.save_structured_profile(profile)
        structured = profile.model_dump(mode="json")
    else:
        structured = intake.load_structured_profile()

    if not structured:
        raise HTTPException(
            status_code=400,
            detail="No structured profile. Validate and save extraction JSON first.",
        )

    prompt = intake.build_compile_prompt(structured)
    return IntakePromptResponse(
        prompt=prompt,
        instructions=(
            "Deterministic compile — run scripts/compile_profile.py instead. "
            "Produces filter_config.json, eligibility_rules.json, ranking_config.json, "
            "ingestion_sources.json, and profile-truth.md"
        ),
        save_path="docs/profile/compiled/",
    )

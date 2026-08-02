"""Profile intake API — form draft, CV, prompt generation, validation."""

import json

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.schemas.profile_intake_api import (
    IntakeCompileResponse,
    IntakeCvUpdate,
    IntakeDraftResponse,
    IntakeDraftUpdate,
    IntakePromptResponse,
    IntakeStatusResponse,
    IntakeSubmitRequest,
    IntakeSubmitResponse,
    IntakeValidateRequest,
    IntakeValidateResponse,
)
from app.services import profile_intake as intake
from app.services.profile_pipeline import (
    build_cv_extraction_prompt,
    check_profile_ready,
    compile_profile,
    load_extraction_json,
    load_prefill,
    merge_prefill_and_extraction,
    prefill_from_submission,
    save_prefill,
)

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


@router.post("/cv/upload")
async def upload_cv_file(file: UploadFile = File(...)):
    content = await file.read()
    filename = (file.filename or "").lower()
    if filename.endswith(".pdf"):
        try:
            from io import BytesIO

            from pypdf import PdfReader

            reader = PdfReader(BytesIO(content))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not read PDF: {exc}") from exc
    else:
        text = content.decode("utf-8", errors="replace")

    if not text.strip():
        raise HTTPException(status_code=400, detail="No text could be extracted from the file")

    intake.save_cv_text(text)
    return {"ok": True, "text": text, "length": len(text)}


@router.post("/submit", response_model=IntakeSubmitResponse)
async def submit_intake(body: IntakeSubmitRequest):
    if not body.cv_text.strip():
        raise HTTPException(status_code=400, detail="CV text is required")
    required = ["full_name", "nationality_code", "target_degree", "linkedin_url"]
    missing = [f for f in required if not body.form.get(f)]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required fields: {', '.join(missing)}",
        )
    path, submission_id = intake.save_raw_submission(body.form, body.cv_text)
    intake.save_draft(body.form, 5, body.cv_text)
    rel = path.relative_to(intake.project_root())
    raw = intake.load_raw_submission()
    return IntakeSubmitResponse(
        ok=True,
        saved_to=str(rel),
        submitted_at=raw["submitted_at"] if raw else "",
        submission_id=submission_id,
    )


@router.get("/submission")
async def get_raw_submission():
    raw = intake.load_raw_submission()
    if not raw:
        raise HTTPException(status_code=404, detail="No submission found")
    return raw


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


@router.post("/prefill")
async def create_prefill():
    try:
        data = prefill_from_submission()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    path = save_prefill(data)
    rel = path.relative_to(intake.project_root())
    aggregators = data.get("sources", {}).get("aggregators", [])
    return {
        "ok": True,
        "saved_to": str(rel),
        "aggregator_count": len(aggregators),
        "aggregators": [a["id"] for a in aggregators],
    }


@router.get("/prefill")
async def get_prefill():
    data = load_prefill()
    if not data:
        raise HTTPException(status_code=404, detail="No prefill found. POST /prefill first.")
    return data


@router.post("/prompts/cv-extraction", response_model=IntakePromptResponse)
async def generate_cv_extraction_prompt():
    prefill = load_prefill()
    if not prefill:
        try:
            prefill = prefill_from_submission()
            save_prefill(prefill)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    cv_text = intake.load_cv_text()
    if not cv_text.strip():
        raw = intake.load_raw_submission()
        cv_text = (raw or {}).get("cv_text", "")
    if not cv_text.strip():
        raise HTTPException(status_code=400, detail="No CV text found")

    prompt = build_cv_extraction_prompt(prefill, cv_text)
    return IntakePromptResponse(
        prompt=prompt,
        instructions=(
            "Copy into ChatGPT or Claude. Save JSON to docs/profile/intake/extraction-output.json "
            "then POST /merge or run merge_profile.py"
        ),
        save_path="docs/profile/intake/extraction-output.json",
    )


@router.post("/merge")
async def merge_extraction(body: IntakeValidateRequest | None = None):
    prefill = load_prefill()
    if not prefill:
        raise HTTPException(status_code=404, detail="No prefill. POST /prefill first.")

    if body and body.data:
        extraction = body.data
    else:
        path = intake.intake_dir() / "extraction-output.json"
        if not path.exists():
            raise HTTPException(status_code=404, detail="No extraction-output.json")
        try:
            extraction = load_extraction_json(path)
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    merged = merge_prefill_and_extraction(prefill, extraction)
    profile, errors = intake.validate_structured_profile(merged)
    if profile is None:
        raise HTTPException(status_code=422, detail={"errors": errors, "merged": merged})

    path = intake.save_structured_profile(profile)
    rel = path.relative_to(intake.project_root())
    return {
        "ok": True,
        "saved_to": str(rel),
        "fields_needing_review": profile.extraction_meta.fields_needing_review,
        "confidence": profile.extraction_meta.confidence.value,
    }


@router.post("/compile", response_model=IntakeCompileResponse)
async def compile_structured_profile(body: IntakeValidateRequest | None = None):
    structured = None
    if body and body.data:
        profile, errors = intake.validate_structured_profile(body.data)
        if profile is None:
            raise HTTPException(status_code=422, detail={"errors": errors})
        intake.save_structured_profile(profile)
        structured = profile
    else:
        data = intake.load_structured_profile()
        if not data:
            raise HTTPException(status_code=404, detail="No structured-profile.json")
        profile, errors = intake.validate_structured_profile(data)
        if profile is None:
            raise HTTPException(status_code=422, detail={"errors": errors})
        structured = profile

    try:
        paths = compile_profile(structured)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    ing_count = 0
    ing_path = paths.get("ingestion_sources")
    if ing_path and ing_path.exists():
        ing_count = len(json.loads(ing_path.read_text(encoding="utf-8")).get("sources", []))

    return IntakeCompileResponse(
        ok=True,
        artifacts={k: str(v.relative_to(intake.project_root())) for k, v in paths.items()},
        ingestion_source_count=ing_count,
    )


@router.get("/readiness")
async def profile_readiness():
    ok, messages = check_profile_ready()
    return {"ready": ok, "messages": messages}

"""API request/response models for profile intake endpoints."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class IntakeDraftResponse(BaseModel):
    step: int = 0
    form: dict[str, Any] = Field(default_factory=dict)
    cv_text: str = ""
    updated_at: Optional[str] = None


class IntakeDraftUpdate(BaseModel):
    step: int = Field(ge=0, le=8)
    form: dict[str, Any] = Field(default_factory=dict)
    cv_text: Optional[str] = None


class IntakeSubmitResponse(BaseModel):
    ok: bool = True
    submission_id: str
    saved_to: str
    pipeline_run_id: Optional[str] = None
    status: str = "queued"


class PipelineStepStatus(BaseModel):
    name: str
    status: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None
    logs: list[str] = Field(default_factory=list)


class PipelineStatus(BaseModel):
    id: str
    status: str
    current_step: Optional[str] = None
    steps: list[PipelineStepStatus] = Field(default_factory=list)
    error: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class ProfileSummary(BaseModel):
    full_name: Optional[str] = None
    discovery_mode: Optional[str] = None
    aggregator_names: list[str] = Field(default_factory=list)
    profile_truth_excerpt: Optional[str] = None


class IntakeCvUpdate(BaseModel):
    cv_text: str


class IntakeCvUploadResponse(BaseModel):
    ok: bool = True
    text: str
    length: int
    filename: str


class IntakePromptResponse(BaseModel):
    prompt: str
    instructions: str
    save_path: str


class IntakeValidateRequest(BaseModel):
    data: dict[str, Any]


class IntakeValidateResponse(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    profile: Optional[dict[str, Any]] = None
    fields_needing_review: list[str] = Field(default_factory=list)
    confidence: Optional[str] = None


class IntakeStatusResponse(BaseModel):
    has_draft: bool
    current_step: int
    has_cv: bool
    has_form_answers: bool
    has_extraction_output: bool
    has_structured_profile: bool
    has_compiled_artifacts: bool = False
    has_profile_truth: bool = False
    updated_at: Optional[str] = None
    pipeline: Optional[PipelineStatus] = None
    summary: Optional[ProfileSummary] = None


class IntakeStructuredResponse(BaseModel):
    profile: dict[str, Any]
    profile_truth: Optional[str] = None
    confidence: Optional[str] = None
    fields_needing_review: list[str] = Field(default_factory=list)

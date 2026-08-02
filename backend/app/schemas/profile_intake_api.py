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


class IntakeCvUpdate(BaseModel):
    cv_text: str


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
    updated_at: Optional[str] = None

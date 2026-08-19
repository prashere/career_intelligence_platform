from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class HealthResponse(BaseModel):
    status: str
    version: str = "0.1.0"


class OpportunitySourceCreate(BaseModel):
    name: str
    url: str
    source_type: str
    fetch_interval_minutes: int = 360
    parser_config: dict = Field(default_factory=dict)


class OpportunitySourceResponse(BaseModel):
    id: str
    name: str
    url: str
    source_type: str
    fetch_interval_minutes: int
    is_active: bool
    last_fetched_at: Optional[datetime] = None
    last_error: Optional[str] = None
    outcome_stats: Optional[dict] = None
    authority: Optional[float] = None

    model_config = {"from_attributes": True}


class OpportunityResponse(BaseModel):
    id: str
    title: str
    summary: Optional[str] = None
    institution: Optional[str] = None
    program: Optional[str] = None
    opportunity_type: str
    url: str
    deadline: Optional[datetime] = None
    opens_at: Optional[datetime] = None
    tags: list = Field(default_factory=list)
    requirements: list = Field(default_factory=list)
    status: Optional[str] = None
    dismiss_reason: Optional[str] = None
    fit_score: Optional[float] = None
    fit_percent: Optional[int] = None
    fit_level: Optional[str] = None
    fit_explanation: Optional[str] = None
    score_breakdown: Optional[dict] = None
    rank_position: Optional[int] = None
    verification_status: Optional[str] = None
    verified_at: Optional[datetime] = None
    days_until_deadline: Optional[int] = None
    urgency_label: Optional[str] = None

    model_config = {"from_attributes": True}


class OpportunityListResponse(BaseModel):
    items: list[OpportunityResponse] = Field(default_factory=list)
    total: int = 0
    next_cursor: Optional[str] = None


class FeedSummary(BaseModel):
    new_since: int = 0
    deadlines_this_week: int = 0
    prep_milestones_due: int = 0
    last_checked: Optional[datetime] = None


class FeedResponse(BaseModel):
    summary: FeedSummary
    scholarships: list[OpportunityResponse] = Field(default_factory=list)
    fellowships: list[OpportunityResponse] = Field(default_factory=list)
    other: list[OpportunityResponse] = Field(default_factory=list)


DismissReasonCode = Literal[
    "wrong_field",
    "wrong_level",
    "wrong_region",
    "not_funded",
    "looks_fake",
    "other",
]


class UserOpportunityUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    dismiss_reason: Optional[DismissReasonCode] = None

    @field_validator("dismiss_reason")
    @classmethod
    def dismiss_reason_only_when_dismissed(cls, v: Optional[str], info) -> Optional[str]:
        status = info.data.get("status")
        if v is not None and status is not None and status != "dismissed":
            raise ValueError("dismiss_reason is only valid when status is dismissed")
        if status == "dismissed" and not v:
            raise ValueError("dismiss_reason is required when status is dismissed")
        return v


class RequirementCreate(BaseModel):
    title: str
    due_date: Optional[datetime] = None


class RequirementUpdate(BaseModel):
    title: Optional[str] = None
    is_completed: Optional[bool] = None
    due_date: Optional[datetime] = None
    notes: Optional[str] = None


class RequirementResponse(BaseModel):
    id: str
    title: str
    is_completed: bool
    due_date: Optional[datetime] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class UserProfileUpdate(BaseModel):
    name: Optional[str] = None
    long_term_goals: Optional[str] = None
    research_interests: Optional[list[str]] = None
    skills: Optional[list[str]] = None
    target_regions: Optional[list[str]] = None
    target_universities: Optional[list[str]] = None
    degree_level: Optional[str] = None
    constraints: Optional[dict] = None
    projects: Optional[list[str]] = None
    connections: Optional[list[str]] = None


class UserProfileResponse(BaseModel):
    id: str
    name: str
    long_term_goals: str
    research_interests: list
    skills: list
    target_regions: list
    target_universities: list
    degree_level: Optional[str] = None
    constraints: dict
    projects: list
    connections: list

    model_config = {"from_attributes": True}


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    citations: list[str] = Field(default_factory=list)
    pending_actions: list[dict] = Field(default_factory=list)


class ApplicationUpdate(BaseModel):
    status: Optional[str] = None
    document_links: Optional[list[str]] = None
    submitted_at: Optional[datetime] = None
    outcome: Optional[str] = None
    critical_analysis: Optional[str] = None
    timeline_events: Optional[list[dict]] = None


class ApplicationResponse(BaseModel):
    id: str
    status: str
    document_links: list
    submitted_at: Optional[datetime] = None
    outcome: Optional[str] = None
    critical_analysis: Optional[str] = None
    timeline_events: list

    model_config = {"from_attributes": True}


class LearningItemCreate(BaseModel):
    title: str
    item_type: str = "course"
    url: Optional[str] = None
    progress_percent: int = 0
    status: str = "not_started"
    outcome_notes: Optional[str] = None
    reminder_at: Optional[datetime] = None


class LearningItemUpdate(BaseModel):
    title: Optional[str] = None
    progress_percent: Optional[int] = None
    status: Optional[str] = None
    outcome_notes: Optional[str] = None
    reminder_at: Optional[datetime] = None


class LearningItemResponse(BaseModel):
    id: str
    title: str
    item_type: str
    url: Optional[str] = None
    progress_percent: int
    status: str
    outcome_notes: Optional[str] = None
    reminder_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class NotificationResponse(BaseModel):
    id: str
    title: str
    body: str
    notification_type: str
    is_read: bool
    related_opportunity_id: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DashboardResponse(BaseModel):
    updated_cards: list[OpportunityResponse] = Field(default_factory=list)
    in_progress: list[OpportunityResponse] = Field(default_factory=list)
    upskilling: list[LearningItemResponse] = Field(default_factory=list)
    notifications: list[NotificationResponse] = Field(default_factory=list)


class PersonCreate(BaseModel):
    name: str
    role: str = "researcher"
    affiliation: Optional[str] = None
    research_areas: list[str] = Field(default_factory=list)
    url: Optional[str] = None
    relationship_notes: Optional[str] = None


class PersonResponse(BaseModel):
    id: str
    name: str
    role: str
    affiliation: Optional[str] = None
    research_areas: list
    url: Optional[str] = None
    relationship_notes: Optional[str] = None

    model_config = {"from_attributes": True}


class CommunityCreate(BaseModel):
    name: str
    community_type: str = "forum"
    url: Optional[str] = None
    description: Optional[str] = None
    relevance_notes: Optional[str] = None


class CommunityResponse(BaseModel):
    id: str
    name: str
    community_type: str
    url: Optional[str] = None
    description: Optional[str] = None
    relevance_notes: Optional[str] = None

    model_config = {"from_attributes": True}


class ExperienceCreate(BaseModel):
    title: str
    experience_type: str = "project"
    description: Optional[str] = None
    url: Optional[str] = None
    status: str = "planned"


class ExperienceResponse(BaseModel):
    id: str
    title: str
    experience_type: str
    description: Optional[str] = None
    url: Optional[str] = None
    status: str

    model_config = {"from_attributes": True}


class WeeklyFocusResponse(BaseModel):
    deadlines: list[dict] = Field(default_factory=list)
    prep_tasks: list[dict] = Field(default_factory=list)
    learning_tasks: list[dict] = Field(default_factory=list)
    focus_summary: str = ""

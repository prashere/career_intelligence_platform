"""Admin scheduler API schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class SchedulerJobResponse(BaseModel):
    id: str
    key: str
    name: str
    description: str
    task_path: str
    schedule_kind: str
    cron_minute: str | None
    cron_hour: str | None
    cron_day_of_week: str | None
    interval_seconds: int | None
    is_enabled: bool
    category: str
    last_run_at: datetime | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class SchedulerJobUpdate(BaseModel):
    is_enabled: bool | None = None
    cron_minute: str | None = None
    cron_hour: str | None = None
    cron_day_of_week: str | None = None
    interval_seconds: int | None = Field(default=None, ge=60, le=86400)
    schedule_kind: str | None = None


class SourceHealthResponse(BaseModel):
    id: str
    name: str
    registry_id: str | None
    fetch_mode: str
    is_active: bool
    last_fetched_at: datetime | None
    next_fetch_at: datetime | None
    consecutive_failures: int
    last_error: str | None
    opportunity_count: int


class IngestionRunResponse(BaseModel):
    id: str
    source_id: str | None
    status: str
    discovered: int
    prefilter_drop: int
    fetched: int
    created: int
    updated: int
    rejected: int
    errors: int
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None
    meta: dict

    model_config = {"from_attributes": True}


class RejectedItemResponse(BaseModel):
    id: str
    run_id: str
    source_id: str | None
    stage: str
    reason: str
    url: str | None
    title: str | None
    snippet: str | None
    meta: dict = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


class IngestionOverviewResponse(BaseModel):
    total_opportunities: int
    total_sources: int
    active_sources: int
    sources_with_errors: int
    last_run_at: datetime | None


class TraceEventResponse(BaseModel):
    id: str
    run_id: str
    source_id: str | None
    seq: int
    stage: str
    level: str
    event: str
    message: str
    payload: dict
    duration_ms: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class IngestionRunDetailResponse(BaseModel):
    run: IngestionRunResponse
    source_name: str | None
    rejected_items: list[RejectedItemResponse]
    trace_events: list[TraceEventResponse]


class RegistryAggregatorResponse(BaseModel):
    id: str
    name: str
    url: str | None
    type: str | None
    fetch_mode: str | None
    default_active: bool
    discover_kind: str | None


class PlaygroundRequest(BaseModel):
    source_id: str | None = None
    registry_id: str | None = None
    mode: str = Field(default="discover", pattern="^(discover|dry_run|persist)$")
    max_items: int = Field(default=15, ge=1, le=100)
    include_browser: bool = False
    resolve_investigate: bool = False


class RelevanceSignal(BaseModel):
    name: str
    matched: bool
    strength: float
    evidence: list[str] = Field(default_factory=list)
    found_in: str | None = None
    note: str | None = None


class PlaygroundPreviewItem(BaseModel):
    url: str
    title: str
    summary: str
    verdict: str
    score: float
    corpus_score: float
    fit_score: float
    sufficiency: float
    reason: str
    stage: str
    type_label: str | None = None
    matched: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    signals: dict[str, RelevanceSignal] = Field(default_factory=dict)
    resolved: bool = False
    resolve_error: str | None = None
    # Legacy fields kept so older stored runs still deserialize.
    prefilter_pass: bool | None = None
    prefilter_reason: str | None = None


class PlaygroundResponse(BaseModel):
    ok: bool
    run_id: str | None = None
    mode: str | None = None
    source_name: str | None = None
    registry_id: str | None = None
    discovered: int | None = None
    prefilter_drop: int | None = None
    admit: int | None = None
    investigate: int | None = None
    reject: int | None = None
    resolved: int | None = None
    winning_strategy: str | None = None
    strategy_probes: list[dict] | None = None
    preview_items: list[PlaygroundPreviewItem] | None = None
    created: int | None = None
    updated: int | None = None
    rejected: int | None = None
    errors: int | None = None
    error: str | None = None
    dry_run: bool | None = None

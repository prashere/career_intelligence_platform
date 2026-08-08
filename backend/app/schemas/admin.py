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

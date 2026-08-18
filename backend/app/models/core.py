"""Core models — auth, profile, and scheduler configuration."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, enum.Enum):
    user = "user"
    administrator = "administrator"


class ScheduleKind(str, enum.Enum):
    cron = "cron"
    interval = "interval"


class SchedulerCategory(str, enum.Enum):
    ingest = "ingest"
    notify = "notify"
    rank = "rank"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.user, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    profile: Mapped[Optional["UserProfile"]] = relationship(back_populates="user", uselist=False)
    intake_draft: Mapped[Optional["ProfileIntakeDraft"]] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    structured_profile: Mapped[Optional["UserStructuredProfile"]] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    profile_artifacts: Mapped[Optional["UserProfileArtifacts"]] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), default="")
    long_term_goals: Mapped[str] = mapped_column(Text, default="")
    research_interests: Mapped[list] = mapped_column(JSONB, default=list)
    skills: Mapped[list] = mapped_column(JSONB, default=list)
    target_regions: Mapped[list] = mapped_column(JSONB, default=list)
    target_universities: Mapped[list] = mapped_column(JSONB, default=list)
    degree_level: Mapped[Optional[str]] = mapped_column(String(100))
    constraints: Mapped[dict] = mapped_column(JSONB, default=dict)
    projects: Mapped[list] = mapped_column(JSONB, default=list)
    connections: Mapped[list] = mapped_column(JSONB, default=list)
    embedding: Mapped[Optional[list]] = mapped_column(Vector(1536))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="profile")


class ProfileIntakeDraft(Base):
    __tablename__ = "profile_intake_drafts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    step: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    form: Mapped[dict] = mapped_column(JSONB, default=dict)
    cv_text: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="intake_draft")


class ProfileSubmission(Base):
    __tablename__ = "profile_submissions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    submission_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    form: Mapped[dict] = mapped_column(JSONB, default=dict)
    cv_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship()


class UserStructuredProfile(Base):
    __tablename__ = "user_structured_profiles"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    prefill: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    extraction: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    schema_version: Mapped[str] = mapped_column(String(16), default="1.0", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="structured_profile")


class UserProfileArtifacts(Base):
    __tablename__ = "user_profile_artifacts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    filter_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    eligibility_rules: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ranking_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ingestion_sources: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    profile_truth: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    compiled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="profile_artifacts")


class ProfilePipelineRunStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class ProfilePipelineRun(Base):
    __tablename__ = "profile_pipeline_runs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    submission_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[ProfilePipelineRunStatus] = mapped_column(
        Enum(ProfilePipelineRunStatus),
        default=ProfilePipelineRunStatus.queued,
        nullable=False,
    )
    current_step: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    steps: Mapped[list] = mapped_column(JSONB, default=list)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship()


class SchedulerJob(Base):
    __tablename__ = "scheduler_jobs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    task_path: Mapped[str] = mapped_column(String(255), nullable=False)
    schedule_kind: Mapped[ScheduleKind] = mapped_column(Enum(ScheduleKind), nullable=False)
    cron_minute: Mapped[Optional[str]] = mapped_column(String(64))
    cron_hour: Mapped[Optional[str]] = mapped_column(String(64))
    cron_day_of_week: Mapped[Optional[str]] = mapped_column(String(64))
    interval_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    category: Mapped[SchedulerCategory] = mapped_column(Enum(SchedulerCategory), nullable=False)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

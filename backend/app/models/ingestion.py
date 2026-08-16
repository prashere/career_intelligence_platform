"""Ingestion pipeline tracking models."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class IngestionRunStatus(str, enum.Enum):
    running = "running"
    completed = "completed"
    failed = "failed"
    partial = "partial"


class RejectedStage(str, enum.Enum):
    discover = "discover"
    prefilter = "prefilter"
    extract = "extract"
    dedupe = "dedupe"
    relevance = "relevance"


class TraceLevel(str, enum.Enum):
    debug = "debug"
    info = "info"
    warn = "warn"
    error = "error"


class FetchKind(str, enum.Enum):
    index = "index"
    detail = "detail"


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    source_id: Mapped[Optional[str]] = mapped_column(ForeignKey("opportunity_sources.id"), index=True)
    status: Mapped[IngestionRunStatus] = mapped_column(
        Enum(IngestionRunStatus), default=IngestionRunStatus.running, nullable=False
    )
    discovered: Mapped[int] = mapped_column(Integer, default=0)
    prefilter_drop: Mapped[int] = mapped_column(Integer, default=0)
    fetched: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    rejected: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)

    source: Mapped[Optional["OpportunitySource"]] = relationship(back_populates="ingestion_runs")
    rejected_items: Mapped[list["RejectedItem"]] = relationship(back_populates="run")
    trace_events: Mapped[list["IngestionTraceEvent"]] = relationship(back_populates="run")


class IngestionTraceEvent(Base):
    """Structured trace event for ingestion runs (LangSmith-style timeline)."""

    __tablename__ = "ingestion_trace_events"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey("ingestion_runs.id"), index=True)
    source_id: Mapped[Optional[str]] = mapped_column(ForeignKey("opportunity_sources.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    level: Mapped[TraceLevel] = mapped_column(Enum(TraceLevel), default=TraceLevel.info, nullable=False)
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped["IngestionRun"] = relationship(back_populates="trace_events")


class RejectedItem(Base):
    __tablename__ = "rejected_items"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey("ingestion_runs.id"), index=True)
    source_id: Mapped[Optional[str]] = mapped_column(ForeignKey("opportunity_sources.id"), index=True)
    stage: Mapped[RejectedStage] = mapped_column(Enum(RejectedStage), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(Text)
    title: Mapped[Optional[str]] = mapped_column(String(500))
    snippet: Mapped[Optional[str]] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped["IngestionRun"] = relationship(back_populates="rejected_items")


class PlatformSettings(Base):
    """Singleton-style platform config (interest envelope, etc.)."""

    __tablename__ = "platform_settings"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

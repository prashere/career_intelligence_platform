"""Sprint 0 domain models — migrated incrementally as features ship."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class OpportunityType(str, enum.Enum):
    scholarship = "scholarship"
    fellowship = "fellowship"
    internship = "internship"
    graduate_program = "graduate_program"
    phd = "phd"
    grant = "grant"
    conference = "conference"
    workshop = "workshop"
    competition = "competition"
    other = "other"


class UserOpportunityStatus(str, enum.Enum):
    new = "new"
    saved = "saved"
    in_progress = "in_progress"
    archived = "archived"


class SourceType(str, enum.Enum):
    rss = "rss"
    html = "html"
    json = "json"


class FitLevel(str, enum.Enum):
    strong = "strong"
    moderate = "moderate"
    weak = "weak"


class OpportunitySource(Base):
    __tablename__ = "opportunity_sources"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType), nullable=False)
    fetch_interval_minutes: Mapped[int] = mapped_column(Integer, default=360)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    parser_config: Mapped[dict] = mapped_column(JSONB, default=dict)
    registry_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    adapter_id: Mapped[Optional[str]] = mapped_column(String(128))
    fetch_mode: Mapped[str] = mapped_column(String(32), default="http")
    summary_completeness: Mapped[str] = mapped_column(String(32), default="snippet_only")
    authority: Mapped[float] = mapped_column(Float, default=0.5)
    politeness_delay_ms: Mapped[int] = mapped_column(Integer, default=2500)
    next_fetch_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    etag: Mapped[Optional[str]] = mapped_column(String(255))
    last_modified: Mapped[Optional[str]] = mapped_column(String(255))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    raw_documents: Mapped[list["RawDocument"]] = relationship(back_populates="source")
    ingestion_runs: Mapped[list["IngestionRun"]] = relationship(back_populates="source")


class RawDocument(Base):
    __tablename__ = "raw_documents"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    source_id: Mapped[str] = mapped_column(ForeignKey("opportunity_sources.id"), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[Optional[str]] = mapped_column(String(500))
    summary: Mapped[Optional[str]] = mapped_column(Text)
    fetch_kind: Mapped[str] = mapped_column(String(16), default="index")
    parent_id: Mapped[Optional[str]] = mapped_column(ForeignKey("raw_documents.id"))
    http_status: Mapped[Optional[int]] = mapped_column(Integer)
    content_type: Mapped[Optional[str]] = mapped_column(String(128))
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed: Mapped[bool] = mapped_column(Boolean, default=False)

    source: Mapped["OpportunitySource"] = relationship(back_populates="raw_documents")


class Opportunity(Base):
    __tablename__ = "opportunities"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    institution: Mapped[Optional[str]] = mapped_column(String(255))
    program: Mapped[Optional[str]] = mapped_column(String(255))
    opportunity_type: Mapped[OpportunityType] = mapped_column(Enum(OpportunityType), default=OpportunityType.other)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[Optional[str]] = mapped_column(Text)
    url_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    first_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    funding_type: Mapped[Optional[str]] = mapped_column(String(64))
    degree_levels: Mapped[list] = mapped_column(JSONB, default=list)
    countries: Mapped[list] = mapped_column(JSONB, default=list)
    extraction_confidence: Mapped[Optional[str]] = mapped_column(String(16))
    field_provenance: Mapped[dict] = mapped_column(JSONB, default=dict)
    field_changes: Mapped[list] = mapped_column(JSONB, default=list)
    duplicate_of: Mapped[Optional[str]] = mapped_column(ForeignKey("opportunities.id"))
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    opens_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    requirements: Mapped[list] = mapped_column(JSONB, default=list)
    embedding: Mapped[Optional[list]] = mapped_column(Vector(1536))
    source_id: Mapped[Optional[str]] = mapped_column(ForeignKey("opportunity_sources.id"))
    raw_document_id: Mapped[Optional[str]] = mapped_column(ForeignKey("raw_documents.id"))
    search_vector: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user_opportunities: Mapped[list["UserOpportunity"]] = relationship(back_populates="opportunity")
    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="opportunity")


class UserOpportunity(Base):
    __tablename__ = "user_opportunities"
    __table_args__ = (UniqueConstraint("user_id", "opportunity_id", name="uq_user_opportunity"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id"), nullable=False)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), nullable=False)
    status: Mapped[UserOpportunityStatus] = mapped_column(
        Enum(UserOpportunityStatus), default=UserOpportunityStatus.new
    )
    fit_score: Mapped[Optional[float]] = mapped_column(Float)
    fit_level: Mapped[Optional[FitLevel]] = mapped_column(Enum(FitLevel))
    fit_explanation: Mapped[Optional[str]] = mapped_column(Text)
    rank_position: Mapped[Optional[int]] = mapped_column(Integer)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    opportunity: Mapped["Opportunity"] = relationship(back_populates="user_opportunities")
    application: Mapped[Optional["Application"]] = relationship(back_populates="user_opportunity", uselist=False)


class Requirement(Base):
    __tablename__ = "requirements"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    user_opportunity_id: Mapped[str] = mapped_column(ForeignKey("user_opportunities.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    user_opportunity_id: Mapped[str] = mapped_column(ForeignKey("user_opportunities.id"), unique=True)
    status: Mapped[str] = mapped_column(String(50), default="draft")
    document_links: Mapped[list] = mapped_column(JSONB, default=list)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[Optional[str]] = mapped_column(String(100))
    critical_analysis: Mapped[Optional[str]] = mapped_column(Text)
    timeline_events: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user_opportunity: Mapped["UserOpportunity"] = relationship(back_populates="application")


class LearningItem(Base):
    __tablename__ = "learning_items"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    item_type: Mapped[str] = mapped_column(String(50), default="course")
    url: Mapped[Optional[str]] = mapped_column(Text)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="not_started")
    outcome_notes: Mapped[Optional[str]] = mapped_column(Text)
    reminder_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    embedding: Mapped[Optional[list]] = mapped_column(Vector(1536))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    opportunity: Mapped["Opportunity"] = relationship(back_populates="chunks")


class AgentThread(Base):
    __tablename__ = "agent_threads"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id"), nullable=False)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), nullable=False)
    messages: Mapped[list] = mapped_column(JSONB, default=list)
    pending_actions: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    notification_type: Mapped[str] = mapped_column(String(50), default="info")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    related_opportunity_id: Mapped[Optional[str]] = mapped_column(ForeignKey("opportunities.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Person(Base):
    __tablename__ = "people"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(100), default="researcher")
    affiliation: Mapped[Optional[str]] = mapped_column(String(255))
    research_areas: Mapped[list] = mapped_column(JSONB, default=list)
    url: Mapped[Optional[str]] = mapped_column(Text)
    relationship_notes: Mapped[Optional[str]] = mapped_column(Text)
    embedding: Mapped[Optional[list]] = mapped_column(Vector(1536))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Community(Base):
    __tablename__ = "communities"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    community_type: Mapped[str] = mapped_column(String(100), default="forum")
    url: Mapped[Optional[str]] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    relevance_notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Experience(Base):
    __tablename__ = "experiences"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    experience_type: Mapped[str] = mapped_column(String(100), default="project")
    description: Mapped[Optional[str]] = mapped_column(Text)
    url: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="planned")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

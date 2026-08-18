"""Verification / trust layer models."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, Float, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class VerificationStatus(str, enum.Enum):
    unverified = "unverified"
    aggregator_only = "aggregator_only"
    primary_confirmed = "primary_confirmed"
    stale = "stale"


class OrgDomainCache(Base):
    """Resolved canonical domain for an institution name (search amortization)."""

    __tablename__ = "org_domain_cache"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    org_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    org_display_name: Mapped[Optional[str]] = mapped_column(String(255))
    canonical_domain: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_url: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DomainLegitimacyCache(Base):
    """Slow-changing domain trust signals (RDAP age, allowlist, scam phrase hits)."""

    __tablename__ = "domain_legitimacy_cache"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    registered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    trust_score: Mapped[float] = mapped_column(Float, default=0.5)
    flags: Mapped[list] = mapped_column(JSONB, default=list)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)

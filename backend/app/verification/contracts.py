"""Verification layer contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

PrescreenAction = Literal["stop", "continue", "light_tier2"]


@dataclass
class AggregatorClaims:
    title: str
    url: str
    institution: str | None = None
    program: str | None = None
    deadline: datetime | None = None
    funding_type: str | None = None
    summary: str | None = None
    eligibility_text: str | None = None


@dataclass
class PrimaryFields:
    deadline: datetime | None = None
    funding_summary: str | None = None
    eligibility_summary: str | None = None
    institution: str | None = None
    confidence_per_field: dict[str, str] = field(default_factory=dict)
    source_url: str | None = None
    raw_extraction: dict[str, Any] = field(default_factory=dict)


@dataclass
class FieldComparison:
    field: str
    aggregator_value: Any
    primary_value: Any
    match: bool
    similarity: float
    note: str | None = None


@dataclass
class ComparisonResult:
    all_match: bool
    partial_match: bool
    fields: list[FieldComparison] = field(default_factory=list)
    discrepancies: list[str] = field(default_factory=list)


@dataclass
class PrescreenResult:
    trust_score: float
    action: PrescreenAction
    flags: list[str] = field(default_factory=list)
    listing_domain: str | None = None
    domain_trust: float | None = None


@dataclass
class VerificationResult:
    status: str
    trust_score: float
    prescreen: PrescreenResult | None = None
    comparison: ComparisonResult | None = None
    primary_url: str | None = None
    search_queries: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

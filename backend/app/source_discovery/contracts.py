"""Pydantic contracts for source discovery agent."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SearchQueryPlan(BaseModel):
    query: str
    category: Literal["aggregator", "institutional", "government_ngo", "professional_association"]
    rationale: str = ""


class QueryPlanResponse(BaseModel):
    queries: list[SearchQueryPlan] = Field(default_factory=list)
    round_focus: str = ""


class StructureEvidence(BaseModel):
    has_rss_feed: bool = False
    rss_urls: list[str] = Field(default_factory=list)
    listing_link_count: int = 0
    has_pagination: bool = False
    has_category_nav: bool = False
    sample_listing_urls: list[str] = Field(default_factory=list)
    suggested_link_selector: str | None = None


class CandidateEvaluation(BaseModel):
    evaluation_verdict: Literal["recurring_source", "one_off_page", "unclear"]
    relevance_notes: str
    legitimacy_notes: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    structure_type: Literal["rss", "html_listing", "unclear"] = "unclear"
    guessed_parser_config: dict[str, Any] = Field(default_factory=dict)
    recurring_evidence_summary: str = ""


class DomainCandidate(BaseModel):
    domain: str
    discovered_url: str
    title: str = ""
    snippet: str = ""
    search_query: str = ""
    query_category: str = ""
    pre_rank_score: float = 0.0


class SourceApprovalPayload(BaseModel):
    registry_id: str
    name: str
    url: str
    source_type: Literal["rss", "html", "json"] = "html"
    fetch_mode: str = "http"
    fetch_interval_minutes: int = 360
    adapter_id: str | None = None
    summary_completeness: str = "snippet_only"
    authority: float = 0.5
    politeness_delay_ms: int = 2500
    regions: list[str] = Field(default_factory=lambda: ["global"])
    tags: list[str] = Field(default_factory=list)
    degree_levels: list[str] = Field(default_factory=lambda: ["Mixed"])
    parser_config: dict[str, Any] = Field(default_factory=dict)

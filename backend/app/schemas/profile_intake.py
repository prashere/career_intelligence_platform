"""Pydantic models for profile intake — matches docs/profile/intake/extraction-schema.json."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class TargetDegree(str, Enum):
    msc = "MSc"
    phd = "PhD"
    fellowship = "Fellowship"
    internship = "Internship"
    mixed = "Mixed"


class ProgramStyle(str, Enum):
    research_aligned = "research_aligned"
    coursework = "coursework"
    no_preference = "no_preference"


class FundingRequirement(str, Enum):
    full_only = "full_only"
    partial_ok = "partial_ok"
    self_fund_possible = "self_fund_possible"


class TestType(str, Enum):
    ielts = "IELTS"
    toefl = "TOEFL"
    duolingo = "Duolingo"
    exempt = "Exempt"
    other = "Other"


class ExtractionConfidence(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class Identity(BaseModel):
    full_name: str
    nationality: str
    current_country: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    website_url: Optional[str] = None


class Preferences(BaseModel):
    target_degree: TargetDegree
    program_style: ProgramStyle = ProgramStyle.no_preference
    target_intake_term: str
    funding_requirement: FundingRequirement
    target_regions: list[str] = Field(min_length=1)
    target_countries_priority: list[str] = Field(default_factory=list)
    target_universities: list[str] = Field(default_factory=list)
    target_fields: list[str] = Field(min_length=1)
    research_direction_one_liner: Optional[str] = None
    long_term_direction: Optional[str] = None
    anti_goals: list[str] = Field(default_factory=list)
    hours_per_week: Optional[float] = None


class EducationEntry(BaseModel):
    degree_level: str
    field: str
    institution: str
    location: Optional[str] = None
    graduation_date: Optional[str] = None
    gpa_value: Optional[float] = None
    gpa_scale: Optional[str] = None
    honors: Optional[str] = None
    is_highest: bool = False


class LanguageTest(BaseModel):
    test_type: TestType
    overall_score: Optional[float] = None
    test_date: Optional[str] = None
    notes: Optional[str] = None


class ExperienceEntry(BaseModel):
    role: str
    organization: str
    location: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    highlights: list[str] = Field(default_factory=list, max_length=4)
    is_technical: bool = True
    is_research: bool = False


class PublicationEntry(BaseModel):
    title: str
    venue: Optional[str] = None
    year: Optional[int] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    summary: Optional[str] = None
    is_peer_reviewed: bool = False


class ProjectEntry(BaseModel):
    name: str
    description: Optional[str] = None
    url: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    is_flagship: bool = False


class AwardEntry(BaseModel):
    title: str
    year: Optional[int] = None
    issuer: Optional[str] = None


class CertificationEntry(BaseModel):
    name: str
    issuer: Optional[str] = None
    year: Optional[int] = None


class ExtractionMeta(BaseModel):
    confidence: ExtractionConfidence
    fields_needing_review: list[str] = Field(default_factory=list)
    notes: Optional[str] = None


class StructuredProfile(BaseModel):
    """L2 profile — validated intake document."""

    schema_version: str = "1.0"
    identity: Identity
    preferences: Preferences
    education: list[EducationEntry] = Field(min_length=1)
    language_tests: list[LanguageTest] = Field(default_factory=list)
    experiences: list[ExperienceEntry] = Field(default_factory=list)
    publications: list[PublicationEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    awards: list[AwardEntry] = Field(default_factory=list)
    certifications: list[CertificationEntry] = Field(default_factory=list)
    connections: list[str] = Field(default_factory=list)
    search_keywords: list[str] = Field(default_factory=list)
    extraction_meta: ExtractionMeta

    @field_validator("search_keywords")
    @classmethod
    def keywords_count(cls, v: list[str]) -> list[str]:
        if v and len(v) < 10:
            raise ValueError("search_keywords should have at least 10 terms for effective filtering")
        return v

    @field_validator("education")
    @classmethod
    def one_highest_degree(cls, v: list[EducationEntry]) -> list[EducationEntry]:
        highest = [e for e in v if e.is_highest]
        if len(highest) != 1:
            raise ValueError("Exactly one education entry must have is_highest=true")
        return v


class FilterConfig(BaseModel):
    """L3 artifact — Phase 1 keyword filter."""

    must_match_any: list[str]
    profile_match_any: list[str]
    region_match_any: list[str]
    hard_drop_any: list[str]
    target_degree_levels: list[str]
    funding_requirement: str
    nationality: str


class EligibilityRules(BaseModel):
    """L3 artifact — Phase 2 rule engine."""

    require_funding: str
    reject_if_text_contains: list[str]
    boost_if_text_contains: list[str]
    target_intake: Optional[str] = None
    min_english_ielts: Optional[float] = None
    nationality: Optional[str] = None

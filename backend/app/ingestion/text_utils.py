"""Shared text parsing helpers for ingestion (no DB imports)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from dateutil import parser as date_parser


def classify_opportunity_type(title: str, summary: str = "") -> str:
    text = f"{title} {summary}".lower()
    mapping = {
        "scholarship": ["scholarship", "stipend", "tuition"],
        "fellowship": ["fellowship", "fellow"],
        "internship": ["internship", "intern "],
        "graduate_program": ["graduate program", "master", "msc", "m.sc"],
        "phd": ["phd", "doctoral", "doctorate"],
        "grant": ["grant", "funding"],
        "conference": ["conference", "symposium"],
        "workshop": ["workshop", "summer school"],
        "competition": ["competition", "hackathon", "challenge"],
    }
    for opp_type, keywords in mapping.items():
        if any(k in text for k in keywords):
            return opp_type
    return "other"


def parse_deadline(text: str) -> Optional[datetime]:
    if not text:
        return None
    patterns = [
        r"deadline[:\s]+([^\n\.]+)",
        r"due[:\s]+([^\n\.]+)",
        r"apply by[:\s]+([^\n\.]+)",
        r"closes?[:\s]+([^\n\.]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                dt = date_parser.parse(match.group(1), fuzzy=True)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except (ValueError, OverflowError):
                continue
    return None


def extract_requirements(text: str) -> list[str]:
    reqs = []
    keywords = [
        "motivation letter",
        "recommendation",
        "transcript",
        "cv",
        "resume",
        "english proficiency",
        "statement of purpose",
        "portfolio",
    ]
    lower = text.lower()
    for kw in keywords:
        if kw in lower:
            reqs.append(kw.title())
    return reqs

"""Post-submit profile pipeline — prefill, merge, compile, readiness."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from app.schemas.profile_intake import (
    DiscoveryMode,
    EligibilityRules,
    FilterConfig,
    RankingConfig,
    StructuredProfile,
)
from app.services.profile_intake import (
    ANTI_GOAL_LABELS,
    compiled_dir,
    intake_dir,
    load_raw_submission,
    project_root,
    validate_structured_profile,
    _extract_prompt_block,
)

# Form chip labels → registry IDs (non-RSS chips map to None)
SEARCH_CHIP_TO_REGISTRY: dict[str, str | None] = {
    "Scholars4Dev": "scholars4dev",
    "DAAD": "daad",
    "ProFellow": "profellow",
    "University websites": None,
    "LinkedIn": None,
    "FindAPhD / MastersPortal": None,
    "Professor cold emails": None,
    "Twitter / X academic": None,
}

REGION_ALIASES: dict[str, list[str]] = {
    "Germany": ["Germany", "German", "DAAD", "Deutschland"],
    "Europe": ["Europe", "European", "EU", "Erasmus"],
    "UK": ["UK", "United Kingdom", "Britain", "Chevening", "British"],
    "USA": ["USA", "United States", "America", "US"],
    "Canada": ["Canada", "Canadian"],
    "Australia": ["Australia", "Australian"],
}

ANTI_GOAL_DROP_PHRASES: dict[str, list[str]] = {
    "unpaid_internships": ["unpaid internship", "unpaid role", "volunteer only"],
    "non_stem": ["non-stem", "humanities only", "business administration only"],
    "no_funding_info": ["self-funded only", "no funding information"],
    "online_only": ["100% online", "online only degree", "fully remote degree"],
    "undergrad_only": ["undergraduate only", "high school only", "bachelor applicants only"],
    "bootcamp": ["coding bootcamp", "bootcamp scholarship"],
}

CV_MERGE_KEYS = (
    "experiences",
    "publications",
    "projects",
    "skills",
    "awards",
    "certifications",
    "connections",
    "search_keywords",
)

PREFILL_PATH = "structured-profile.prefill.json"


def _registry_path() -> Path:
    return project_root() / "docs" / "profile" / "source-registry.yaml"


def _prefill_path() -> Path:
    return intake_dir() / PREFILL_PATH


def _profile_truth_path() -> Path:
    return project_root() / "docs" / "profile" / "profile-truth.md"


def load_source_registry() -> dict[str, Any]:
    path = _registry_path()
    if not path.exists():
        raise FileNotFoundError(f"Source registry not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _normalize_url(url: str) -> str:
    url = url.strip()
    if url and not url.startswith(("http://", "https://")):
        return f"https://{url}"
    return url


def _parse_gpa(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _graduation_date(form: dict[str, Any]) -> str | None:
    if form.get("graduation_date"):
        return str(form["graduation_date"])
    month = form.get("graduation_month", "")
    year = form.get("graduation_year", "")
    if month and year:
        month_map = {
            "January": "01",
            "February": "02",
            "March": "03",
            "April": "04",
            "May": "05",
            "June": "06",
            "July": "07",
            "August": "08",
            "September": "09",
            "October": "10",
            "November": "11",
            "December": "12",
        }
        mm = month_map.get(str(month), "01")
        return f"{year}-{mm}"
    return None


def _degree_level(form: dict[str, Any]) -> str:
    raw = str(form.get("degree_level", "BSc"))
    if "BSc" in raw or "BE" in raw or "BA" in raw:
        return "BSc"
    if "MSc" in raw or "MS" in raw:
        return "MSc"
    if "PhD" in raw:
        return "PhD"
    return raw.split("/")[0].strip() if "/" in raw else raw


def _field_of_study(form: dict[str, Any]) -> str:
    field = form.get("field_of_study", "")
    if field == "Other" and form.get("field_of_study_other"):
        return str(form["field_of_study_other"])
    return str(field)


def _honors(form: dict[str, Any]) -> str | None:
    honors = form.get("honors", "")
    if honors == "Other" and form.get("honors_other"):
        return str(form["honors_other"]) or None
    return str(honors) if honors else None


def _intake_term(form: dict[str, Any]) -> str:
    term = form.get("target_intake_term", "")
    if term == "custom" and form.get("custom_intake_term"):
        return str(form["custom_intake_term"])
    return str(term)


def _anti_goals_labels(form: dict[str, Any]) -> list[str]:
    codes = form.get("anti_goals") or []
    labels = [ANTI_GOAL_LABELS.get(c, c) for c in codes if c != "other"]
    if form.get("anti_goals_other"):
        labels.append(str(form["anti_goals_other"]))
    return labels


def _connections_list(form: dict[str, Any]) -> list[str]:
    raw = form.get("connections", "")
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    return [p.strip() for p in re.split(r"[,;\n]", str(raw)) if p.strip()]


def _parse_list_field(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [p.strip() for p in re.split(r"[,;\n]", value) if p.strip()]
    return []


def _collapse_program_style(form: dict[str, Any]) -> str:
    styles = _parse_list_field(form.get("program_styles"))
    if not styles:
        legacy = form.get("program_style")
        return str(legacy) if legacy else "no_preference"
    if "no_preference" in styles:
        return "no_preference"
    has_research = "research_aligned" in styles
    has_coursework = "coursework" in styles
    if has_research and has_coursework:
        return "no_preference"
    if has_research:
        return "research_aligned"
    if has_coursework:
        return "coursework"
    return styles[0]


def _collapse_funding_requirement(form: dict[str, Any]) -> str:
    reqs = _parse_list_field(form.get("funding_requirements"))
    if not reqs:
        legacy = form.get("funding_requirement")
        return str(legacy) if legacy else "full_only"
    for strict in ("full_only", "partial_ok", "self_fund_possible"):
        if strict in reqs:
            return strict
    return "full_only"


def _hours_per_week(form: dict[str, Any]) -> float | None:
    raw = form.get("hours_per_week")
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _discovery_mode(form: dict[str, Any]) -> str:
    mode = form.get("discovery_mode", "open")
    return str(mode) if mode in ("open", "target_list") else "open"


def _manual_channels(form: dict[str, Any]) -> list[str]:
    chips = [str(c) for c in (form.get("search_sources") or [])]
    return [c for c in chips if SEARCH_CHIP_TO_REGISTRY.get(c) is None]


def _other_languages(form: dict[str, Any]) -> list[str]:
    langs = form.get("other_languages") or []
    if isinstance(langs, str):
        return _parse_list_field(langs)
    return [str(v) for v in langs if str(v).strip()]


def score_aggregators(form: dict[str, Any], registry: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Score registry entries; return sorted list with scores and reasons."""
    registry = registry or load_source_registry()
    target_degree = form.get("target_degree", "MSc")
    regions = [str(r) for r in (form.get("target_regions") or [])]
    chips = [str(c) for c in (form.get("search_sources") or [])]
    developing = bool(form.get("developing_country_scholarships"))

    selected_ids = {
        SEARCH_CHIP_TO_REGISTRY[c]
        for c in chips
        if c in SEARCH_CHIP_TO_REGISTRY and SEARCH_CHIP_TO_REGISTRY[c]
    }

    scored: list[dict[str, Any]] = []
    for entry in registry.get("aggregators", []):
        if entry.get("type") != "rss":
            continue
        degrees = entry.get("degree_levels") or []
        if target_degree and degrees and target_degree not in degrees:
            continue

        score = 0
        reasons: list[str] = []
        entry_id = entry["id"]

        if entry_id in selected_ids:
            score += 15
            reasons.append("user chip")

        chip_label = entry.get("chip_label")
        if chip_label and chip_label in chips:
            score += 15
            reasons.append("user chip")

        entry_regions = [str(r) for r in (entry.get("regions") or [])]
        for region in regions:
            if region in entry_regions or "global" in entry_regions:
                score += 5
                reasons.append(f"region:{region}")
                break

        if developing and "international" in (entry.get("tags") or []):
            score += 5
            reasons.append("international_scholarships")

        if "Germany" in regions and entry_id == "daad":
            score += 10
            reasons.append("germany_priority")

        if entry.get("funding_signal") == "high":
            score += 3

        tags = [str(t).lower() for t in (entry.get("tags") or [])]
        if target_degree == "Fellowship" and "fellowship" in tags:
            score += 8
            reasons.append("fellowship_focus")
        elif target_degree == "MSc" and "scholarship" in tags:
            score += 5
            reasons.append("scholarship_focus")
        elif target_degree == "PhD" and ("phd" in tags or "doctoral" in tags):
            score += 5
            reasons.append("phd_focus")
        elif target_degree == "Internship" and "internship" in tags:
            score += 5
            reasons.append("internship_focus")

        scored.append(
            {
                "id": entry_id,
                "score": score,
                "reasons": list(dict.fromkeys(reasons)),
                "entry": entry,
            }
        )

    scored.sort(key=lambda x: (-x["score"], x["id"]))
    return scored


def select_aggregators(
    form: dict[str, Any],
    count: int | None = None,
    registry: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    registry = registry or load_source_registry()
    n = count or int(registry.get("default_selection_count", 4))
    scored = score_aggregators(form, registry)
    selected = scored[:n]
    return [
        {
            "id": item["id"],
            "enabled": True,
            "priority": idx + 1,
            "user_selected": "user chip" in item["reasons"],
            "selection_reason": ", ".join(item["reasons"]) or "default",
        }
        for idx, item in enumerate(selected)
    ]


def prefill_from_form(form: dict[str, Any]) -> dict[str, Any]:
    """Build partial L2 profile from form fields — no LLM, no CV parsing."""
    nationality = form.get("nationality_code") or form.get("nationality", "")
    current = form.get("current_country_code") or form.get("current_country")

    flagship = form.get("flagship_projects") or []
    if isinstance(flagship, str):
        flagship = [p.strip() for p in re.split(r"[,;]", flagship) if p.strip()]

    projects = [
        {
            "name": name,
            "description": None,
            "url": None,
            "tags": list(form.get("target_fields") or [])[:4],
            "is_flagship": idx == 0,
        }
        for idx, name in enumerate(flagship[:2])
    ]

    aggregators = select_aggregators(form)
    discovery = _discovery_mode(form)
    manual = _manual_channels(form)

    return {
        "schema_version": "1.0",
        "identity": {
            "full_name": form.get("full_name", ""),
            "nationality": nationality,
            "current_country": current,
            "linkedin_url": _normalize_url(str(form.get("linkedin_url", ""))),
            "github_url": _normalize_url(str(form.get("github_url", ""))) or None,
            "website_url": _normalize_url(str(form.get("website_url", ""))) or None,
        },
        "preferences": {
            "target_degree": form.get("target_degree", "MSc"),
            "program_style": _collapse_program_style(form),
            "target_intake_term": _intake_term(form),
            "funding_requirement": _collapse_funding_requirement(form),
            "target_regions": list(form.get("target_regions") or []),
            "target_countries_priority": _parse_list_field(form.get("target_countries_priority")),
            "target_universities": _parse_list_field(form.get("target_universities")),
            "target_fields": list(form.get("target_fields") or []),
            "research_direction_one_liner": form.get("research_one_liner") or None,
            "long_term_direction": None,
            "anti_goals": _anti_goals_labels(form),
            "hours_per_week": _hours_per_week(form),
            "discovery_mode": discovery,
            "open_to_relocation": bool(form.get("open_to_relocation", True)),
            "other_languages": _other_languages(form),
            "mobility_notes": form.get("mobility_notes") or None,
        },
        "education": [
            {
                "degree_level": _degree_level(form),
                "field": _field_of_study(form),
                "institution": form.get("institution", ""),
                "location": None,
                "graduation_date": _graduation_date(form),
                "gpa_value": _parse_gpa(form.get("gpa")),
                "gpa_scale": str(form.get("gpa_scale", "")) or None,
                "honors": _honors(form),
                "is_highest": True,
            }
        ],
        "language_tests": (
            [
                {
                    "test_type": form.get("english_test", "IELTS"),
                    "overall_score": _parse_gpa(form.get("english_score")),
                    "test_date": form.get("english_test_date") or None,
                    "notes": None,
                }
            ]
            if form.get("english_test")
            else []
        ),
        "experiences": [],
        "publications": [],
        "projects": projects,
        "skills": [],
        "awards": [],
        "certifications": [],
        "connections": _connections_list(form),
        "search_keywords": [],
        "sources": {
            "aggregators": aggregators,
            "manual_channels": manual,
            "notes": (
                f"Selected from source-registry.yaml via region and chip scoring "
                f"(discovery_mode={discovery})"
            ),
        },
        "extraction_meta": {
            "confidence": "high",
            "fields_needing_review": [
                "experiences",
                "publications",
                "skills",
                "search_keywords",
                "preferences.long_term_direction",
            ],
            "notes": "Prefilled from form. Run CV extraction prompt for remaining fields.",
        },
    }


def prefill_from_submission(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = raw or load_raw_submission()
    if not raw:
        raise FileNotFoundError("No raw-submission.json found. Submit the intake form first.")
    return prefill_from_form(raw.get("form") or {})


def save_prefill(data: dict[str, Any]) -> Path:
    path = _prefill_path()
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_prefill() -> dict[str, Any] | None:
    path = _prefill_path()
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_year(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    match = re.search(r"(20\d{2})", text)
    return int(match.group(1)) if match else None


def _strip_json_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def load_extraction_json(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8-sig").strip()
    if not raw:
        raise ValueError(f"{path} is empty. Paste LLM JSON output before running merge.")
    return json.loads(_strip_json_fences(raw))


def normalize_extraction_output(extraction: dict[str, Any]) -> dict[str, Any]:
    """Map common LLM field names/shapes to StructuredProfile schema."""
    data = deepcopy(extraction)

    normalized_experiences: list[dict[str, Any]] = []
    for exp in data.get("experiences") or []:
        role = exp.get("role") or exp.get("title") or "Unknown role"
        org = exp.get("organization") or exp.get("company") or "Unknown organization"
        highlights = list(exp.get("highlights") or [])[:4]
        research_hints = ("research", "teaching assistant", "fellow", "publication", "r&d")
        role_org = f"{role} {org}".lower()
        normalized_experiences.append(
            {
                "role": role,
                "organization": org,
                "location": exp.get("location"),
                "start_date": exp.get("start_date"),
                "end_date": exp.get("end_date"),
                "highlights": highlights,
                "is_technical": exp.get("is_technical", True),
                "is_research": exp.get(
                    "is_research",
                    any(h in role_org for h in research_hints),
                ),
            }
        )
    data["experiences"] = normalized_experiences

    normalized_publications: list[dict[str, Any]] = []
    for pub in data.get("publications") or []:
        venue_parts = [
            str(pub.get("venue") or ""),
            str(pub.get("publisher") or ""),
            str(pub.get("location") or ""),
        ]
        venue = ", ".join(p for p in venue_parts if p) or None
        doi = pub.get("doi")
        if isinstance(doi, str) and doi.startswith("http"):
            url = doi
            doi = doi.rsplit("/", 1)[-1] if "/" in doi else doi
        else:
            url = pub.get("url")
        normalized_publications.append(
            {
                "title": pub.get("title", ""),
                "venue": venue,
                "year": pub.get("year") or _parse_year(pub.get("date")),
                "doi": doi,
                "url": url,
                "summary": pub.get("summary"),
                "is_peer_reviewed": pub.get(
                    "is_peer_reviewed",
                    pub.get("type") == "conference_paper" or bool(pub.get("publisher")),
                ),
            }
        )
    data["publications"] = normalized_publications

    normalized_projects: list[dict[str, Any]] = []
    for proj in data.get("projects") or []:
        normalized_projects.append(
            {
                "name": proj.get("name", ""),
                "description": proj.get("description"),
                "url": proj.get("url"),
                "tags": list(proj.get("tags") or []),
                "is_flagship": bool(proj.get("is_flagship")),
            }
        )
    data["projects"] = normalized_projects

    skills = data.get("skills")
    if isinstance(skills, dict):
        flat: list[str] = []
        for values in skills.values():
            if isinstance(values, list):
                flat.extend(str(v) for v in values if v)
        data["skills"] = list(dict.fromkeys(flat))
    elif isinstance(skills, list):
        data["skills"] = [str(s) for s in skills if s]

    normalized_awards: list[dict[str, Any]] = []
    for award in data.get("awards") or []:
        normalized_awards.append(
            {
                "title": award.get("title") or award.get("name") or "",
                "year": award.get("year") or _parse_year(award.get("date")),
                "issuer": award.get("issuer"),
            }
        )
    data["awards"] = normalized_awards

    normalized_certs: list[dict[str, Any]] = []
    for cert in data.get("certifications") or []:
        notes = cert.get("notes")
        normalized_certs.append(
            {
                "name": cert.get("name", ""),
                "issuer": cert.get("issuer"),
                "year": cert.get("year") or _parse_year(cert.get("date")),
            }
        )
        if notes and normalized_certs:
            # Preserve extra cert detail in issuer when notes exist
            last = normalized_certs[-1]
            if last["issuer"] and notes:
                last["issuer"] = f"{last['issuer']} ({notes})"
    data["certifications"] = normalized_certs

    normalized_edu: list[dict[str, Any]] = []
    for edu in data.get("education") or []:
        normalized_edu.append(
            {
                "degree_level": edu.get("degree_level") or "Other",
                "field": edu.get("field") or "General",
                "institution": edu.get("institution", ""),
                "location": edu.get("location"),
                "graduation_date": edu.get("graduation_date"),
                "gpa_value": edu.get("gpa_value"),
                "gpa_scale": edu.get("gpa_scale"),
                "honors": edu.get("honors"),
                "is_highest": bool(edu.get("is_highest")),
            }
        )
    data["education"] = normalized_edu

    if isinstance(data.get("connections"), str):
        data["connections"] = _connections_list({"connections": data["connections"]})

    sources = data.get("sources") or {}
    if isinstance(sources, dict):
        if "manual_sources" in sources and "manual_channels" not in sources:
            sources["manual_channels"] = sources.pop("manual_sources")
        data["sources"] = sources

    meta = data.get("extraction_meta") or {}
    data["extraction_meta"] = {
        "confidence": meta.get("confidence", "medium"),
        "fields_needing_review": list(meta.get("fields_needing_review") or []),
        "notes": meta.get("notes"),
    }

    return data


def merge_prefill_and_extraction(
    prefill: dict[str, Any],
    extraction: dict[str, Any],
) -> dict[str, Any]:
    """Merge CV extraction into prefill. Form/prefill wins on identity and preferences."""
    extraction = normalize_extraction_output(extraction)
    merged = deepcopy(prefill)

    for key in CV_MERGE_KEYS:
        value = extraction.get(key)
        if value:
            merged[key] = value

    # Append extra education entries from CV (keep prefill highest)
    extra_edu = [
        e for e in (extraction.get("education") or [])
        if not e.get("is_highest")
    ]
    if extra_edu:
        merged["education"] = list(merged.get("education") or []) + extra_edu

    if extraction.get("preferences", {}).get("long_term_direction"):
        merged.setdefault("preferences", {})["long_term_direction"] = extraction["preferences"][
            "long_term_direction"
        ]

    prefill_meta = prefill.get("extraction_meta") or {}
    extract_meta = extraction.get("extraction_meta") or {}
    review = list(dict.fromkeys(
        (prefill_meta.get("fields_needing_review") or [])
        + (extract_meta.get("fields_needing_review") or [])
    ))
    merged["extraction_meta"] = {
        "confidence": extract_meta.get("confidence") or prefill_meta.get("confidence") or "medium",
        "fields_needing_review": review,
        "notes": extract_meta.get("notes") or prefill_meta.get("notes"),
    }

    return merged


def build_cv_extraction_prompt(prefill: dict[str, Any], cv_text: str) -> str:
    template = _extract_prompt_block("llm-cv-extraction-prompt.md")
    prefill_json = json.dumps(prefill, indent=2, ensure_ascii=False)
    return (
        template.replace("{{PREFILL_JSON}}", prefill_json)
        .replace("{{CV_TEXT}}", cv_text.strip())
    )


def _degree_synonyms(degree: str) -> list[str]:
    base = {
        "MSc": ["MSc", "master", "masters", "MS", "graduate program", "postgraduate"],
        "PhD": ["PhD", "doctoral", "doctorate", "Ph.D"],
        "Fellowship": ["fellowship", "fellow"],
        "Internship": ["internship", "intern"],
        "Mixed": ["MSc", "master", "scholarship", "fellowship"],
    }
    return base.get(degree, [degree.lower()])


def _build_filter_config(profile: StructuredProfile) -> dict[str, Any]:
    prefs = profile.preferences
    identity = profile.identity

    must_match = _degree_synonyms(prefs.target_degree.value)
    must_match.extend(["scholarship", "fellowship", "fully funded", "stipend", "tuition"])

    profile_match = list(prefs.target_fields)
    profile_match.extend(profile.search_keywords)
    for proj in profile.projects:
        profile_match.extend(proj.tags)

    institution_match: list[str] = []
    if prefs.discovery_mode == DiscoveryMode.target_list:
        institution_match.extend(prefs.target_universities)
        for uni in prefs.target_universities:
            profile_match.append(uni)

    profile_match = list(dict.fromkeys(t.lower() for t in profile_match if t))[:30]
    institution_match = list(dict.fromkeys(t for t in institution_match if t))

    region_match: list[str] = []
    for region in prefs.target_regions:
        region_match.extend(REGION_ALIASES.get(region, [region]))
    region_match.extend(prefs.target_countries_priority)
    region_match = list(dict.fromkeys(r for r in region_match if r))

    hard_drop: list[str] = []
    for goal in prefs.anti_goals:
        for code, label in ANTI_GOAL_LABELS.items():
            if goal == label or code.replace("_", " ") in goal.lower():
                hard_drop.extend(ANTI_GOAL_DROP_PHRASES.get(code, []))
    hard_drop.extend(["webinar only", "conference registration", "high school"])
    hard_drop = list(dict.fromkeys(hard_drop))

    return FilterConfig(
        must_match_any=must_match[:15],
        profile_match_any=profile_match,
        region_match_any=region_match,
        institution_match_any=institution_match,
        hard_drop_any=hard_drop[:12],
        target_degree_levels=[prefs.target_degree.value],
        funding_requirement=prefs.funding_requirement.value,
        nationality=identity.nationality,
        discovery_mode=prefs.discovery_mode.value,
    ).model_dump(mode="json")


def _build_eligibility_rules(profile: StructuredProfile) -> dict[str, Any]:
    prefs = profile.preferences
    identity = profile.identity

    funding_map = {
        "full_only": "full_only",
        "partial_ok": "full_or_partial",
        "self_fund_possible": "any",
    }

    ielts_min = None
    for test in profile.language_tests:
        if test.test_type.value == "IELTS" and test.overall_score is not None:
            ielts_min = test.overall_score
            break

    intake = prefs.target_intake_term
    target_intake = None
    match = re.search(r"(20\d{2})", intake)
    if match:
        year = match.group(1)
        target_intake = f"{year}-09" if "fall" in intake.lower() else f"{year}-01"

    boost = [
        "international students",
        "developing countries",
        "global south",
        "DAAD",
        "fully funded",
        "tuition waiver",
    ]
    for lang in prefs.other_languages:
        boost.append(lang)
        boost.append(f"{lang} language")

    if not prefs.open_to_relocation:
        boost.extend(prefs.target_regions[:3])

    return EligibilityRules(
        require_funding=funding_map.get(prefs.funding_requirement.value, "full_only"),
        reject_if_text_contains=[
            "PhD only",
            "EU citizens only",
            "domestic students only",
            "undergraduate only",
            "high school students",
            "unpaid",
            "volunteer only",
        ],
        boost_if_text_contains=list(dict.fromkeys(boost)),
        target_intake=target_intake,
        min_english_ielts=ielts_min,
        nationality=identity.nationality,
        other_languages=prefs.other_languages,
        open_to_relocation=prefs.open_to_relocation,
    ).model_dump(mode="json")


def _build_ranking_config(profile: StructuredProfile) -> dict[str, Any]:
    prefs = profile.preferences
    manual = profile.sources.manual_channels if profile.sources else []

    uni_weight = 0.35 if prefs.discovery_mode == DiscoveryMode.target_list else 0.2

    return RankingConfig(
        discovery_mode=prefs.discovery_mode.value,
        university_match_weight=uni_weight,
        region_match_weight=0.1,
        interest_match_weight=0.15,
        language_match_weight=0.08,
        open_to_relocation=prefs.open_to_relocation,
        manual_channels=manual,
    ).model_dump(mode="json")


def _build_ingestion_sources(profile: StructuredProfile) -> dict[str, Any]:
    registry = load_source_registry()
    registry_by_id = {e["id"]: e for e in registry.get("aggregators", [])}

    sources_block = profile.sources
    aggregators = (sources_block.aggregators if sources_block else []) or []

    sources = []
    for sel in aggregators:
        if not sel.enabled:
            continue
        entry = registry_by_id.get(sel.id)
        if not entry:
            continue
        sources.append(
            {
                "id": sel.id,
                "name": entry["name"],
                "url": entry["url"],
                "source_type": entry.get("type", "rss"),
                "fetch_interval_minutes": entry.get("fetch_interval_minutes", 360),
                "is_active": True,
                "selection_reason": sel.selection_reason or "profile selection",
            }
        )

    return {
        "schema_version": "1.0",
        "compiled_at": datetime.now(timezone.utc).isoformat(),
        "profile_version": profile.schema_version,
        "discovery_mode": profile.preferences.discovery_mode.value,
        "manual_channels": profile.sources.manual_channels if profile.sources else [],
        "sources": sources,
    }


def _build_profile_truth(profile: StructuredProfile) -> str:
    prefs = profile.preferences
    identity = profile.identity
    highest = next(e for e in profile.education if e.is_highest)

    constraints = [
        ("Target degree", prefs.target_degree.value),
        ("Intake", prefs.target_intake_term),
        ("Funding", prefs.funding_requirement.value),
        ("Nationality", identity.nationality),
        ("Regions", ", ".join(prefs.target_regions)),
    ]
    constraint_rows = "\n".join(f"| {k} | {v} |" for k, v in constraints)

    soft = [
        ("Program style", prefs.program_style.value),
        ("Target fields", ", ".join(prefs.target_fields)),
        ("Discovery mode", prefs.discovery_mode.value),
        ("Target universities", ", ".join(prefs.target_universities) or "—"),
        ("Other languages", ", ".join(prefs.other_languages) or "—"),
        ("Open to relocation", "Yes" if prefs.open_to_relocation else "No"),
        ("Hours/week", str(prefs.hours_per_week or "—")),
    ]
    soft_rows = "\n".join(f"| {k} | {v} |" for k, v in soft)

    agg_names = []
    if profile.sources and profile.sources.aggregators:
        registry = load_source_registry()
        by_id = {e["id"]: e["name"] for e in registry.get("aggregators", [])}
        for sel in profile.sources.aggregators:
            if sel.enabled:
                agg_names.append(by_id.get(sel.id, sel.id))

    manual = profile.sources.manual_channels if profile.sources else []
    sources_block = "\n".join(
        [
            "## Ingestion sources (RSS)",
            "",
            "\n".join(f"- {n}" for n in agg_names) or "- —",
            "",
            "## Manual channels (workflow only)",
            "",
            "\n".join(f"- {c}" for c in manual) or "- —",
            "",
        ]
    )

    flagship = [p.name for p in profile.projects if p.is_flagship]
    pub_titles = [p.title for p in profile.publications[:3]]

    keywords = profile.search_keywords[:30]
    keyword_block = "\n".join(f"- {k}" for k in keywords)

    anti = "\n".join(f"- {g}" for g in prefs.anti_goals)

    long_dir = prefs.long_term_direction or prefs.research_direction_one_liner or "See target fields and CV evidence."

    return f"""# Profile Truth — {identity.full_name}

## One-line identity

{identity.full_name} — {prefs.target_degree.value} candidate targeting {', '.join(prefs.target_regions[:3])} with focus on {', '.join(prefs.target_fields[:3])}.

## Long-term direction

{long_dir}

## Hard constraints

| Constraint | Value |
|------------|-------|
{constraint_rows}

## Soft preferences

| Preference | Value |
|------------|-------|
{soft_rows}

{sources_block}

## Evidence base

- **Education:** {highest.degree_level} in {highest.field}, {highest.institution} ({highest.graduation_date or 'n/a'})
- **Experiences:** {len(profile.experiences)} roles on record
- **Publications:** {len(profile.publications)} ({'; '.join(pub_titles) if pub_titles else 'none listed'})
- **Flagship projects:** {', '.join(flagship) if flagship else '—'}

## Profile keywords

{keyword_block}

## Named anchors

| Anchor | Use when matching |
|--------|-------------------|
{chr(10).join(f'| {p.name} | {", ".join(p.tags[:4]) if p.tags else "flagship project"} |' for p in profile.projects if p.is_flagship) or '| — | — |'}

## Anti-goals

{anti}

## Decision question

Which fully funded, research-aligned {prefs.target_degree.value} opportunities best match this profile for {prefs.target_intake_term}?
"""


def compile_profile(profile: StructuredProfile | dict[str, Any]) -> dict[str, Path]:
    if isinstance(profile, dict):
        validated, errors = validate_structured_profile(profile)
        if validated is None:
            raise ValueError(f"Invalid structured profile: {'; '.join(errors)}")
        profile = validated

    out_dir = compiled_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    paths: dict[str, Path] = {}

    fc = _build_filter_config(profile)
    fc_path = out_dir / "filter_config.json"
    fc_path.write_text(json.dumps(fc, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["filter_config"] = fc_path

    er = _build_eligibility_rules(profile)
    er_path = out_dir / "eligibility_rules.json"
    er_path.write_text(json.dumps(er, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["eligibility_rules"] = er_path

    rc = _build_ranking_config(profile)
    rc_path = out_dir / "ranking_config.json"
    rc_path.write_text(json.dumps(rc, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["ranking_config"] = rc_path

    ing = _build_ingestion_sources(profile)
    ing_path = out_dir / "ingestion_sources.json"
    ing_path.write_text(json.dumps(ing, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["ingestion_sources"] = ing_path

    truth = _build_profile_truth(profile)
    truth_path = _profile_truth_path()
    truth_path.parent.mkdir(parents=True, exist_ok=True)
    truth_path.write_text(truth, encoding="utf-8")
    paths["profile_truth"] = truth_path

    return paths


def check_profile_ready(expected_sources: int = 4) -> tuple[bool, list[str]]:
    """Return (ready, messages)."""
    messages: list[str] = []
    ok = True

    structured_path = intake_dir() / "structured-profile.json"
    if not structured_path.exists():
        ok = False
        messages.append("Missing structured-profile.json")
    else:
        try:
            data = json.loads(structured_path.read_text(encoding="utf-8"))
            _, errors = validate_structured_profile(data)
            if errors:
                ok = False
                messages.append(f"structured-profile.json invalid: {errors[0]}")
        except (json.JSONDecodeError, ValidationError) as exc:
            ok = False
            messages.append(f"structured-profile.json unreadable: {exc}")

    compiled = compiled_dir()
    for name in (
        "filter_config.json",
        "eligibility_rules.json",
        "ranking_config.json",
        "ingestion_sources.json",
    ):
        p = compiled / name
        if not p.exists():
            ok = False
            messages.append(f"Missing compiled/{name} — run compile_profile.py")

    truth = _profile_truth_path()
    if not truth.exists():
        ok = False
        messages.append("Missing profile-truth.md — run compile_profile.py")

    ing_path = compiled / "ingestion_sources.json"
    if ing_path.exists():
        ing = json.loads(ing_path.read_text(encoding="utf-8"))
        count = len(ing.get("sources") or [])
        if count != expected_sources:
            ok = False
            messages.append(f"ingestion_sources.json has {count} sources, expected {expected_sources}")

    if ok:
        messages.append("Profile package ready for Sprint 1 ingest.")

    return ok, messages


def structured_profile_to_user_fields(profile: StructuredProfile) -> dict[str, Any]:
    """Map L2 structured profile → UserProfile column updates."""
    prefs = profile.preferences
    return {
        "name": profile.identity.full_name,
        "long_term_goals": prefs.long_term_direction or prefs.research_direction_one_liner or "",
        "research_interests": prefs.target_fields,
        "skills": profile.skills,
        "target_regions": prefs.target_regions,
        "target_universities": prefs.target_universities,
        "degree_level": prefs.target_degree.value,
        "connections": profile.connections,
        "projects": [p.model_dump(mode="json") for p in profile.projects],
        "constraints": {
            "discovery_mode": prefs.discovery_mode.value,
            "open_to_relocation": prefs.open_to_relocation,
            "other_languages": prefs.other_languages,
            "mobility_notes": prefs.mobility_notes,
            "funding_requirement": prefs.funding_requirement.value,
            "program_style": prefs.program_style.value,
            "target_intake_term": prefs.target_intake_term,
            "manual_channels": profile.sources.manual_channels if profile.sources else [],
            "anti_goals": prefs.anti_goals,
        },
    }

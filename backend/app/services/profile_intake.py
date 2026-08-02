"""Profile intake service — L1 draft storage, prompt assembly, validation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.config import settings
from app.schemas.profile_intake import StructuredProfile

ANTI_GOAL_LABELS: dict[str, str] = {
    "unpaid_internships": "Unpaid internships / volunteer-only roles",
    "non_stem": "Non-STEM fields",
    "no_funding_info": "Programs with no funding info for international students",
    "online_only": "Pure online degrees (no research component)",
    "undergrad_only": "Undergraduate-only opportunities",
    "bootcamp": "Generic coding bootcamp scholarships",
}


def project_root() -> Path:
    """Monorepo root (parent of backend/). Uses PROJECT_ROOT env in Docker."""
    if settings.project_root:
        return Path(settings.project_root)
    return Path(__file__).resolve().parents[3]


def intake_dir() -> Path:
    path = project_root() / "docs" / "profile" / "intake"
    path.mkdir(parents=True, exist_ok=True)
    return path


def compiled_dir() -> Path:
    path = project_root() / "docs" / "profile" / "compiled"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _draft_path() -> Path:
    return intake_dir() / "draft.json"


def _cv_path() -> Path:
    return intake_dir() / "cv.txt"


def _structured_path() -> Path:
    return intake_dir() / "structured-profile.json"


def _extraction_output_path() -> Path:
    return intake_dir() / "extraction-output.json"


def _raw_submission_path() -> Path:
    return intake_dir() / "raw-submission.json"


def _submissions_archive_dir() -> Path:
    path = intake_dir() / "submissions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_raw_submission() -> dict[str, Any] | None:
    path = _raw_submission_path()
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_raw_submission(form: dict[str, Any], cv_text: str) -> tuple[Path, str]:
    now = datetime.now(timezone.utc)
    sub_id = now.strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "schema_version": "1.0",
        "submission_id": sub_id,
        "submitted_at": now.isoformat(),
        "source": "web_ui",
        "form": form,
        "cv_text": cv_text,
        "cv_char_count": len(cv_text),
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    path = _raw_submission_path()
    path.write_text(text, encoding="utf-8")
    archive = _submissions_archive_dir() / f"{sub_id}.json"
    archive.write_text(text, encoding="utf-8")
    return path, sub_id


def _extract_prompt_block(md_filename: str) -> str:
    md_path = intake_dir() / md_filename
    if not md_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {md_path}")
    text = md_path.read_text(encoding="utf-8")
    marker = "## Prompt (copy from here)"
    idx = text.find(marker)
    if idx == -1:
        raise ValueError(f"No prompt block in {md_filename}")
    rest = text[idx + len(marker) :]
    fence_start = rest.find("```")
    if fence_start == -1:
        raise ValueError(f"No code fence in {md_filename}")
    content_start = fence_start + 3
    if rest[content_start : content_start + 1] == "\r":
        content_start += 1
    if rest[content_start : content_start + 1] == "\n":
        content_start += 1
    fence_end = rest.find("```", content_start)
    if fence_end == -1:
        raise ValueError(f"Unclosed code fence in {md_filename}")
    return rest[content_start:fence_end].strip()


def load_draft() -> dict[str, Any] | None:
    path = _draft_path()
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_draft(form: dict[str, Any], step: int, cv_text: str | None = None) -> dict[str, Any]:
    existing = load_draft() or {}
    payload = {
        "step": step,
        "form": form,
        "cv_text": cv_text if cv_text is not None else existing.get("cv_text", ""),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _draft_path().write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def load_cv_text() -> str:
    path = _cv_path()
    if path.exists():
        return path.read_text(encoding="utf-8")
    draft = load_draft()
    return (draft or {}).get("cv_text", "")


def save_cv_text(text: str) -> None:
    _cv_path().write_text(text, encoding="utf-8")
    draft = load_draft()
    if draft:
        draft["cv_text"] = text
        draft["updated_at"] = datetime.now(timezone.utc).isoformat()
        _draft_path().write_text(json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8")


def _join_list(value: Any, sep: str = ", ") -> str:
    if isinstance(value, list):
        return sep.join(str(v) for v in value if v)
    if value:
        return str(value)
    return ""


def form_answers_to_markdown(form: dict[str, Any]) -> str:
    """Convert UI form dict to text block for LLM Pass 1."""
    anti = form.get("anti_goals") or []
    anti_labels = [ANTI_GOAL_LABELS.get(k, k) for k in anti if k != "other"]
    if form.get("anti_goals_other"):
        anti_labels.append(str(form["anti_goals_other"]))

    lines = [
        "## Step 1 — Identity",
        f"1.1 Full name: {form.get('full_name', '')}",
        f"1.2 Nationality: {form.get('nationality', '')}",
        f"1.3 Current country: {form.get('current_country', '')}",
        f"1.4 LinkedIn: {form.get('linkedin_url', '')}",
        f"1.5 GitHub: {form.get('github_url', '') or '—'}",
        f"1.6 Website: {form.get('website_url', '') or '—'}",
        "",
        "## Step 3 — Education & language",
        f"3.1 Highest degree: {form.get('degree_level', '')}",
        f"3.2 Field: {form.get('field_of_study', '')}",
        f"3.3 Institution: {form.get('institution', '')}",
        f"3.4 Graduation: {form.get('graduation_date', '')}",
        f"3.5 GPA: {form.get('gpa', '')}",
        f"3.6 Honors: {form.get('honors', '') or '—'}",
        f"3.7 English test: {form.get('english_test', '')}",
        f"3.8 Score + date: {form.get('english_score', '')} {form.get('english_test_date', '')}".strip(),
    ]

    if form.get("still_studying"):
        lines.extend(
            [
                f"3.V1 Expected graduation: {form.get('expected_graduation', '')}",
                f"3.V2 Current year: {form.get('current_year', '')}",
            ]
        )

    lines.extend(
        [
            "",
            "## Step 4 — Goals & constraints",
            f"4.1 Primary target: {form.get('target_degree', '')}",
            f"4.2 Program style: {form.get('program_style', '')}",
            f"4.3 Target start term: {form.get('target_intake_term', '')}",
            f"4.4 Funding requirement: {form.get('funding_requirement', '')}",
            f"4.5 Target regions: {_join_list(form.get('target_regions'))}",
            f"4.6 Country priority: {form.get('target_countries_priority', '') or '—'}",
        ]
    )

    if form.get("developing_country_scholarships"):
        lines.append("4.V1 Developing-country scholarships: Yes")

    lines.extend(
        [
            f"4.7 Research areas: {_join_list(form.get('target_fields'))}",
            f"4.8 One-liner: {form.get('research_one_liner', '')}",
            f"4.9 Flagship projects: {form.get('flagship_projects', '') or '—'}",
        ]
    )

    if form.get("target_degree") == "PhD":
        lines.extend(
            [
                f"4.V2 Preferred supervisors/labs: {form.get('preferred_supervisors', '') or '—'}",
                f"4.V3 Open to RA before PhD: {'Yes' if form.get('open_to_ra') else 'No'}",
            ]
        )
    if form.get("target_degree") == "Fellowship":
        lines.append(
            f"4.V4 Fellowship types: {_join_list(form.get('fellowship_types')) or '—'}"
        )

    lines.extend(
        [
            f"4D Anti-goals: {', '.join(anti_labels) if anti_labels else '—'}",
            "",
            "## Step 5 — Optional depth",
            f"5.1 Target universities: {form.get('target_universities', '') or '—'}",
            f"5.2 Connections: {form.get('connections', '') or '—'}",
            f"5.3 Hours/week: {form.get('hours_per_week', '') or '—'}",
            f"5.4 Search sources today: {form.get('search_sources', '') or '—'}",
            f"5.5 Additional notes: {form.get('additional_notes', '') or '—'}",
        ]
    )

    return "\n".join(lines)


def save_form_answers_markdown(form: dict[str, Any]) -> Path:
    path = intake_dir() / "form-answers.md"
    path.write_text(form_answers_to_markdown(form), encoding="utf-8")
    return path


def build_extraction_prompt(form: dict[str, Any], cv_text: str) -> str:
    template = _extract_prompt_block("llm-extraction-prompt.md")
    form_block = form_answers_to_markdown(form)
    save_form_answers_markdown(form)
    if cv_text.strip():
        save_cv_text(cv_text)
    return (
        template.replace("{{FORM_ANSWERS}}", form_block).replace("{{CV_TEXT}}", cv_text.strip())
    )


def build_compile_prompt(structured: dict[str, Any]) -> str:
    template = _extract_prompt_block("llm-compile-prompt.md")
    json_block = json.dumps(structured, indent=2, ensure_ascii=False)
    return template.replace("{{STRUCTURED_PROFILE_JSON}}", json_block)


def validate_structured_profile(data: dict[str, Any]) -> tuple[StructuredProfile | None, list[str]]:
    try:
        profile = StructuredProfile.model_validate(data)
        return profile, []
    except ValidationError as exc:
        errors = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"])
            errors.append(f"{loc}: {err['msg']}")
        return None, errors


def save_extraction_output(data: dict[str, Any]) -> Path:
    path = _extraction_output_path()
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def save_structured_profile(profile: StructuredProfile) -> Path:
    path = _structured_path()
    path.write_text(
        json.dumps(profile.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def load_structured_profile() -> dict[str, Any] | None:
    path = _structured_path()
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def intake_status() -> dict[str, Any]:
    draft = load_draft()
    return {
        "has_draft": draft is not None,
        "current_step": (draft or {}).get("step", 0),
        "has_cv": _cv_path().exists() or bool((draft or {}).get("cv_text")),
        "has_form_answers": (intake_dir() / "form-answers.md").exists(),
        "has_extraction_output": _extraction_output_path().exists(),
        "has_structured_profile": _structured_path().exists(),
        "updated_at": (draft or {}).get("updated_at"),
    }

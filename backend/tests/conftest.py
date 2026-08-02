"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def source_registry() -> dict:
    path = FIXTURES_DIR / "source-registry.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def patch_source_registry(monkeypatch: pytest.MonkeyPatch, source_registry: dict) -> None:
    """Tests must not depend on docs/profile/source-registry.yaml being present."""
    from app.services import profile_pipeline as pipeline

    monkeypatch.setattr(pipeline, "load_source_registry", lambda: source_registry)

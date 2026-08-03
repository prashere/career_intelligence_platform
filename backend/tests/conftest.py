"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.source_registry_paths import SOURCE_REGISTRY_PATH


@pytest.fixture
def source_registry() -> dict:
    return yaml.safe_load(SOURCE_REGISTRY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def patch_source_registry(monkeypatch: pytest.MonkeyPatch, source_registry: dict) -> None:
    """Use bundled registry in tests (not docs/)."""
    from app.services import profile_pipeline as pipeline

    monkeypatch.setattr(pipeline, "load_source_registry", lambda: source_registry)

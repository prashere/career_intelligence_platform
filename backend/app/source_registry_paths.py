"""Paths to git-tracked ingestion source configuration."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

# career_intelligence_platform/config/sources/
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


def _resolve_platform_root() -> Path:
    env_root = os.environ.get("PROJECT_ROOT")
    if env_root:
        candidate = Path(env_root)
        registry = candidate / "config" / "sources" / "source-registry.yaml"
        if registry.exists():
            return candidate
        nested = candidate / "career_intelligence_platform" / "config" / "sources" / "source-registry.yaml"
        if nested.exists():
            return candidate / "career_intelligence_platform"
    return _BACKEND_ROOT


PLATFORM_ROOT = _resolve_platform_root()
SOURCES_CONFIG_DIR = PLATFORM_ROOT / "config" / "sources"
SOURCE_REGISTRY_PATH = SOURCES_CONFIG_DIR / "source-registry.yaml"
INGESTION_CONFIG_PATH = SOURCES_CONFIG_DIR / "ingestion-config.yaml"
RELEVANCE_CONFIG_PATH = SOURCES_CONFIG_DIR / "relevance-config.yaml"


@lru_cache(maxsize=1)
def load_ingestion_config() -> dict[str, Any]:
    if not INGESTION_CONFIG_PATH.exists():
        return {}
    return yaml.safe_load(INGESTION_CONFIG_PATH.read_text(encoding="utf-8")) or {}


@lru_cache(maxsize=1)
def load_relevance_config() -> dict[str, Any]:
    if not RELEVANCE_CONFIG_PATH.exists():
        return {}
    return yaml.safe_load(RELEVANCE_CONFIG_PATH.read_text(encoding="utf-8")) or {}

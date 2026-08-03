"""Path to the git-tracked aggregator catalog."""

from pathlib import Path

# backend/app/data/source-registry.yaml
SOURCE_REGISTRY_PATH = Path(__file__).resolve().parent / "data" / "source-registry.yaml"

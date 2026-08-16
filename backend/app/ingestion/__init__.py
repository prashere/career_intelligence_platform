"""Ingestion pipeline — discover, extract, canonicalize (Phase A)."""

from app.ingestion.discover.runner import validate_all_aggregators, validate_aggregator

__all__ = ["validate_aggregator", "validate_all_aggregators"]

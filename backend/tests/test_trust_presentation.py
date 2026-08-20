"""Tests for trust presentation mapping."""

from datetime import datetime, timezone

from app.models.legacy import Opportunity
from app.verification.presentation import (
    build_trust_presentation,
    derive_trust_state,
    TRUST_LABELS,
)


def _opp(**kwargs) -> Opportunity:
    o = Opportunity(
        title="Test",
        url="https://example.com/listing",
        url_hash="abc123",
        opportunity_type="scholarship",
        verification_status="unverified",
    )
    for k, v in kwargs.items():
        setattr(o, k, v)
    return o


def test_unverified_maps_to_unchecked():
    opp = _opp(verification_status="unverified")
    assert derive_trust_state(opp.verification_status) == "unchecked"
    trust = build_trust_presentation(opp)
    assert trust["state"] == "unchecked"
    assert trust["label"] == TRUST_LABELS["unchecked"]
    assert "not checked" in trust["hint"].lower()


def test_primary_confirmed_maps_to_verified():
    checked = datetime.now(timezone.utc)
    opp = _opp(
        verification_status="primary_confirmed",
        verified_at=checked,
        verification_meta={"primary_url": "https://uni.edu/grant"},
    )
    trust = build_trust_presentation(opp)
    assert trust["state"] == "verified"
    assert trust["primary_url"] == "https://uni.edu/grant"
    assert trust["checked_at"] == checked


def test_aggregator_only_maps_correctly():
    opp = _opp(verification_status="aggregator_only", verified_at=datetime.now(timezone.utc))
    trust = build_trust_presentation(opp)
    assert trust["state"] == "aggregator_only"
    assert trust["label"] == TRUST_LABELS["aggregator_only"]


def test_stale_maps_to_conflict():
    opp = _opp(
        verification_status="stale",
        verified_at=datetime.now(timezone.utc),
        verification_meta={
            "primary_url": "https://uni.edu/grant",
            "comparison": {"discrepancies": ["deadline_mismatch:delta_30_days"]},
        },
    )
    trust = build_trust_presentation(opp)
    assert trust["state"] == "conflict"
    assert trust["primary_url"] == "https://uni.edu/grant"

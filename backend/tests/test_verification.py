"""Tests for verification compare and prescreen."""

from datetime import datetime, timedelta, timezone

from app.verification.compare import compare_claims
from app.verification.contracts import AggregatorClaims, PrimaryFields
from app.verification.domain_utils import extract_domain, is_institutional_domain, normalize_org_key
from app.verification.prescreen import run_prescreen, scan_scam_phrases


def test_normalize_org_key():
    assert normalize_org_key("  DAAD  Berlin ") == "daad berlin"


def test_institutional_domain():
    assert is_institutional_domain("uni-berlin.de") is False
    assert is_institutional_domain("stanford.edu") is True


def test_extract_domain():
    assert extract_domain("https://www.example.com/path") == "example.com"


def test_scam_phrase_detection():
    hits = scan_scam_phrases("Pay to apply with processing fee")
    assert "pay to apply" in hits


def test_prescreen_stops_on_scam():
    claims = AggregatorClaims(
        title="Guaranteed acceptance scholarship",
        url="https://sketchy-new-site.xyz/apply",
        summary="Send money via wire transfer",
    )
    result = run_prescreen(claims, domain_trust=0.3)
    assert result.action == "stop"
    assert result.trust_score < 0.5


def test_prescreen_institutional_light_tier2():
    claims = AggregatorClaims(
        title="PhD Fellowship in CS",
        url="https://www.stanford.edu/fellowship",
        summary="Fully funded doctoral program",
    )
    result = run_prescreen(claims, domain_trust=0.8)
    assert result.action in ("light_tier2", "continue")
    assert result.trust_score >= 0.5


def test_compare_deadline_match_within_tolerance():
    agg = AggregatorClaims(
        title="Scholarship",
        url="https://example.com",
        deadline=datetime(2026, 10, 15, tzinfo=timezone.utc),
    )
    primary = PrimaryFields(
        deadline=datetime(2026, 10, 18, tzinfo=timezone.utc),
        funding_summary="fully funded",
        eligibility_summary="international students",
    )
    result = compare_claims(agg, primary)
    assert result.fields[0].match is True
    assert result.all_match or result.partial_match


def test_compare_stale_on_deadline_conflict():
    agg = AggregatorClaims(
        title="Scholarship",
        url="https://example.com",
        deadline=datetime(2026, 6, 1, tzinfo=timezone.utc),
        funding_type="full",
        summary="funding available",
    )
    primary = PrimaryFields(
        deadline=datetime(2027, 6, 1, tzinfo=timezone.utc),
        funding_summary="self-funded only",
        eligibility_summary="EU citizens",
    )
    result = compare_claims(agg, primary)
    assert not result.all_match
    assert result.discrepancies

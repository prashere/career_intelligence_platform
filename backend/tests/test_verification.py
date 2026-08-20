"""Tests for verification compare and prescreen."""

from datetime import datetime, timedelta, timezone

from app.verification.cache import pick_canonical_domain_from_search
from app.verification.compare import compare_claims, confirms_listing, has_material_conflict
from app.verification.contracts import AggregatorClaims, PrimaryFields
from app.verification.domain_utils import (
    domain_matches_org,
    extract_domain,
    is_institutional_domain,
    is_non_primary_domain,
    normalize_org_key,
)
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


def test_missing_aggregator_deadline_is_not_a_conflict():
    """Absence of a deadline on the aggregator is missing evidence, not disagreement."""
    agg = AggregatorClaims(
        title="Fellowship",
        url="https://opportunitydesk.org/listing",
        funding_type="full",
        summary="fully funded fellowship",
    )
    primary = PrimaryFields(
        deadline=datetime(2027, 1, 15, tzinfo=timezone.utc),
        funding_summary="fully funded fellowship",
    )
    result = compare_claims(agg, primary)
    deadline_field = next(f for f in result.fields if f.field == "deadline")

    assert deadline_field.comparable is False
    assert not any(d.startswith("deadline_mismatch") for d in result.discrepancies)
    assert result.all_match is True


def test_no_comparable_fields_does_not_confirm():
    agg = AggregatorClaims(title="Fellowship", url="https://example.com/listing")
    primary = PrimaryFields(deadline=datetime(2027, 1, 15, tzinfo=timezone.utc))
    result = compare_claims(agg, primary)

    assert result.all_match is False
    assert result.discrepancies == []


def test_non_primary_domains():
    assert is_non_primary_domain("opportunitydesk.org") is True
    assert is_non_primary_domain("linkedin.com") is True
    assert is_non_primary_domain("www.linkedin.com") is True
    assert is_non_primary_domain("science.osti.gov") is False
    assert is_non_primary_domain("stanford.edu") is False


def test_pick_domain_skips_aggregator_and_self():
    results = [
        {"title": "Listing", "url": "https://opportunitydesk.org/x", "content": ""},
        {"title": "Profile", "url": "https://linkedin.com/in/y", "content": ""},
        {"title": "EINSTEIN Fellowship", "url": "https://science.osti.gov/wdts/einstein", "content": ""},
    ]
    domain, url = pick_canonical_domain_from_search(
        "Albert Einstein Distinguished Educator",
        results,
        exclude_domains={"profellow.com"},
    )
    assert domain == "science.osti.gov"
    assert url == "https://science.osti.gov/wdts/einstein"


def test_equivalent_funding_wording_is_not_a_mismatch():
    """'(Fully Funded)' in a title and 'fully funded stipend' agree."""
    agg = AggregatorClaims(
        title="KAUST AMS School 2026 in Saudi Arabia (Fully Funded)",
        url="https://opportunitiescorners.com/kaust-ams-school-2026/",
        summary="A long description of the programme and its activities.",
    )
    primary = PrimaryFields(funding_summary="fully funded stipend")
    result = compare_claims(agg, primary)
    funding = next(f for f in result.fields if f.field == "funding")

    assert funding.comparable is True
    assert funding.match is True
    assert "funding_mismatch" not in result.discrepancies


def test_noisy_eligibility_does_not_block_confirmation():
    """Objective fields agree, so prose differences must not veto confirmation."""
    agg = AggregatorClaims(
        title="KAUST AMS School 2026 (Fully Funded)",
        url="https://opportunitiescorners.com/kaust-ams-school-2026/",
        summary="Applicants from around the world are welcome to join.",
    )
    primary = PrimaryFields(
        funding_summary="fully funded stipend",
        eligibility_summary="Enrolled MSc and PhD students in mathematics",
    )
    result = compare_claims(agg, primary)

    assert "eligibility_mismatch" in result.discrepancies
    assert confirms_listing(result) is True


def test_confirmation_requires_a_checkable_objective_field():
    agg = AggregatorClaims(
        title="Creative Catalyst Fellowship 2027",
        url="https://opportunitydesk.org/x",
        summary="Grants of up to $30,000 for artists",
    )
    primary = PrimaryFields(eligibility_summary="Pennsylvania residents only")
    result = compare_claims(agg, primary)

    assert confirms_listing(result) is False


def test_material_conflict_blocks_confirmation():
    agg = AggregatorClaims(
        title="Scholarship",
        url="https://example.com",
        deadline=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    primary = PrimaryFields(deadline=datetime(2027, 6, 1, tzinfo=timezone.utc))
    result = compare_claims(agg, primary)

    assert confirms_listing(result) is False


def test_conflicting_funding_is_still_detected():
    agg = AggregatorClaims(
        title="Fully Funded Fellowship",
        url="https://example.com",
        summary="fully funded",
    )
    primary = PrimaryFields(funding_summary="self-funded only, no stipend")
    result = compare_claims(agg, primary)

    assert "funding_mismatch" in result.discrepancies


def test_lone_eligibility_mismatch_is_not_material():
    """One fuzzy text mismatch must not hide an opportunity from the feed."""
    agg = AggregatorClaims(
        title="Creative Catalyst Fellowship",
        url="https://opportunitydesk.org/x",
        summary="Artists based anywhere may apply",
    )
    primary = PrimaryFields(eligibility_summary="Pennsylvania residents only")
    result = compare_claims(agg, primary)

    assert result.discrepancies == ["eligibility_mismatch"]
    assert has_material_conflict(result) is False


def test_deadline_mismatch_is_material():
    agg = AggregatorClaims(
        title="Scholarship",
        url="https://example.com",
        deadline=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    primary = PrimaryFields(deadline=datetime(2027, 6, 1, tzinfo=timezone.utc))
    result = compare_claims(agg, primary)

    assert has_material_conflict(result) is True


def test_domain_matches_org_accepts_own_site():
    assert domain_matches_org("catalystnow.net", "Catalyst Now Learning Initiatives") is True
    assert (
        domain_matches_org(
            "greenearthactionfoundation.org",
            "Green Earth Action Foundation (GEAF) Ambassador Programme 2027",
        )
        is True
    )


def test_domain_matches_org_rejects_republishers():
    """Third-party republishers must not count as the organization's own site."""
    assert domain_matches_org("careerflora.com", "CRCA Emerging Conflict Analysts") is False
    assert (
        domain_matches_org("globalsouthopportunities.com", "Standard Chartered") is False
    )
    assert domain_matches_org("opportunitydesk.org", "Creative Catalyst") is False


def test_pick_domain_returns_none_when_only_aggregators():
    results = [
        {"title": "Listing", "url": "https://opportunitydesk.org/x", "content": ""},
        {"title": "Same site", "url": "https://profellow.com/y", "content": ""},
    ]
    domain, url = pick_canonical_domain_from_search(
        "Some Org", results, exclude_domains={"profellow.com"}
    )
    assert domain is None
    assert url is None

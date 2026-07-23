from app.services.ingestion import classify_opportunity_type, hash_url, parse_deadline
from app.models import OpportunityType


def test_classify_scholarship():
    assert classify_opportunity_type("DAAD Scholarship 2026") == OpportunityType.scholarship


def test_classify_fellowship():
    assert classify_opportunity_type("AI Fellowship Program") == OpportunityType.fellowship


def test_hash_url_stable():
    assert hash_url("https://example.com/a") == hash_url("https://example.com/a")


def test_parse_deadline():
    result = parse_deadline("Application deadline: March 15, 2026")
    assert result is not None
    assert result.year == 2026

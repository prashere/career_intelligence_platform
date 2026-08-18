from app.models import Opportunity
from app.verification.eligibility import is_eligible_for_verification


def test_eligible_only_with_gate_admit():
    opp = Opportunity(
        title="Test",
        url="https://example.com",
        ingestion_meta={"gate": {"verdict": "admit", "score": 0.7}},
    )
    assert is_eligible_for_verification(opp) is True


def test_not_eligible_without_gate():
    opp = Opportunity(title="Test", url="https://example.com", ingestion_meta=None)
    assert is_eligible_for_verification(opp) is False


def test_not_eligible_on_reject_verdict():
    opp = Opportunity(
        title="Test",
        url="https://example.com",
        ingestion_meta={"gate": {"verdict": "reject"}},
    )
    assert is_eligible_for_verification(opp) is False

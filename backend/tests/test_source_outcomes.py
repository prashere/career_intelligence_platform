from app.services.source_outcomes import (
    compute_admit_rate,
    effective_authority,
    merge_outcome_stats,
    outcome_bonus_for_scoring,
)


def test_compute_admit_rate():
    assert compute_admit_rate(10, 40) == 0.25
    assert compute_admit_rate(0, 0) is None


def test_merge_outcome_stats_accumulates():
    merged = merge_outcome_stats(
        {"runs": 1, "discovered_total": 20, "admitted_total": 5, "rejected_total": 15, "created_total": 2, "updated_total": 1},
        {"discovered": 30, "admitted": 8, "rejected_at_discover": 20, "rejected_after_detail": 2, "created": 3, "updated": 1},
    )
    assert merged["runs"] == 2
    assert merged["discovered_total"] == 50
    assert merged["admit_rate"] == round(13 / 50, 4)


def test_outcome_bonus_high_admit_rate():
    bonus, reasons = outcome_bonus_for_scoring({"admit_rate": 0.4, "runs": 5})
    assert bonus == 8
    assert any("high_admit_rate" in r for r in reasons)


def test_outcome_bonus_low_admit_rate_penalty():
    bonus, reasons = outcome_bonus_for_scoring({"admit_rate": 0.05, "runs": 4})
    assert bonus == -6
    assert any("low_admit_rate" in r for r in reasons)


def test_effective_authority_blends_static_and_empirical():
    eff = effective_authority(0.7, {"admit_rate": 0.4})
    assert 0.5 < eff < 1.0

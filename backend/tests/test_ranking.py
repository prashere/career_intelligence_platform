from app.services.ranking import cosine_similarity, fit_level_from_score, urgency_score
from app.models import FitLevel
from datetime import datetime, timedelta, timezone


def test_cosine_similarity():
    a = [1.0, 0.0, 0.0]
    b = [1.0, 0.0, 0.0]
    assert cosine_similarity(a, b) == 1.0


def test_fit_level():
    assert fit_level_from_score(0.8) == FitLevel.strong
    assert fit_level_from_score(0.6) == FitLevel.moderate
    assert fit_level_from_score(0.3) == FitLevel.weak


def test_urgency_score():
    soon = datetime.now(timezone.utc) + timedelta(days=3)
    assert urgency_score(soon) == 1.0
    assert urgency_score(None) == 0.2

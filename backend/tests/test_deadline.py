"""Tests for deadline math and bucket classification."""

from datetime import datetime, timedelta, timezone

from app.services.calendar_export import create_calendar_event, google_calendar_url
from app.services.ranking import days_until, deadline_bucket, urgency_label


def test_days_until_ceiling_not_truncation():
    base = datetime.now(timezone.utc).replace(microsecond=0)
    assert days_until(base + timedelta(hours=23)) == 1
    assert days_until(base + timedelta(hours=47)) == 2
    assert days_until(base + timedelta(minutes=30)) == 1


def test_days_until_overdue():
    now = datetime.now(timezone.utc)
    assert days_until(now - timedelta(hours=2)) == -1


def test_deadline_bucket_values():
    assert deadline_bucket(None) == "unknown"
    assert deadline_bucket(-2) == "overdue"
    assert deadline_bucket(0) == "today"
    assert deadline_bucket(2) == "within_3_days"
    assert deadline_bucket(5) == "within_7_days"
    assert deadline_bucket(20) == "within_30_days"
    assert deadline_bucket(45) == "later"


def test_urgency_label_uses_days_not_weeks_for_mid_range():
    assert urgency_label(10) == "10 days left"
    assert urgency_label(1) == "1 day left"
    assert urgency_label(0) == "Due today"


def test_calendar_event_has_uid_and_alarm():
    deadline = datetime(2026, 10, 15, tzinfo=timezone.utc)
    ics = create_calendar_event("Test Fellowship", deadline, "https://example.com/apply")
    assert "BEGIN:VCALENDAR" in ics
    assert "UID:" in ics
    assert "DTSTAMP" in ics
    assert "VALARM" in ics
    assert "https://example.com/apply" in ics


def test_google_calendar_url():
    deadline = datetime(2026, 10, 15, tzinfo=timezone.utc)
    url = google_calendar_url("Test Fellowship", deadline, "https://example.com")
    assert "calendar.google.com" in url
    assert "20261015" in url

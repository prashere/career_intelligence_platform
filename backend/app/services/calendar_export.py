"""Calendar export helpers for opportunity deadlines."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from uuid import uuid4

from icalendar import Alarm, Calendar, Event


def create_calendar_event(title: str, deadline: datetime, url: str = "") -> str:
    """Build a valid VCALENDAR with UID, DTSTAMP, all-day dates, and a VALARM."""
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)

    cal = Calendar()
    cal.add("prodid", "-//Career Intelligence//EN")
    cal.add("version", "2.0")

    event = Event()
    event.add("uid", f"career-intel-{uuid4()}@career-intelligence")
    event.add("dtstamp", datetime.now(timezone.utc))
    event.add("summary", title)

    start_date = deadline.date()
    event.add("dtstart", start_date)
    event.add("dtend", start_date + timedelta(days=1))

    description_parts = ["Application deadline"]
    if url:
        description_parts.append(url)
    event.add("description", "\n".join(description_parts))
    if url:
        event.add("url", url)

    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("description", f"Deadline reminder: {title}")
    alarm.add("trigger", timedelta(days=-1))
    event.add_component(alarm)

    cal.add_component(event)
    return cal.to_ical().decode("utf-8")


def google_calendar_url(title: str, deadline: datetime, url: str = "") -> str:
    """Google Calendar template URL (no auth required on the client)."""
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    start = deadline.strftime("%Y%m%d")
    end = (deadline + timedelta(days=1)).strftime("%Y%m%d")
    params = [
        "action=TEMPLATE",
        f"text={quote(title)}",
        f"dates={start}/{end}",
    ]
    if url:
        params.append(f"details={quote(url)}")
    return "https://calendar.google.com/calendar/render?" + "&".join(params)

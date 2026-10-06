"""Quiet hours: the part of the day when a notification should wait."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo


def local_now(now_utc: datetime, tz_name: Optional[str]) -> Optional[datetime]:
    """The current time in the person's own time zone, or None if that's not known."""
    if not tz_name:
        return None
    try:
        return now_utc.astimezone(ZoneInfo(tz_name))
    except Exception:
        return None


def in_quiet_hours(now_utc: datetime, tz_name: Optional[str], start: float, end: float) -> bool:
    """True when it is currently inside the person's quiet window.

    start and end are hours of the day (22.5 means 10:30 pm). A window that
    runs past midnight (22 to 7) is handled. If the person's time zone isn't
    known there is no way to tell, so nothing is held back.
    """
    local = local_now(now_utc, tz_name)
    if local is None or start == end:
        return False
    hour = local.hour + local.minute / 60.0
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end

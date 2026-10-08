"""
"Today" where the person is. The server runs on UTC, which is a different
calendar day from Queensland's for ten hours of every day, so anything that
means "this week" or "in the last 60 days" asks here.

Uses the time zone the app sent (notification_prefs.tz), or Australia/Brisbane
(no daylight saving) when none is known.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

DEFAULT_TZ = "Australia/Brisbane"


def today_in(tz_name: Optional[str], now_utc: Optional[datetime] = None) -> date:
    now = now_utc or datetime.now(timezone.utc)
    for name in (tz_name, DEFAULT_TZ):
        if not name:
            continue
        try:
            return now.astimezone(ZoneInfo(name)).date()
        except Exception:
            continue
    return now.date()


async def user_today(user_id: str) -> date:
    """Today's date in the person's own time zone."""
    from utils.push import get_prefs  # imported here: push pulls in more than this module needs

    prefs = await get_prefs(user_id)
    return today_in((prefs or {}).get("tz"))

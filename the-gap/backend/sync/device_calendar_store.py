"""
Persistent storage for on-device Calendar data (EventKit), pushed from the
mobile app — mirrors sync/apple_health_store.py exactly, for the same
reason: Apple has no server-side Calendar OAuth API. EventKit only exists
on-device, so the native app reads it locally and POSTs the aggregated
daily data here, same as Apple Health.

This exists alongside Google Calendar, not instead of it — Google
Calendar OAuth still reaches anyone who *only* uses the standalone
Google Calendar app. EventKit only sees calendars actually added at the
iOS system level (Settings -> Calendar -> Accounts). daily_sync.py
combines both sources: Google Calendar takes priority for any day it
has data for, and this fills in gaps (or covers users who never
completed Google's OAuth verification/test-user flow at all).

Table DDL (run once in Supabase SQL editor):
  CREATE TABLE IF NOT EXISTS device_calendar_daily (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    entry_date DATE NOT NULL,
    calendar_events NUMERIC,
    meeting_hours NUMERIC,
    has_late_meeting NUMERIC,
    is_meeting_free NUMERIC,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, entry_date)
  );
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import httpx
import pandas as pd

logger = logging.getLogger(__name__)


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


async def upsert_device_calendar_rows(user_id: str, daily_rows: dict[str, dict[str, float]]) -> None:
    """
    Saves each day's device-calendar aggregates permanently, keyed by
    (user_id, date). A later sync for the same date overwrites that
    date's row rather than duplicating it — same upsert pattern as
    Apple Health.
    """
    if not daily_rows:
        return

    payload = [
        {
            "user_id": user_id,
            "entry_date": date,
            "calendar_events": values.get("calendar_events"),
            "meeting_hours": values.get("meeting_hours"),
            "has_late_meeting": values.get("has_late_meeting"),
            "is_meeting_free": values.get("is_meeting_free"),
        }
        for date, values in daily_rows.items()
    ]

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                _sb_url("device_calendar_daily"),
                headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                params={"on_conflict": "user_id,entry_date"},
                json=payload,
            )
            resp.raise_for_status()
    except Exception as exc:
        # Non-fatal by design: even if persistent storage fails, the sync
        # that's about to run can still use this same data for right now —
        # it just won't be remembered for next time.
        logger.warning("Device calendar upsert failed (continuing anyway): %s", exc)


async def get_device_calendar_dataframe(user_id: str, days: int = 90) -> pd.DataFrame:
    """Fetch this user's stored device-calendar history as a date-indexed DataFrame."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                _sb_url("device_calendar_daily"),
                headers=_sb_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "entry_date": f"gte.{since}",
                    "select": "entry_date,calendar_events,meeting_hours,has_late_meeting,is_meeting_free",
                },
            )
            resp.raise_for_status()
            rows = resp.json() or []
    except Exception as exc:
        logger.warning("Device calendar fetch failed (continuing without it): %s", exc)
        return pd.DataFrame()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).set_index("entry_date")
    df.index = pd.to_datetime(df.index)
    df = df.dropna(how="all")  # drop rows where every metric is null
    return df

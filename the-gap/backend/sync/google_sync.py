"""
Google Calendar sync — pulls calendar events via the Google Calendar API v3.
Uses stored OAuth tokens from Supabase user_connections table.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

GOOGLE_CALENDAR_API = "https://www.googleapis.com/calendar/v3"


async def refresh_google_token(
    refresh_token: str,
    client_id: str,
    client_secret: str,
) -> dict:
    """Get a new access token using the refresh token."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_google_calendar_data(
    access_token: str,
    days_back: int = 90,
) -> pd.DataFrame:
    """
    Fetch Google Calendar events for the last N days.
    Returns a DataFrame with daily calendar features.
    """
    now = datetime.now(timezone.utc)
    time_min = (now - timedelta(days=days_back)).isoformat()
    time_max = now.isoformat()

    headers = {"Authorization": f"Bearer {access_token}"}
    all_events = []
    page_token = None

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            params = {
                "calendarId": "primary",
                "timeMin": time_min,
                "timeMax": time_max,
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": 500,
            }
            if page_token:
                params["pageToken"] = page_token

            resp = await client.get(
                f"{GOOGLE_CALENDAR_API}/calendars/primary/events",
                headers=headers,
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

            all_events.extend(data.get("items", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break

    if not all_events:
        return pd.DataFrame()

    # Build daily features
    rows: dict[str, dict] = {}
    date_range = pd.date_range(
        start=(now - timedelta(days=days_back)).date(),
        end=now.date(),
        freq="D",
    )
    for date in date_range:
        rows[str(date.date())] = {
            "calendar_events": 0,
            "meeting_hours": 0.0,
            "has_late_meeting": 0,
            "is_meeting_free": 1,
        }

    for event in all_events:
        if event.get("status") == "cancelled":
            continue

        start_info = event.get("start", {})
        end_info = event.get("end", {})
        start_str = start_info.get("dateTime") or start_info.get("date")
        end_str = end_info.get("dateTime") or end_info.get("date")

        if not start_str or not end_str:
            continue

        try:
            start_dt = pd.Timestamp(start_str)
            end_dt = pd.Timestamp(end_str)
            duration_h = (end_dt - start_dt).total_seconds() / 3600
        except Exception:
            continue

        # Skip all-day events
        if duration_h >= 20:
            continue

        date_key = str(start_dt.date())
        if date_key not in rows:
            continue

        rows[date_key]["calendar_events"] += 1
        rows[date_key]["meeting_hours"] += max(0, duration_h)
        rows[date_key]["is_meeting_free"] = 0

        if start_dt.hour >= 18:
            rows[date_key]["has_late_meeting"] = 1

    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index = pd.to_datetime(df.index)
    df.index.name = "date"
    df = df.sort_index()
    df["meeting_hours"] = df["meeting_hours"].round(2)

    logger.info("Google Calendar sync: %d days fetched, %d events", len(df), len(all_events))
    return df

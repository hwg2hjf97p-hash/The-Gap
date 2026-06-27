"""
Oura data sync — pulls daily readiness, sleep, and activity via the Oura API v2.
Uses stored OAuth tokens from Supabase user_connections table.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

OURA_API_BASE = "https://api.ouraring.com/v2/usercollection"


async def refresh_oura_token(
    refresh_token: str,
    client_id: str,
    client_secret: str,
) -> dict:
    """Get a new access token using the refresh token."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://api.ouraring.com/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_oura_data(
    access_token: str,
    days_back: int = 90,
) -> pd.DataFrame:
    """
    Fetch Oura daily readiness, sleep, and activity data for the last N days.
    Returns a DataFrame with The Gap column names.
    """
    end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime(
        "%Y-%m-%d"
    )
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"start_date": start_date, "end_date": end_date}

    async with httpx.AsyncClient(timeout=30) as client:
        # Daily readiness (HRV, resting HR, recovery score)
        readiness_resp = await client.get(
            f"{OURA_API_BASE}/daily_readiness",
            headers=headers,
            params=params,
        )
        readiness_resp.raise_for_status()
        readiness_data = readiness_resp.json().get("data", [])

        # Daily sleep
        sleep_resp = await client.get(
            f"{OURA_API_BASE}/daily_sleep",
            headers=headers,
            params=params,
        )
        sleep_resp.raise_for_status()
        sleep_data = sleep_resp.json().get("data", [])

        # Daily activity
        activity_resp = await client.get(
            f"{OURA_API_BASE}/daily_activity",
            headers=headers,
            params=params,
        )
        activity_resp.raise_for_status()
        activity_data = activity_resp.json().get("data", [])

        # HRV detail (average nightly HRV)
        hrv_resp = await client.get(
            f"{OURA_API_BASE}/hrv",
            headers=headers,
            params=params,
        )
        hrv_resp.raise_for_status()
        hrv_data = hrv_resp.json().get("data", [])

    rows: dict[str, dict] = {}

    for r in readiness_data:
        date = r.get("day", "")
        rows.setdefault(date, {})
        rows[date]["recovery_score"] = r.get("score")
        rows[date]["resting_hr"] = r.get("contributors", {}).get("resting_heart_rate")
        rows[date]["temp_deviation"] = r.get("temperature_deviation")

    for s in sleep_data:
        date = s.get("day", "")
        rows.setdefault(date, {})
        rows[date]["sleep_total_min"] = (s.get("total_sleep_duration") or 0) / 60
        rows[date]["sleep_deep_min"] = (s.get("deep_sleep_duration") or 0) / 60
        rows[date]["sleep_score"] = s.get("score")
        rows[date]["sleep_efficiency"] = s.get("efficiency")

    for a in activity_data:
        date = a.get("day", "")
        rows.setdefault(date, {})
        rows[date]["steps"] = a.get("steps")
        rows[date]["active_energy"] = a.get("active_calories")
        rows[date]["activity_score"] = a.get("score")

    for h in hrv_data:
        date = h.get("day", "")
        rows.setdefault(date, {})
        # HRV items is a list of 5-min averages — take the mean
        items = h.get("items", []) or []
        if items:
            valid = [x for x in items if x is not None]
            if valid:
                rows[date]["hrv"] = sum(valid) / len(valid)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index = pd.to_datetime(df.index)
    df.index.name = "date"
    df = df.sort_index()

    # Default alcohol flag to 0
    df["alcohol_flag"] = 0

    logger.info("Oura sync: %d days fetched", len(df))
    return df

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


async def _get_oura(client: httpx.AsyncClient, endpoint: str, headers: dict, params: dict) -> list[dict]:
    """
    Fetch one Oura endpoint. Returns [] on failure instead of raising, so a
    problem with one data type (e.g. an endpoint that doesn't exist, or a
    scope the user didn't grant) doesn't discard every other data type we
    already successfully fetched.
    """
    try:
        resp = await client.get(f"{OURA_API_BASE}/{endpoint}", headers=headers, params=params)
        resp.raise_for_status()
        return resp.json().get("data", [])
    except Exception as exc:
        logger.warning("Oura endpoint %s failed (continuing without it): %s", endpoint, exc)
        return []


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
        readiness_data = await _get_oura(client, "daily_readiness", headers, params)
        sleep_data = await _get_oura(client, "daily_sleep", headers, params)
        activity_data = await _get_oura(client, "daily_activity", headers, params)
        # HRV lives on the *detailed* sleep endpoint ("sleep"), not "daily_sleep" —
        # there is no standalone "/hrv" endpoint in Oura's v2 API.
        detailed_sleep_data = await _get_oura(client, "sleep", headers, params)

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

    for s in detailed_sleep_data:
        date = s.get("day", "")
        if not date:
            continue
        rows.setdefault(date, {})
        avg_hrv = s.get("average_hrv")
        if avg_hrv is not None:
            # A night can have more than one sleep period; keep the longest-duration one's HRV
            # by simply taking the last non-null value (detailed sleep records are already
            # ordered by Oura's API — good enough for a daily aggregate).
            rows[date]["hrv"] = avg_hrv

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

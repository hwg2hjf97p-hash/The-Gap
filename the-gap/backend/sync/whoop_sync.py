"""
Whoop data sync — pulls HRV, sleep, and recovery data via the Whoop API.
Uses stored OAuth tokens from Supabase user_connections table.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

WHOOP_API_BASE = "https://api.prod.whoop.com/developer/v1"


async def refresh_whoop_token(
    refresh_token: str,
    client_id: str,
    client_secret: str,
) -> dict:
    """Get a new access token using the refresh token."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://api.prod.whoop.com/oauth/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_whoop_data(
    access_token: str,
    days_back: int = 90,
) -> pd.DataFrame:
    """
    Fetch Whoop recovery, sleep, and cycle data for the last N days.
    Returns a DataFrame with The Gap column names.
    """
    start = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime(
        "%Y-%m-%dT00:00:00.000Z"
    )
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient(timeout=30) as client:
        # Fetch recovery records
        recovery_resp = await client.get(
            f"{WHOOP_API_BASE}/recovery",
            headers=headers,
            params={"start": start, "limit": 200},
        )
        recovery_resp.raise_for_status()
        recovery_records = recovery_resp.json().get("records", [])

        # Fetch sleep records
        sleep_resp = await client.get(
            f"{WHOOP_API_BASE}/activity/sleep",
            headers=headers,
            params={"start": start, "limit": 200},
        )
        sleep_resp.raise_for_status()
        sleep_records = sleep_resp.json().get("records", [])

        # Fetch cycle records (steps, active calories)
        cycle_resp = await client.get(
            f"{WHOOP_API_BASE}/cycle",
            headers=headers,
            params={"start": start, "limit": 200},
        )
        cycle_resp.raise_for_status()
        cycle_records = cycle_resp.json().get("records", [])

    # Build daily rows
    rows: dict[str, dict] = {}

    for r in recovery_records:
        date = r.get("created_at", "")[:10]
        score = r.get("score", {}) or {}
        rows.setdefault(date, {})["hrv"] = score.get("hrv_rmssd_on_wakeup")
        rows[date]["resting_hr"] = score.get("resting_heart_rate")
        rows[date]["recovery_score"] = score.get("recovery_score")

    for s in sleep_records:
        date = s.get("start", "")[:10]
        score = s.get("score", {}) or {}
        stage_summary = score.get("stage_summary", {}) or {}
        rows.setdefault(date, {})
        total_ms = stage_summary.get("total_in_bed_time_milli", 0) or 0
        deep_ms = stage_summary.get("slow_wave_sleep_duration_milli", 0) or 0
        rows[date]["sleep_total_min"] = total_ms / 60000
        rows[date]["sleep_deep_min"] = deep_ms / 60000
        rows[date]["sleep_score"] = score.get("sleep_performance_percentage")

    for c in cycle_records:
        date = c.get("start", "")[:10]
        score = c.get("score", {}) or {}
        rows.setdefault(date, {})
        rows[date]["steps"] = score.get("step_count")
        rows[date]["active_energy"] = score.get("kilojoule_active") or 0
        if rows[date]["active_energy"]:
            rows[date]["active_energy"] *= 0.239  # kJ → kcal

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index = pd.to_datetime(df.index)
    df.index.name = "date"
    df = df.sort_index()

    # Default alcohol flag to 0 — not available via API
    df["alcohol_flag"] = 0

    logger.info("Whoop sync: %d days fetched", len(df))
    return df

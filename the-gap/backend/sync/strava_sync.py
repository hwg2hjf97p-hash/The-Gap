"""
Strava data sync — pulls activities, training load, and heart rate data.
Uses stored OAuth tokens from Supabase user_connections table.

Key data points extracted:
  - activity_type: run, ride, swim, weighttraining, etc.
  - duration_min: total activity duration in minutes
  - distance_km: distance covered
  - avg_hr: average heart rate during activity
  - max_hr: max heart rate
  - suffer_score: Strava's perceived effort score (0-100+)
  - training_load: estimated daily training load (TSS proxy)
  - is_hard_day: binary — suffer_score > 50
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from collections import defaultdict

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

STRAVA_API_BASE = "https://www.strava.com/api/v3"


async def refresh_strava_token(
    refresh_token: str,
    client_id: str,
    client_secret: str,
) -> dict:
    """Get a new access token using the refresh token."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://www.strava.com/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_strava_data(
    access_token: str,
    days_back: int = 90,
) -> pd.DataFrame:
    """
    Fetch Strava activities for the last N days.
    Returns a DataFrame with daily training features.
    """
    after_ts = int(
        (datetime.now(timezone.utc) - timedelta(days=days_back)).timestamp()
    )
    headers = {"Authorization": f"Bearer {access_token}"}
    all_activities = []
    page = 1

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            resp = await client.get(
                f"{STRAVA_API_BASE}/athlete/activities",
                headers=headers,
                params={
                    "after": after_ts,
                    "per_page": 100,
                    "page": page,
                },
            )
            resp.raise_for_status()
            activities = resp.json()
            if not activities:
                break
            all_activities.extend(activities)
            if len(activities) < 100:
                break
            page += 1

    if not all_activities:
        return pd.DataFrame()

    # Aggregate by day
    daily: dict[str, dict] = defaultdict(lambda: {
        "training_load": 0.0,
        "activity_minutes": 0.0,
        "activity_count": 0,
        "avg_hr_sum": 0.0,
        "avg_hr_count": 0,
        "max_suffer_score": 0,
        "has_run": 0,
        "has_ride": 0,
        "has_strength": 0,
        "is_hard_day": 0,
    })

    for act in all_activities:
        date = act.get("start_date_local", "")[:10]
        if not date:
            continue

        duration_min = (act.get("moving_time") or 0) / 60
        suffer = act.get("suffer_score") or 0
        avg_hr = act.get("average_heartrate") or 0
        act_type = (act.get("type") or "").lower()

        # Training load proxy: duration * intensity factor
        # Intensity based on suffer_score or HR zone estimate
        intensity = min(suffer / 50, 2.0) if suffer > 0 else 0.7
        load = duration_min * intensity

        daily[date]["training_load"] += load
        daily[date]["activity_minutes"] += duration_min
        daily[date]["activity_count"] += 1
        daily[date]["max_suffer_score"] = max(daily[date]["max_suffer_score"], suffer)

        if avg_hr > 0:
            daily[date]["avg_hr_sum"] += avg_hr
            daily[date]["avg_hr_count"] += 1

        if "run" in act_type:
            daily[date]["has_run"] = 1
        if "ride" in act_type or "cycling" in act_type:
            daily[date]["has_ride"] = 1
        if "weight" in act_type or "crossfit" in act_type or "strength" in act_type:
            daily[date]["has_strength"] = 1
        if suffer > 50:
            daily[date]["is_hard_day"] = 1

    rows = []
    for date, vals in daily.items():
        row = {"date": date}
        row.update(vals)
        if vals["avg_hr_count"] > 0:
            row["workout_avg_hr"] = round(vals["avg_hr_sum"] / vals["avg_hr_count"], 1)
        else:
            row["workout_avg_hr"] = None
        row["training_load"] = round(vals["training_load"], 1)
        row["activity_minutes"] = round(vals["activity_minutes"], 1)
        rows.append(row)

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()

    # Drop helper columns
    df = df.drop(columns=["avg_hr_sum", "avg_hr_count"], errors="ignore")

    # Fill rest days with 0
    date_range = pd.date_range(
        start=df.index.min(),
        end=datetime.now(timezone.utc).date(),
        freq="D",
    )
    df = df.reindex(date_range, fill_value=0)
    df.index.name = "date"

    # Rolling 7-day training load (chronic load proxy)
    df["training_load_7d"] = df["training_load"].rolling(7, min_periods=1).sum()

    logger.info("Strava sync: %d days, %d activities", len(df), len(all_activities))
    return df

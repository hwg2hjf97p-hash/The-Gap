"""
Environment data — weather and commute time as causal inputs.

Weather comes from Open-Meteo (genuinely free, no API key, includes
geocoding) — real historical data can be backfilled immediately once a
location is saved. Commute time comes from Google's Distance Matrix API
(requires a Google Cloud API key with billing enabled) — this one can
only be tracked forward from today, since live traffic estimates aren't
retroactive; there's no way to backfill "what would traffic have been
like" for past days.

Table DDL (run once in Supabase SQL editor):
  CREATE TABLE IF NOT EXISTS user_locations (
    user_id TEXT PRIMARY KEY,
    home_address TEXT,
    home_lat NUMERIC,
    home_lon NUMERIC,
    work_address TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
  );

  CREATE TABLE IF NOT EXISTS environment_daily (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    entry_date DATE NOT NULL,
    rainfall_mm NUMERIC,
    temp_c NUMERIC,
    is_rainy INTEGER,
    commute_minutes NUMERIC,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, entry_date)
  );
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

OPEN_METEO_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


async def geocode_address(address: str) -> tuple[float, float] | None:
    """Turns a city/address string into (lat, lon) using Open-Meteo's free geocoding — no API key needed."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(OPEN_METEO_GEOCODE_URL, params={"name": address, "count": 1})
            resp.raise_for_status()
            results = resp.json().get("results")
            if not results:
                return None
            return results[0]["latitude"], results[0]["longitude"]
    except Exception as exc:
        logger.warning("Geocoding failed for %r: %s", address, exc)
        return None


async def save_user_location(user_id: str, home_address: str, work_address: str = "") -> bool:
    """Geocodes the home address and persists both addresses for this user."""
    coords = await geocode_address(home_address)
    if coords is None:
        return False
    lat, lon = coords
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _sb_url("user_locations"),
                headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                params={"on_conflict": "user_id"},
                json={
                    "user_id": user_id,
                    "home_address": home_address,
                    "home_lat": lat,
                    "home_lon": lon,
                    "work_address": work_address,
                },
            )
            resp.raise_for_status()
            return True
    except Exception as exc:
        logger.error("Saving user location failed for %s: %s", user_id[:8], exc)
        return False


async def get_user_location(user_id: str) -> Optional[dict]:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                _sb_url("user_locations"),
                headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "select": "*"},
            )
            resp.raise_for_status()
            rows = resp.json() or []
            return rows[0] if rows else None
    except Exception as exc:
        logger.warning("Fetching user location failed for %s: %s", user_id[:8], exc)
        return None


async def fetch_and_store_weather(user_id: str, lat: float, lon: float, days_back: int = 90) -> int:
    """
    Pulls real historical daily weather (rain, temperature) for the last
    N days and stores it — this is the one part of environment data that
    CAN be backfilled immediately, unlike commute time.
    Returns the number of days successfully stored.
    """
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days_back)
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                OPEN_METEO_ARCHIVE_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "daily": "precipitation_sum,temperature_2m_mean",
                    "timezone": "auto",
                },
            )
            resp.raise_for_status()
            daily = resp.json().get("daily", {})
    except Exception as exc:
        logger.warning("Weather fetch failed for %s: %s", user_id[:8], exc)
        return 0

    dates = daily.get("time", [])
    rain = daily.get("precipitation_sum", [])
    temp = daily.get("temperature_2m_mean", [])
    if not dates:
        return 0

    payload = [
        {
            "user_id": user_id,
            "entry_date": d,
            "rainfall_mm": rain[i] if i < len(rain) else None,
            "temp_c": temp[i] if i < len(temp) else None,
            "is_rainy": 1 if (rain[i] if i < len(rain) else 0) and rain[i] > 1.0 else 0,
        }
        for i, d in enumerate(dates)
    ]

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                _sb_url("environment_daily"),
                headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                params={"on_conflict": "user_id,entry_date"},
                json=payload,
            )
            resp.raise_for_status()
        return len(payload)
    except Exception as exc:
        logger.warning("Weather upsert failed for %s: %s", user_id[:8], exc)
        return 0


async def fetch_and_store_commute(user_id: str, home_address: str, work_address: str) -> bool:
    """
    Fetches today's live commute estimate (with current traffic) between
    home and work, and stores it against today's date. Only ever writes
    "today" — there's no retroactive traffic data to backfill with.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
    if not api_key or not work_address:
        return False

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                DISTANCE_MATRIX_URL,
                params={
                    "origins": home_address,
                    "destinations": work_address,
                    "departure_time": "now",
                    "key": api_key,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            element = data["rows"][0]["elements"][0]
            if element.get("status") != "OK":
                logger.warning("Distance Matrix returned status=%s for user %s", element.get("status"), user_id[:8])
                return False
            duration_min = element["duration_in_traffic"]["value"] / 60 if "duration_in_traffic" in element else element["duration"]["value"] / 60
    except Exception as exc:
        logger.warning("Commute fetch failed for %s: %s", user_id[:8], exc)
        return False

    today = datetime.now(timezone.utc).date().isoformat()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _sb_url("environment_daily"),
                headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                params={"on_conflict": "user_id,entry_date"},
                json={"user_id": user_id, "entry_date": today, "commute_minutes": round(duration_min, 1)},
            )
            resp.raise_for_status()
            return True
    except Exception as exc:
        logger.warning("Commute upsert failed for %s: %s", user_id[:8], exc)
        return False


async def get_environment_dataframe(user_id: str, days: int = 90) -> pd.DataFrame:
    """Fetch this user's stored weather/commute history as a date-indexed DataFrame, for merging into the causal engine."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                _sb_url("environment_daily"),
                headers=_sb_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "entry_date": f"gte.{since}",
                    "select": "entry_date,rainfall_mm,temp_c,is_rainy,commute_minutes",
                },
            )
            resp.raise_for_status()
            rows = resp.json() or []
    except Exception as exc:
        logger.warning("Environment fetch failed for %s: %s", user_id[:8], exc)
        return pd.DataFrame()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).set_index("entry_date")
    df.index = pd.to_datetime(df.index)
    df = df.dropna(how="all")
    return df

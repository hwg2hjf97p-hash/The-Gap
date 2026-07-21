"""
Persistent storage for Apple Health data pushed from the mobile app.

This is the piece that was missing before: Apple Health data only ever
existed for the duration of one sync request, then was discarded — so
every subsequent OAuth-provider sync (Whoop, Oura, etc.) would overwrite
the results with no memory that Apple Health data existed at all, and
vice versa. Storing it here means _sync_user (daily_sync.py) can pull it
in and merge it with everything else on every sync, regardless of which
sync triggered the run.

Table DDL (run once in Supabase SQL editor):
  CREATE TABLE IF NOT EXISTS apple_health_daily (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    entry_date DATE NOT NULL,
    hrv NUMERIC,
    resting_hr NUMERIC,
    steps NUMERIC,
    sleep_total_min NUMERIC,
    sleep_deep_min NUMERIC,
    dietary_energy NUMERIC,
    protein_g NUMERIC,
    carbs_g NUMERIC,
    fat_g NUMERIC,
    active_energy NUMERIC,
    vo2max NUMERIC,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, entry_date)
  );

  -- If the table already exists from before nutrition support was added:
  ALTER TABLE apple_health_daily ADD COLUMN IF NOT EXISTS dietary_energy NUMERIC;
  ALTER TABLE apple_health_daily ADD COLUMN IF NOT EXISTS protein_g NUMERIC;
  ALTER TABLE apple_health_daily ADD COLUMN IF NOT EXISTS carbs_g NUMERIC;
  ALTER TABLE apple_health_daily ADD COLUMN IF NOT EXISTS fat_g NUMERIC;

  -- New in this fix: deep sleep, active energy, VO2 max — previously
  -- collected nowhere at all, which permanently blocked 8 of the 34
  -- causal hypotheses for anyone relying on Apple Health alone.
  ALTER TABLE apple_health_daily ADD COLUMN IF NOT EXISTS sleep_deep_min NUMERIC;
  ALTER TABLE apple_health_daily ADD COLUMN IF NOT EXISTS active_energy NUMERIC;
  ALTER TABLE apple_health_daily ADD COLUMN IF NOT EXISTS vo2max NUMERIC;
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


async def upsert_apple_health_rows(user_id: str, daily_rows: dict[str, dict[str, float]]) -> None:
    """
    Saves each day's Apple Health data permanently, keyed by (user_id, date).
    A later sync for the same date overwrites that date's row rather than
    duplicating it.
    """
    if not daily_rows:
        return

    payload = [
        {
            "user_id": user_id,
            "entry_date": date,
            "hrv": values.get("hrv"),
            "resting_hr": values.get("resting_hr"),
            "steps": values.get("steps"),
            "sleep_total_min": values.get("sleep_total_min"),
            "sleep_deep_min": values.get("sleep_deep_min"),
            "dietary_energy": values.get("dietary_energy"),
            "protein_g": values.get("protein_g"),
            "carbs_g": values.get("carbs_g"),
            "fat_g": values.get("fat_g"),
            "active_energy": values.get("active_energy"),
            "vo2max": values.get("vo2max"),
        }
        for date, values in daily_rows.items()
    ]

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                _sb_url("apple_health_daily"),
                headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                params={"on_conflict": "user_id,entry_date"},
                json=payload,
            )
            resp.raise_for_status()
    except Exception as exc:
        # Non-fatal by design: even if persistent storage fails, the sync
        # that's about to run can still use this same data for right now —
        # it just won't be remembered for next time.
        logger.warning("Apple Health upsert failed (continuing anyway): %s", exc)


async def get_apple_health_dataframe(user_id: str, days: int = 90) -> pd.DataFrame:
    """Fetch this user's stored Apple Health history as a date-indexed DataFrame."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                _sb_url("apple_health_daily"),
                headers=_sb_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "entry_date": f"gte.{since}",
                    "select": "entry_date,hrv,resting_hr,steps,sleep_total_min,sleep_deep_min,dietary_energy,protein_g,carbs_g,fat_g,active_energy,vo2max",
                },
            )
            resp.raise_for_status()
            rows = resp.json() or []
    except Exception as exc:
        logger.warning("Apple Health fetch failed (continuing without it): %s", exc)
        return pd.DataFrame()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).set_index("entry_date")
    df.index = pd.to_datetime(df.index)
    df = df.dropna(how="all")  # drop rows where every metric is null
    return df

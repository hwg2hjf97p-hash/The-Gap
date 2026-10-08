"""
Weight logged by hand in the app (table weight_log, see phase9.sql), as a
daily table the sync can merge with every other source.
"""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta

import httpx
import pandas as pd

logger = logging.getLogger(__name__)


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers() -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


async def get_weight_dataframe(user_id: str, days: int = 400) -> pd.DataFrame:
    """The person's logged weights as a date-indexed frame with one column, weight_kg (empty when none)."""
    since = (date.today() - timedelta(days=days)).isoformat()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                _sb_url("weight_log"),
                headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "local_date": f"gte.{since}", "select": "local_date,weight_kg", "order": "local_date.asc"},
            )
            resp.raise_for_status()
            rows = resp.json() or []
    except Exception as exc:
        logger.info("Weight log fetch failed for %s (continuing without it): %s", user_id[:8], exc)
        return pd.DataFrame()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["local_date"] = pd.to_datetime(df["local_date"])
    df["weight_kg"] = pd.to_numeric(df["weight_kg"], errors="coerce")
    return df.set_index("local_date").sort_index()[["weight_kg"]].dropna()

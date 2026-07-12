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

WHOOP_API_BASE = "https://api.prod.whoop.com/developer/v2"
# NOTE: Whoop fully deprecated the v1 data API (Oct 2025) — v1 endpoints now 404.
# v2 uses the same general shape but with a few renamed fields (noted below).


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


async def _get_whoop_paginated(
    client: httpx.AsyncClient,
    endpoint: str,
    headers: dict,
    start: str,
    max_pages: int = 20,
) -> list[dict]:
    """
    Fetch every page of a Whoop v2 collection endpoint.
    Whoop's real max `limit` is 25, not the 200 this code used to send —
    sending 200 gets flatly rejected with 400 Bad Request. This pages
    through with next_token until Whoop stops returning one.

    Returns [] on failure instead of raising, so a problem with one data
    type (e.g. a missing scope causing 401 on just this endpoint) doesn't
    discard every other data type that already fetched successfully.
    """
    records: list[dict] = []
    params = {"start": start, "limit": 25}
    try:
        for _ in range(max_pages):
            resp = await client.get(f"{WHOOP_API_BASE}/{endpoint}", headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
            records.extend(data.get("records", []))
            next_token = data.get("next_token")
            if not next_token:
                break
            params = {"start": start, "limit": 25, "next_token": next_token}
    except Exception as exc:
        logger.warning("Whoop endpoint %s failed (continuing without it): %s", endpoint, exc)
        return records  # return whatever pages succeeded before the failure, if any
    return records


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
        recovery_records = await _get_whoop_paginated(client, "recovery", headers, start)
        sleep_records = await _get_whoop_paginated(client, "activity/sleep", headers, start)
        cycle_records = await _get_whoop_paginated(client, "cycle", headers, start)

    # Build daily rows
    rows: dict[str, dict] = {}

    # score_state can be "SCORED" / "PENDING_SCORE" / "UNSCORABLE" in v2 —
    # only "SCORED" records are guaranteed to have a populated `score` object.
    for r in recovery_records:
        if r.get("score_state") != "SCORED":
            continue
        date = r.get("created_at", "")[:10]
        score = r.get("score", {}) or {}
        # v2 renamed hrv_rmssd_on_wakeup -> hrv_rmssd_milli (units unchanged: ms)
        rows.setdefault(date, {})["hrv"] = score.get("hrv_rmssd_milli")
        rows[date]["resting_hr"] = score.get("resting_heart_rate")
        rows[date]["recovery_score"] = score.get("recovery_score")

    for s in sleep_records:
        if s.get("score_state") != "SCORED":
            continue
        date = s.get("start", "")[:10]
        score = s.get("score", {}) or {}
        stage_summary = score.get("stage_summary", {}) or {}
        rows.setdefault(date, {})
        total_ms = stage_summary.get("total_in_bed_time_milli", 0) or 0
        # v2 renamed slow_wave_sleep_duration_milli -> total_slow_wave_sleep_time_milli
        deep_ms = stage_summary.get("total_slow_wave_sleep_time_milli", 0) or 0
        rows[date]["sleep_total_min"] = total_ms / 60000
        rows[date]["sleep_deep_min"] = deep_ms / 60000
        rows[date]["sleep_score"] = score.get("sleep_performance_percentage")

    for c in cycle_records:
        if c.get("score_state") != "SCORED":
            continue
        date = c.get("start", "")[:10]
        score = c.get("score", {}) or {}
        rows.setdefault(date, {})
        # Whoop's Cycle score has never included step_count in either v1 or v2 —
        # it only exposes strain/kilojoule/heart-rate. Deliberately NOT setting a
        # "steps" key here (rather than None/0) so that parsers/whoop.py's
        # existing active_energy-based estimate still fires — that fallback only
        # triggers when "steps" isn't already a column.
        active_kj = score.get("kilojoule") or 0
        rows[date]["active_energy"] = active_kj * 0.239 if active_kj else 0  # kJ → kcal

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

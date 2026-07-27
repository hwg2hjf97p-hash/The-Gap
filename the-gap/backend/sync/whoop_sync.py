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
        return _dedupe_by_id(records)  # return whatever pages succeeded before the failure, if any
    return _dedupe_by_id(records)


def _dedupe_by_id(records: list[dict]) -> list[dict]:
    """
    REAL BUG FIXED HERE: production logs showed Whoop returning the exact
    same sleep record twice for every single night — confirmed by nearly
    identical stage_summary totals across many different dates, not
    genuinely different sleep periods. Whether this comes from an overlap
    at our pagination page boundaries or a quirk in Whoop's own API, every
    Whoop record has a unique "id" — deduplicating by it is correct
    regardless of the exact mechanism, and safe even if duplication never
    happens for a given user (a no-op in that case).
    """
    seen: set[str] = set()
    deduped: list[dict] = []
    for r in records:
        rid = r.get("id")
        if rid is not None and rid in seen:
            continue
        if rid is not None:
            seen.add(rid)
        deduped.append(r)
    return deduped


async def fetch_whoop_data(
    access_token: str,
    days_back: int = 180,
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

    logger.info(
        "Whoop raw records: recovery=%d sleep=%d cycle=%d",
        len(recovery_records), len(sleep_records), len(cycle_records),
    )
    scored_counts = {"recovery": 0, "sleep": 0, "cycle": 0}

    # Build daily rows
    rows: dict[str, dict] = {}

    # score_state can be "SCORED" / "PENDING_SCORE" / "UNSCORABLE" in v2 —
    # only "SCORED" records are guaranteed to have a populated `score` object.
    for r in recovery_records:
        if r.get("score_state") != "SCORED":
            continue
        scored_counts["recovery"] += 1
        date = r.get("created_at", "")[:10]
        score = r.get("score", {}) or {}
        # v2 renamed hrv_rmssd_on_wakeup -> hrv_rmssd_milli (units unchanged: ms)
        rows.setdefault(date, {})["hrv"] = score.get("hrv_rmssd_milli")
        rows[date]["resting_hr"] = score.get("resting_heart_rate")
        rows[date]["recovery_score"] = score.get("recovery_score")

    for s in sleep_records:
        if s.get("score_state") != "SCORED":
            continue
        # Naps come back as separate sleep records from Whoop's API (each
        # with its own "nap" boolean) — skip them so they can't overwrite
        # or distort the main overnight sleep number.
        if s.get("nap"):
            continue
        scored_counts["sleep"] += 1
        date = s.get("start", "")[:10]
        score = s.get("score", {}) or {}
        stage_summary = score.get("stage_summary", {}) or {}
        rows.setdefault(date, {})
        if "sleep_total_min" in rows[date]:
            # More than one non-nap sleep record for the same date — log
            # it so we have real evidence next time, rather than guessing
            # at the mechanism again. Currently just keeps the later
            # record (see note below), but this tells us whether that's
            # actually the right call or whether these should be summed.
            logger.warning(
                "Whoop: multiple non-nap sleep records for date=%s — "
                "previous sleep_total_min=%.1f, new stage_summary=%s",
                date, rows[date]["sleep_total_min"], stage_summary,
            )
        # total_in_bed_time_milli includes time spent lying awake — not
        # actual sleep duration, and larger than what Whoop's own app
        # shows as your sleep number. Actual asleep time is the sum of
        # the three real sleep stages instead.
        light_ms = stage_summary.get("total_light_sleep_time_milli", 0) or 0
        # v2 renamed slow_wave_sleep_duration_milli -> total_slow_wave_sleep_time_milli
        deep_ms = stage_summary.get("total_slow_wave_sleep_time_milli", 0) or 0
        rem_ms = stage_summary.get("total_rem_sleep_time_milli", 0) or 0
        asleep_ms = light_ms + deep_ms + rem_ms
        # REVERTED to overwrite, not sum: an earlier version of this fix
        # summed non-nap records sharing a date, meant to handle the rare
        # case of Whoop splitting one night into two records. That
        # produced a demonstrated, clearly wrong result (an ~169 hour
        # single-night reading) for at least one real user — the exact
        # mechanism isn't confirmed yet without production logs showing
        # the raw record count per date, so this reverts to the safer,
        # previously-working behavior (last record seen wins) rather
        # than ship a second guess. Worth revisiting properly once we
        # can see how many non-nap records Whoop actually returns per
        # date for a real affected account.
        rows[date]["sleep_total_min"] = asleep_ms / 60000
        rows[date]["sleep_deep_min"] = deep_ms / 60000
        rows[date]["sleep_score"] = score.get("sleep_performance_percentage")

    for c in cycle_records:
        if c.get("score_state") != "SCORED":
            continue
        scored_counts["cycle"] += 1
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

    logger.info(
        "Whoop sync: %d distinct days | scored: recovery=%d sleep=%d cycle=%d (of %d/%d/%d raw)",
        len(df), scored_counts["recovery"], scored_counts["sleep"], scored_counts["cycle"],
        len(recovery_records), len(sleep_records), len(cycle_records),
    )
    return df

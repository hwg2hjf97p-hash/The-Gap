"""
Quick Entry — lightweight, high-frequency journaling for The Gap.

Deliberately NOT a daily journal. The product bet: people forget small
things (a bad call, poor sleep from noise, an argument, travel) if asked
to reflect once at end of day. Quick Entry is built to encourage many
short notes logged in the moment, which then get summarized by an LLM
into structured daily signals for the causal engine.

Table DDL (run once in Supabase SQL editor):
  CREATE TABLE IF NOT EXISTS quick_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    entry_text TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
  );
  CREATE INDEX IF NOT EXISTS idx_quick_entries_user_date
    ON quick_entries (user_id, created_at);
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from utils.journal_extract import extract_daily_signals

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/journal", tags=["journal"])

MAX_ENTRY_LENGTH = 280  # deliberately short — a quick moment, not an essay


# ── Supabase REST helpers (same direct-REST pattern used elsewhere) ─────────

def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


# ── Request / Response models ────────────────────────────────────────────────

class QuickEntryRequest(BaseModel):
    user_id: str
    text: str = Field(..., min_length=1, max_length=MAX_ENTRY_LENGTH)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/entry")
async def create_entry(body: QuickEntryRequest) -> JSONResponse:
    """Log one quick entry. Each submission is its own row — no editing a running draft."""
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Entry can't be empty.")

    payload = {"user_id": body.user_id, "entry_text": text}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _sb_url("quick_entries"),
                headers=_sb_headers(prefer="return=minimal"),
                json=payload,
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.error("Quick entry save failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save entry.")

    count_today = await _count_today(body.user_id)
    streak = await _get_streak(body.user_id)

    return JSONResponse(content={"success": True, "count_today": count_today, "streak": streak})


@router.get("/{user_id}/today")
async def get_today_entries(user_id: str) -> JSONResponse:
    """List today's entries — shown as a running list above the input box."""
    start = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _sb_url("quick_entries"),
                headers=_sb_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "created_at": f"gte.{start}",
                    "select": "id,entry_text,created_at",
                    "order": "created_at.asc",
                },
            )
            resp.raise_for_status()
            return JSONResponse(content={"entries": resp.json() or []})
    except Exception as exc:
        logger.error("Quick entry fetch failed: %s", exc)
        return JSONResponse(content={"entries": []})


@router.get("/{user_id}/streak")
async def get_streak_endpoint(user_id: str) -> JSONResponse:
    streak = await _get_streak(user_id)
    return JSONResponse(content={"streak": streak})


async def _count_today(user_id: str) -> int:
    start = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _sb_url("quick_entries"),
                headers=_sb_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "created_at": f"gte.{start}",
                    "select": "id",
                },
            )
            resp.raise_for_status()
            return len(resp.json() or [])
    except Exception:
        return 0


async def _get_streak(user_id: str) -> int:
    """Consecutive days with at least one quick entry — same idea as the check-in streak."""
    since = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _sb_url("quick_entries"),
                headers=_sb_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "created_at": f"gte.{since}",
                    "select": "created_at",
                    "order": "created_at.desc",
                },
            )
            resp.raise_for_status()
            rows = resp.json() or []

        dates = sorted(
            {datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")).date() for r in rows},
            reverse=True,
        )
        if not dates:
            return 0

        today = datetime.now(timezone.utc).date()
        expected = today if dates[0] == today else today - timedelta(days=1)
        if dates[0] not in (today, today - timedelta(days=1)):
            return 0

        streak = 0
        for d in dates:
            if d == expected:
                streak += 1
                expected = expected - timedelta(days=1)
            else:
                break
        return streak
    except Exception:
        return 0


async def get_journal_dataframe(user_id: str, days: int = 90) -> pd.DataFrame:
    """
    Fetch quick entries for the last N days, group by date, run each day's
    entries through the LLM extractor, and return a date-indexed DataFrame
    ready to merge into the main health DataFrame.

    Days with no entries simply don't appear as rows — this merges via a
    left-join elsewhere, so missing days correctly stay NaN rather than
    being assumed to be "no stress" etc.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                _sb_url("quick_entries"),
                headers=_sb_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "created_at": f"gte.{since}",
                    "select": "entry_text,created_at",
                    "order": "created_at.asc",
                },
            )
            resp.raise_for_status()
            rows = resp.json() or []
    except Exception as exc:
        logger.error("Journal dataframe fetch failed: %s", exc)
        return pd.DataFrame()

    if not rows:
        return pd.DataFrame()

    # Group entries by calendar date
    by_date: dict[str, list[str]] = {}
    for r in rows:
        d = r["created_at"][:10]
        by_date.setdefault(d, []).append(r["entry_text"])

    records = {}
    for d, entries in by_date.items():
        signals = await extract_daily_signals(entries)
        if signals is not None:
            signals.pop("summary", None)  # not a numeric feature — display-only, not for the engine
            records[d] = signals

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame.from_dict(records, orient="index")
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    return df

"""
Browse a past day's log — what you actually typed/tracked that day, not a
re-run of the causal engine (a confirmed insight is stable over a 30-180
day window, so there's no meaningful "insight for Tuesday"; what changes
day to day is your own logged data). Reuses the three already-per-day-
indexed tables directly rather than touching the sync pipeline at all.
"""

from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from auth import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/history", tags=["history"])


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers() -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


@router.get("/{date}")
async def get_day_history(date: str, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    """date is a YYYY-MM-DD string — the device's own local date, same
    convention used everywhere else in this app (see journal.py/checkin.py's
    local_date handling)."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            entries_resp = await client.get(
                _sb_url("quick_entries"),
                headers=_sb_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "local_date": f"eq.{date}",
                    "select": "entry_text,created_at",
                    "order": "created_at.asc",
                },
            )
            checkin_resp = await client.get(
                _sb_url("daily_checkins"),
                headers=_sb_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "date": f"eq.{date}",
                    "select": "alcohol,afternoon_caffeine,stress_score,notes",
                    "limit": "1",
                },
            )
            extracted_resp = await client.get(
                _sb_url("journal_extractions"),
                headers=_sb_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "entry_date": f"eq.{date}",
                    "select": "mood_score,stress_event,travel_event,illness_event,conflict_event,big_win_event,summary",
                    "limit": "1",
                },
            )
            entries_resp.raise_for_status()
            checkin_resp.raise_for_status()
            extracted_resp.raise_for_status()

            entries = entries_resp.json() or []
            checkin_rows = checkin_resp.json() or []
            extracted_rows = extracted_resp.json() or []
    except Exception as exc:
        logger.error("History fetch failed for %s on %s: %s", user_id[:8], date, exc)
        raise HTTPException(status_code=500, detail="Couldn't load that day — please try again.")

    return JSONResponse(content={
        "date": date,
        "entries": entries,
        "checkin": checkin_rows[0] if checkin_rows else None,
        "extracted": extracted_rows[0] if extracted_rows else None,
    })

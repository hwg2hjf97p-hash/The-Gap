"""
Weekly insight digest — a Sunday recap so there's a reason to open the app
even on a week where nothing dramatic happened. Reuses the same data every
other screen already reads (latest saved results, journal streak) rather
than re-running the causal engine.

Table DDL (run once in Supabase SQL editor):
  CREATE TABLE IF NOT EXISTS weekly_digests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    week_start DATE NOT NULL,
    digest_text TEXT NOT NULL,
    confirmed_count INTEGER NOT NULL DEFAULT 0,
    in_progress_count INTEGER NOT NULL DEFAULT 0,
    streak INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, week_start)
  );

Called weekly by the same scheduled GitHub Action that drives /sync/run
(see .github/workflows/scheduled-sync.yml in the repo root), protected by
the same SYNC_SECRET.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse

from auth import get_current_user_id
from db.supabase_client import get_latest_results
from routers.journal import _get_streak as _get_journal_streak
from utils.push import send_push

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/digest", tags=["digest"])

SYNC_SECRET = os.getenv("SYNC_SECRET", "")


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


async def _supabase_get(table: str, params: dict) -> list[dict]:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(_sb_url(table), headers=_sb_headers(), params=params)
        resp.raise_for_status()
        return resp.json() or []


def _build_digest_text(confirmed_count: int, in_progress_count: int, streak: int) -> str:
    parts = []
    if confirmed_count > 0:
        parts.append(f"{confirmed_count} confirmed pattern{'s' if confirmed_count != 1 else ''} running on you right now")
    else:
        parts.append("no confirmed patterns yet — keep logging, they take a few weeks to show up")
    if in_progress_count > 0:
        parts.append(f"{in_progress_count} more still gathering data")
    if streak > 0:
        parts.append(f"a {streak}-day streak")
    return "This week: " + ", ".join(parts) + "."


async def _run_one_digest(user_id: str) -> dict:
    latest = get_latest_results(user_id)
    if not latest:
        return {"user_id": user_id, "status": "no_data"}

    insights = latest.get("insights") or []
    experiments = latest.get("experiments") or []
    confirmed_count = len(insights)
    in_progress_count = len(experiments)
    streak = await _get_journal_streak(user_id)

    digest_text = _build_digest_text(confirmed_count, in_progress_count, streak)
    week_start = (datetime.now(timezone.utc).date() - timedelta(days=datetime.now(timezone.utc).weekday())).isoformat()

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _sb_url("weekly_digests"),
                headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                params={"on_conflict": "user_id,week_start"},
                json=[{
                    "user_id": user_id,
                    "week_start": week_start,
                    "digest_text": digest_text,
                    "confirmed_count": confirmed_count,
                    "in_progress_count": in_progress_count,
                    "streak": streak,
                }],
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.error("Saving weekly digest failed for %s: %s", user_id[:8], exc)
        return {"user_id": user_id, "status": "save_failed"}

    await send_push(user_id, title="Your weekly recap is ready", body=digest_text, data={"kind": "digest"})

    return {"user_id": user_id, "status": "sent"}


@router.post("/run")
async def run_weekly_digest(x_sync_secret: str = Header(default="")):
    """Generate + push this week's digest for every user with at least one saved result."""
    if SYNC_SECRET and x_sync_secret != SYNC_SECRET:
        raise HTTPException(status_code=403, detail="Invalid sync secret.")

    try:
        rows = await _supabase_get("results", {"select": "user_id"})
    except Exception as exc:
        logger.error("Failed to fetch users for digest run: %s", exc)
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}")

    user_ids = sorted({r["user_id"] for r in rows if r.get("user_id")})
    logger.info("Weekly digest: %d users", len(user_ids))

    results = [await _run_one_digest(uid) for uid in user_ids]

    return JSONResponse(content={
        "processed_users": len(results),
        "results": results,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@router.get("/latest")
async def get_latest_digest(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        rows = await _supabase_get(
            "weekly_digests",
            {
                "user_id": f"eq.{user_id}",
                "select": "week_start,digest_text,confirmed_count,in_progress_count,streak,created_at",
                "order": "week_start.desc",
                "limit": "1",
            },
        )
        return JSONResponse(content={"digest": rows[0] if rows else None})
    except Exception as exc:
        logger.error("Fetching latest digest failed for %s: %s", user_id[:8], exc)
        return JSONResponse(content={"digest": None})

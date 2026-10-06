"""
Notification preferences: the person's time zone and quiet hours, so pushes
from the server (discoveries, follow-ups, the weekly review) wait until
they're awake instead of arriving at 3 am. See utils/push.py for how they're used.

Table DDL (run once in the Supabase SQL editor — see phase6.sql):
  CREATE TABLE IF NOT EXISTS notification_prefs (
    user_id TEXT PRIMARY KEY,
    tz TEXT NOT NULL,
    quiet_start NUMERIC NOT NULL DEFAULT 22,
    quiet_end NUMERIC NOT NULL DEFAULT 7,
    updated_at TIMESTAMPTZ DEFAULT NOW()
  );
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from auth import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notifications", tags=["notifications"])


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


class PrefsBody(BaseModel):
    tz: str = Field(min_length=1, max_length=64)  # an IANA name such as "Australia/Brisbane"
    quiet_start: float = Field(ge=0, lt=24)
    quiet_end: float = Field(ge=0, lt=24)


@router.get("/prefs")
async def get_prefs(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _sb_url("notification_prefs"), headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "select": "tz,quiet_start,quiet_end", "limit": "1"},
            )
            resp.raise_for_status()
            rows = resp.json() or []
    except Exception as exc:
        logger.warning("Loading notification prefs failed for %s: %s", user_id[:8], exc)
        return JSONResponse(content={"prefs": None})
    return JSONResponse(content={"prefs": rows[0] if rows else None})


@router.put("/prefs")
async def put_prefs(body: PrefsBody, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        ZoneInfo(body.tz)
    except Exception:
        raise HTTPException(status_code=400, detail="That isn't a known time zone.")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _sb_url("notification_prefs"),
                headers=_sb_headers("resolution=merge-duplicates,return=minimal"),
                params={"on_conflict": "user_id"},
                json={
                    "user_id": user_id, "tz": body.tz, "quiet_start": body.quiet_start,
                    "quiet_end": body.quiet_end, "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.error("Saving notification prefs failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Couldn't save your notification settings.")
    return JSONResponse(content={"prefs": {"tz": body.tz, "quiet_start": body.quiet_start, "quiet_end": body.quiet_end}})

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
from typing import Optional
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from auth import get_current_user_id
from utils.push import PUSH_SWITCHES

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
    # Which notifications from The Gap this person has switched on (utils/push.py PUSH_SWITCHES). Only the ones sent
    # are changed; the rest keep what they had. Everything is off until the person turns it on.
    kinds: Optional[dict[str, bool]] = None


def merged_kinds(existing: Optional[dict], changes: dict[str, bool]) -> dict[str, bool]:
    """The saved switches with these changes applied. Unknown names are an error, so a typo can't quietly do nothing."""
    unknown = sorted(set(changes) - set(PUSH_SWITCHES))
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown notification switch: {', '.join(unknown)}.")
    out = {name: bool((existing or {}).get(name)) for name in PUSH_SWITCHES}
    out.update({name: bool(value) for name, value in changes.items()})
    return out


@router.get("/prefs")
async def get_prefs(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        row = await load_prefs(user_id)
    except Exception as exc:
        logger.warning("Loading notification prefs failed for %s: %s", user_id[:8], exc)
        return JSONResponse(content={"prefs": None, "kinds": {name: False for name in PUSH_SWITCHES}})
    kinds = merged_kinds((row or {}).get("push_kinds"), {})
    return JSONResponse(content={"prefs": ({k: v for k, v in row.items() if k != "push_kinds"} if row else None), "kinds": kinds})


async def load_prefs(user_id: str) -> Optional[dict]:
    """This person's saved row, with the push switches when phase29.sql has been run (without them when it hasn't)."""
    async with httpx.AsyncClient(timeout=10) as client:
        for select in ("tz,quiet_start,quiet_end,push_kinds", "tz,quiet_start,quiet_end"):
            resp = await client.get(
                _sb_url("notification_prefs"), headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "select": select, "limit": "1"},
            )
            if resp.status_code == 400 and "push_kinds" in select:
                continue
            resp.raise_for_status()
            rows = resp.json() or []
            return rows[0] if rows else None
    return None


@router.put("/prefs")
async def put_prefs(body: PrefsBody, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        ZoneInfo(body.tz)
    except Exception:
        raise HTTPException(status_code=400, detail="That isn't a known time zone.")
    row = {
        "user_id": user_id, "tz": body.tz, "quiet_start": body.quiet_start,
        "quiet_end": body.quiet_end, "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    kinds: Optional[dict[str, bool]] = None
    if body.kinds is not None:
        try:
            existing = await load_prefs(user_id)
        except Exception:
            existing = None
        kinds = merged_kinds((existing or {}).get("push_kinds"), body.kinds)
        row["push_kinds"] = kinds  # type: ignore[assignment]
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _sb_url("notification_prefs"),
                headers=_sb_headers("resolution=merge-duplicates,return=minimal"),
                params={"on_conflict": "user_id"},
                json=row,
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.error("Saving notification prefs failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Couldn't save your notification settings.")
    return JSONResponse(content={"prefs": {"tz": body.tz, "quiet_start": body.quiet_start, "quiet_end": body.quiet_end}, "kinds": kinds})

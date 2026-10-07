"""
Which source each kind of reading comes from, when several are connected.

  GET /sources  -> what's connected, which sources can supply each group of
                   readings, the person's choices, and the defaults
  PUT /sources  -> save the choices (applied on the next sync)

The merge itself lives in utils/source_merge.py.

Table DDL (run once in the Supabase SQL editor — see phase7.sql):
  CREATE TABLE IF NOT EXISTS source_prefs (
    user_id TEXT PRIMARY KEY,
    prefs JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ DEFAULT NOW()
  );
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from auth import get_current_user_id
from utils.source_merge import (
    DEFAULT_FILL_GAPS,
    DEFAULT_PRIORITY,
    GROUP_LABELS,
    GROUPS,
    SOURCE_LABELS,
    load_source_prefs,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sources", tags=["sources"])

# Which sources can supply each group at all.
# Only sources that really report that reading (checked against each sync file): Whoop has no steps,
# Strava shares workouts and training load only, and Apple Health has no weight here.
CAN_SUPPLY = {
    "sleep": ["whoop", "oura", "withings", "polar", "apple_health"],
    "recovery": ["whoop", "oura", "withings", "polar", "apple_health"],
    "activity": ["apple_health", "oura"],
    "energy": ["apple_health", "whoop", "oura"],
    "body": ["withings"],
}


def group_notes(key: str, available: list[str]) -> list[str]:
    """Short explanations for a group, based on what the person has connected."""
    notes: list[str] = []
    if key == "activity":
        if "whoop" in available:
            notes.append("Whoop doesn't record or share steps, so it can't be used for this.")
        if "strava" in available:
            notes.append("Strava shares your workouts and training load (used automatically), not steps.")
    if key == "energy" and "whoop" in available:
        notes.append("Whoop reports the calories you burn over the whole day, so its number reads higher than active calories from Apple Health. When sources are mixed it is lined up with your main one, so your trend doesn't jump.")
    return notes


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


async def _available_sources(user_id: str) -> list[str]:
    """Connected services, plus Apple Health if it has sent any data."""
    available: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            conns = await client.get(
                _sb_url("user_connections"), headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "is_active": "eq.true", "select": "provider"},
            )
            conns.raise_for_status()
            available = [c["provider"] for c in (conns.json() or []) if c.get("provider") in SOURCE_LABELS]
            apple = await client.get(
                _sb_url("apple_health_daily"), headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "select": "entry_date", "limit": "1"},
            )
            apple.raise_for_status()
            if apple.json():
                available.append("apple_health")
    except Exception as exc:
        logger.warning("Listing available sources failed for %s: %s", user_id[:8], exc)
    return available


class SourcePrefsBody(BaseModel):
    primary: dict[str, str] = Field(default_factory=dict)
    fill_gaps: dict[str, bool] = Field(default_factory=dict)


@router.get("")
async def get_sources(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    available = await _available_sources(user_id)
    prefs = await load_source_prefs(user_id) or {}
    primary = prefs.get("primary") or {}
    fill = {**DEFAULT_FILL_GAPS, **(prefs.get("fill_gaps") or {})}

    groups = []
    for key in GROUPS:
        options = [s for s in CAN_SUPPLY[key] if s in available]
        # What is used right now: the saved choice if it's still available, else the default order's first.
        default_first = next((s for s in DEFAULT_PRIORITY[key] if s in options), None)
        chosen = primary.get(key) if primary.get(key) in options else None
        groups.append({
            "key": key,
            "label": GROUP_LABELS[key],
            "options": [{"id": s, "label": SOURCE_LABELS[s]} for s in options],
            "chosen": chosen,
            "in_use": chosen or default_first,
            "fill_gaps": bool(fill[key]),
            "notes": group_notes(key, available),
        })
    return JSONResponse(content={"groups": groups})


@router.put("")
async def put_sources(body: SourcePrefsBody, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    for key, source in body.primary.items():
        if key not in GROUPS or source not in SOURCE_LABELS:
            raise HTTPException(status_code=400, detail="Unknown reading group or source.")
    for key in body.fill_gaps:
        if key not in GROUPS:
            raise HTTPException(status_code=400, detail="Unknown reading group.")
    # Keep anything else stored in the row (e.g. the sample-data flag); only the two settings change.
    existing = dict(await load_source_prefs(user_id) or {})
    existing["primary"] = body.primary
    existing["fill_gaps"] = body.fill_gaps
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _sb_url("source_prefs"),
                headers=_sb_headers("resolution=merge-duplicates,return=minimal"),
                params={"on_conflict": "user_id"},
                json={
                    "user_id": user_id,
                    "prefs": existing,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.error("Saving source preferences failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Couldn't save your choices. Please try again.")
    return JSONResponse(content={"saved": True})

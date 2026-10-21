"""
Heads-ups: short coach-style messages from today's numbers (see utils/headsups.py).

  GET  /headsups/today          today's, for the cards in the app
  POST /headsups/{id}/dismiss   hide one
  GET  /headsups/prefs          is the person getting them
  PUT  /headsups/prefs          switch them on or off
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth import get_current_user_id
from db.supabase_client import get_latest_results
from utils.headsups import _save, _sb_headers, _sb_url, apply_live, headsups_enabled, live_cards, local_day_and_hour
from utils.local_time import DEFAULT_TZ

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/headsups", tags=["headsups"])

MAX_CARDS = 3


@router.get("/today")
async def today(live_steps: Optional[float] = None, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    if not await headsups_enabled(user_id):
        return JSONResponse(content={"headsups": []})
    day, hour = await local_day_and_hour(user_id)
    # Water and protein are checked against what's logged right now, so logging something makes the card go away.
    insights: list[dict] = []
    if live_steps is not None:
        try:
            insights = ((await asyncio.to_thread(get_latest_results, user_id)) or {}).get("insights") or []
        except Exception as exc:
            logger.info("Latest insights for live heads-ups unavailable (%s)", exc)
    steps_source = ""
    if live_steps is not None:
        from routers.sources import activity_source

        key, label = await activity_source(user_id)
        steps_source = label if key and key != "apple_health" else ""
    live, checked = await live_cards(user_id, day, hour, live_steps, insights, steps_source)
    if live:
        try:
            await _save(user_id, day.isoformat(), list(live.values()))  # a card that has only just become true
        except Exception as exc:
            logger.warning("Saving live heads-ups failed for %s: %s", user_id[:8], exc)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _sb_url("headsups"), headers=_sb_headers(),
                params={
                    "user_id": f"eq.{user_id}", "headsup_date": f"eq.{day.isoformat()}", "dismissed_at": "is.null",
                    "select": "id,kind,title,body,tone,priority", "order": "priority.desc",
                },
            )
            resp.raise_for_status()
            rows = resp.json() or []
    except Exception as exc:
        logger.warning("Loading heads-ups failed for %s: %s", user_id[:8], exc)
        rows = []
    return JSONResponse(content={"headsups": apply_live(rows, live, checked)[:MAX_CARDS]})


@router.post("/{headsup_id}/dismiss")
async def dismiss(headsup_id: str, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    from datetime import datetime, timezone

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.patch(
                _sb_url("headsups"), headers=_sb_headers("return=minimal"),
                params={"id": f"eq.{headsup_id}", "user_id": f"eq.{user_id}"},
                json={"dismissed_at": datetime.now(timezone.utc).isoformat()},
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("Dismissing a heads-up failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Couldn't hide that. Please try again.")
    return JSONResponse(content={"success": True})


class PrefsBody(BaseModel):
    enabled: bool


@router.get("/prefs")
async def get_prefs(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    return JSONResponse(content={"enabled": await headsups_enabled(user_id)})


@router.put("/prefs")
async def put_prefs(body: PrefsBody, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.patch(
                _sb_url("notification_prefs"), headers=_sb_headers("return=representation"),
                params={"user_id": f"eq.{user_id}"}, json={"headsups_enabled": body.enabled},
            )
            resp.raise_for_status()
            updated = resp.json() or []
            if not updated:
                # No row yet (the app saves one at sign-in, but not necessarily before this): make it with the defaults.
                created = await client.post(
                    _sb_url("notification_prefs"), headers=_sb_headers("return=minimal"),
                    json={"user_id": user_id, "tz": DEFAULT_TZ, "headsups_enabled": body.enabled},
                )
                created.raise_for_status()
    except Exception as exc:
        logger.warning("Saving the heads-ups switch failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Couldn't save that. Please try again.")
    return JSONResponse(content={"enabled": body.enabled})

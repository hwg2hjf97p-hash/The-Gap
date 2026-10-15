"""
Heads-ups: short coach-style messages from today's numbers (see utils/headsups.py).

  GET  /headsups/today          today's, for the cards in the app
  POST /headsups/{id}/dismiss   hide one
  GET  /headsups/prefs          is the person getting them
  PUT  /headsups/prefs          switch them on or off
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth import get_current_user_id
from utils.headsups import _sb_headers, _sb_url, headsups_enabled
from utils.local_time import DEFAULT_TZ, user_today

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/headsups", tags=["headsups"])

MAX_CARDS = 3


@router.get("/today")
async def today(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    if not await headsups_enabled(user_id):
        return JSONResponse(content={"headsups": []})
    day = await user_today(user_id)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _sb_url("headsups"), headers=_sb_headers(),
                params={
                    "user_id": f"eq.{user_id}", "headsup_date": f"eq.{day.isoformat()}", "dismissed_at": "is.null",
                    "select": "id,kind,title,body,tone,priority", "order": "priority.desc", "limit": str(MAX_CARDS),
                },
            )
            resp.raise_for_status()
            rows = resp.json() or []
    except Exception as exc:
        logger.warning("Loading heads-ups failed for %s: %s", user_id[:8], exc)
        rows = []
    return JSONResponse(content={"headsups": rows})


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

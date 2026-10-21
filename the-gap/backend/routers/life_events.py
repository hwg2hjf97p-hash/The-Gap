"""
Life events: big changes a person adds about themselves (see utils/life_events.py).

  GET    /life-events        their events (newest first), each with what their readings did around it, and the list of types
  POST   /life-events        {"kind": "job_lost", "event_date": "2026-09-02", "note": "optional, short"}
  DELETE /life-events/{id}

Table DDL: see phase21.sql (life_events).
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth import get_current_user_id
from utils import life_events as le
from utils.local_time import user_today

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/life-events", tags=["life-events"])

CHANGES_CAVEAT = "A lot changes around big events, so this describes your readings, not what caused them."


class EventBody(BaseModel):
    kind: str
    event_date: str
    note: Optional[str] = None


def _kinds() -> list[dict]:
    return [{"key": key, "label": label} for key, label in le.KINDS.items()]


@router.get("")
async def list_my_events(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        events = await le.list_events(user_id)
    except Exception as exc:
        logger.warning("Loading life events failed for %s: %s", user_id[:8], exc)
        return JSONResponse(content={"events": [], "kinds": _kinds(), "caveat": CHANGES_CAVEAT, "available": False})
    today = await user_today(user_id)
    try:
        effects = await le.effects_for(user_id, events, today)
    except Exception as exc:
        logger.warning("Life event effects failed for %s: %s", user_id[:8], exc)
        effects = {}
    out = [{**e, "label": le.KINDS.get(e["kind"], "A big change"), "changes": effects.get(e["id"], [])} for e in events]
    return JSONResponse(content={"events": out, "kinds": _kinds(), "caveat": CHANGES_CAVEAT, "available": True})


@router.post("")
async def add_event(body: EventBody, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    today = await user_today(user_id)
    fields, problem = le.validate(body.kind, body.event_date, body.note, today)
    if problem or not fields:
        raise HTTPException(status_code=400, detail=problem or "Couldn't read that.")
    try:
        existing = await le.list_events(user_id)
        if len(existing) >= le.MAX_EVENTS:
            raise HTTPException(status_code=400, detail="That's a lot of events. Remove one you no longer need first.")
        if any(e["kind"] == fields["kind"] and e["event_date"] == fields["event_date"] for e in existing):
            raise HTTPException(status_code=409, detail="You've already added that one.")
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                le._sb_url("life_events"), headers=le._sb_headers("return=representation"), json={"user_id": user_id, **fields},
            )
            resp.raise_for_status()
            created = (resp.json() or [None])[0]
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Saving a life event failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Couldn't save that. Please try again.")
    return JSONResponse(content={"event": {**(created or fields), "label": le.KINDS[fields["kind"]], "changes": []}})


@router.delete("/{event_id}")
async def delete_event(event_id: str, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.delete(
                le._sb_url("life_events"), headers=le._sb_headers("return=minimal"),
                params={"id": f"eq.{event_id}", "user_id": f"eq.{user_id}"},
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.error("Deleting a life event failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Couldn't remove that. Please try again.")
    return JSONResponse(content={"success": True})

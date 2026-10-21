"""
Training settings that follow the person from phone to phone: their weekly workout target, the program they are on, and their
rest-timer choice.

  GET /training/state   {"exists": bool, "weekly_target": int|null, "active_program": {"id","startDate"}|null, "rest_pref": str|null}
  PUT /training/state   any of those fields (only the ones sent are changed; null clears one)

`exists` is false until the person has saved anything here, so the app can copy what it already kept on the phone up to the
server the first time, without a stale phone ever bringing back something cleared elsewhere.

Table DDL: see phase23.sql (training_state).
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from auth import get_current_user_id
from routers.suggestions import _sb_headers, _sb_url

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/training", tags=["training"])

REST_PREFS = {"auto", "off", "60", "90", "120", "180"}
PROGRAM_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
FIELDS = ("weekly_target", "active_program", "rest_pref")


class ProgramState(BaseModel):
    id: str = Field(..., max_length=40)
    startDate: str


class StateBody(BaseModel):
    weekly_target: Optional[int] = Field(default=None, ge=1, le=7)
    active_program: Optional[ProgramState] = None
    rest_pref: Optional[str] = None


def clean(fields: dict) -> tuple[Optional[dict], Optional[str]]:
    """(the values to save, None) or (None, what is wrong). Only the fields that were sent are in `fields`."""
    out: dict = {}
    if "weekly_target" in fields:
        value = fields["weekly_target"]
        if value is not None and not (isinstance(value, int) and 1 <= value <= 7):
            return None, "The weekly target is between 1 and 7."
        out["weekly_target"] = value
    if "rest_pref" in fields:
        value = fields["rest_pref"]
        if value is not None and value not in REST_PREFS:
            return None, "That rest timer choice isn't one of the options."
        out["rest_pref"] = value
    if "active_program" in fields:
        value = fields["active_program"]
        if value is not None:
            program_id, start = value.get("id", ""), value.get("startDate", "")
            if not PROGRAM_ID.match(program_id):
                return None, "That program isn't recognised."
            try:
                date.fromisoformat(start)
            except ValueError:
                return None, "The program's start date doesn't look right."
            value = {"id": program_id, "startDate": start}
        out["active_program"] = value
    return out, None


@router.get("/state")
async def get_state(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    empty = {"exists": False, "weekly_target": None, "active_program": None, "rest_pref": None}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _sb_url("training_state"), headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "select": ",".join(FIELDS), "limit": "1"},
            )
            resp.raise_for_status()
            rows = resp.json() or []
    except Exception as exc:
        logger.info("Training state unavailable for %s (%s)", user_id[:8], exc)
        return JSONResponse(content={**empty, "available": False})
    if not rows:
        return JSONResponse(content={**empty, "available": True})
    return JSONResponse(content={"exists": True, "available": True, **{k: rows[0].get(k) for k in FIELDS}})


@router.put("/state")
async def put_state(body: StateBody, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    dump = body.model_dump if hasattr(body, "model_dump") else body.dict  # pydantic 2 or 1
    values, problem = clean(dump(exclude_unset=True))
    if problem or values is None:
        raise HTTPException(status_code=400, detail=problem or "Couldn't read that.")
    payload = {"user_id": user_id, "updated_at": datetime.now(timezone.utc).isoformat(), **values}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                _sb_url("training_state"), headers=_sb_headers("resolution=merge-duplicates,return=minimal"),
                params={"on_conflict": "user_id"}, json=payload,
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("Saving training state failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=503, detail="Couldn't save that to your account. It's kept on this phone for now.")
    return JSONResponse(content={"saved": list(values)})

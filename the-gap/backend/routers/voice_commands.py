"""
"Your voice, your command": a person's own spoken shortcuts (see utils/voice_commands.py).

  GET    /voice-commands          their shortcuts, what already works (examples), what a shortcut can log, and the limit
  POST   /voice-commands          {"phrase": "big bottle", "kind": "water", "amount": 750}  (saved food or meal: add "ref_id")
  PATCH  /voice-commands/{id}     the same fields, to change one
  DELETE /voice-commands/{id}
  POST   /voice-commands/test     {"text": "drank my big bottle"}  what would be logged. Nothing is saved.

A shortcut applies everywhere words are sorted: Siri and the Shortcuts action, and typing or talking in Quick Entry.

Table DDL: see phase25.sql (voice_commands).
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from auth import get_current_user_id
from utils.log_router import parse_log
from utils.saved_logging import _sb_headers, _sb_url, load_saved
from utils.voice_commands import EXAMPLES, KINDS, MAX_COMMANDS, SAVED_KINDS, Problem, check_command, clean_phrase, describe, load_commands

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice-commands", tags=["voice-commands"])

SETUP_NEEDED = "Voice shortcuts aren't set up yet. Try again soon."


class CommandBody(BaseModel):
    phrase: str = Field(min_length=1, max_length=80)
    kind: str = Field(max_length=20)
    amount: float = 1
    ref_id: Optional[str] = Field(default=None, max_length=64)


class TestBody(BaseModel):
    text: str = Field(min_length=1, max_length=300)


def _shown(row: dict) -> dict:
    return {**row, "logs": describe(row)}


def _kinds() -> list[dict]:
    return [{"key": key, "label": label} for key, label in KINDS.items()]


async def _cleaned(user_id: str, body: CommandBody) -> dict:
    """The fields to store, or a 400 saying what to change."""
    try:
        phrase = clean_phrase(body.phrase)
        foods, meals = [], []
        if body.kind in SAVED_KINDS:
            async with httpx.AsyncClient(timeout=15) as client:
                foods, meals = await load_saved(client, user_id)
        return {"phrase": phrase, **check_command(body.kind, body.amount, body.ref_id, foods, meals)}
    except Problem as problem:
        raise HTTPException(status_code=400, detail=str(problem))


@router.get("")
async def list_commands(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    base = {"examples": EXAMPLES, "kinds": _kinds(), "limit": MAX_COMMANDS}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            rows = await load_commands(client, user_id, strict=True)
    except Exception as exc:
        logger.warning("Loading voice commands failed for %s: %s", user_id[:8], exc)
        return JSONResponse(content={**base, "commands": [], "available": False})
    return JSONResponse(content={**base, "commands": [_shown(r) for r in rows], "available": True})


@router.post("")
async def add_command(body: CommandBody, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    fields = await _cleaned(user_id, body)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            existing = await load_commands(client, user_id, strict=True)
            if len(existing) >= MAX_COMMANDS:
                raise HTTPException(status_code=400, detail=f"You can have up to {MAX_COMMANDS} shortcuts. Remove one to add another.")
            resp = await client.post(_sb_url("voice_commands"), headers=_sb_headers("return=representation"), json={"user_id": user_id, **fields})
            if resp.status_code == 409:
                raise HTTPException(status_code=409, detail="You already have a shortcut with that phrase.")
            resp.raise_for_status()
            row = (resp.json() or [{}])[0]
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Adding a voice command failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail=SETUP_NEEDED)
    return JSONResponse(content={"command": _shown(row)})


@router.patch("/{command_id}")
async def change_command(command_id: str, body: CommandBody, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    fields = await _cleaned(user_id, body)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.patch(
                _sb_url("voice_commands"),
                headers=_sb_headers("return=representation"),
                params={"id": f"eq.{command_id}", "user_id": f"eq.{user_id}"},
                json=fields,
            )
            if resp.status_code == 409:
                raise HTTPException(status_code=409, detail="You already have a shortcut with that phrase.")
            resp.raise_for_status()
            rows = resp.json() or []
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Changing a voice command failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Couldn't save that. Please try again.")
    if not rows:
        raise HTTPException(status_code=404, detail="That shortcut wasn't found.")
    return JSONResponse(content={"command": _shown(rows[0])})


@router.delete("/{command_id}")
async def remove_command(command_id: str, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.delete(_sb_url("voice_commands"), headers=_sb_headers("return=minimal"), params={"id": f"eq.{command_id}", "user_id": f"eq.{user_id}"})
            resp.raise_for_status()
    except Exception as exc:
        logger.error("Removing a voice command failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Couldn't remove that. Please try again.")
    return JSONResponse(content={"success": True})


@router.post("/test")
async def try_it(body: TestBody, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    """What a sentence would log, using the person's shortcuts and the built-in rules. Writes nothing."""
    async with httpx.AsyncClient(timeout=15) as client:
        foods, meals = await load_saved(client, user_id)
        custom = await load_commands(client, user_id)
    parsed = parse_log(body.text, 12.0, foods, meals, custom)
    understood = [{"kind": a.kind, "label": a.label} for a in parsed.actions if a.kind != "food_note"]
    return JSONResponse(content={"understood": understood, "kept_as_note": any(a.kind == "food_note" for a in parsed.actions), "unsure": parsed.unsure})

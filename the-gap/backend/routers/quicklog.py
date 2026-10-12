"""
Siri, Shortcuts, the Action Button and Back Tap: add a quick log without opening the app.

  POST   /quicklog/token    (signed in)   mint this device's quick-log key
  DELETE /quicklog/token    (signed in)   revoke it (sign-out)
  GET    /quicklog/check    (the key)     is the key still good?
  POST   /quicklog/entry    (the key)     a sentence, sorted exactly like Quick Entry (routers/log.py)

The key (header X-QuickLog-Token) can do nothing but add a quick log for its
owner. See utils/quicklog_tokens.py for why it isn't the normal login.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from auth import get_current_user_id
from routers.log import MAX_TEXT, process_log_text
from utils import quicklog_tokens

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/quicklog", tags=["quicklog"])

SIGN_IN_AGAIN = "Open The Gap and sign in again, then try once more."


class MintBody(BaseModel):
    label: str = Field(default="iphone", min_length=1, max_length=40)


class EntryBody(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT)
    occurred_at: Optional[datetime] = None
    tz: Optional[str] = Field(default=None, max_length=64)
    local_date: Optional[str] = Field(default=None, max_length=10)
    source: str = Field(default="siri", max_length=20)


@router.post("/token")
async def mint_token(body: MintBody, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        token = await quicklog_tokens.mint(user_id, body.label.strip())
    except Exception as exc:
        logger.error("Minting a quick-log key failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Couldn't set up voice logging. Please try again.")
    return JSONResponse(content={"token": token})


@router.delete("/token")
async def revoke_token(label: Optional[str] = None, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        await quicklog_tokens.revoke_all(user_id, label)
    except Exception as exc:
        logger.error("Revoking quick-log keys failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Couldn't turn off voice logging. Please try again.")
    return JSONResponse(content={"success": True})


async def _owner(token: str) -> str:
    user_id = await quicklog_tokens.user_for_token((token or "").strip())
    if not user_id:
        raise HTTPException(status_code=401, detail=SIGN_IN_AGAIN)
    return user_id


@router.get("/check")
async def check(x_quicklog_token: str = Header(default="")) -> JSONResponse:
    await _owner(x_quicklog_token)
    return JSONResponse(content={"valid": True})


@router.post("/entry")
async def entry(body: EntryBody, x_quicklog_token: str = Header(default="")) -> JSONResponse:
    user_id = await _owner(x_quicklog_token)
    if quicklog_tokens.rate_limited(user_id):
        raise HTTPException(status_code=429, detail="That's a lot of logs at once. Try again in a few minutes.")
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="I didn't catch anything to log.")
    source = body.source if body.source in ("siri", "shortcut", "action_button", "watch") else "siri"
    result = await process_log_text(user_id, body.text, body.local_date, body.occurred_at, body.tz, source)
    return JSONResponse(content=result)

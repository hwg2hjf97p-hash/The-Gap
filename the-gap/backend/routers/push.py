"""
Push token registration. See utils/push.py for the send path and the
push_tokens table DDL.
"""

from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/push", tags=["push"])


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


class RegisterPushTokenRequest(BaseModel):
    expo_push_token: str


@router.post("/register")
async def register_push_token(body: RegisterPushTokenRequest, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    token = body.expo_push_token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="expo_push_token is required.")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _sb_url("push_tokens"),
                headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                params={"on_conflict": "user_id,expo_push_token"},
                json=[{"user_id": user_id, "expo_push_token": token}],
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.error("Push token registration failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Could not register for notifications — please try again.")

    return JSONResponse(content={"status": "ok"})

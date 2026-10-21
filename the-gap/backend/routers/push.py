"""
Push token registration. See utils/push.py for the send path and the
push_tokens table DDL.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth import get_current_user_id
from utils.push import _get_tokens_for_user, get_receipts, send_push_detailed

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


_test_calls: dict[str, list[float]] = {}
MAX_TESTS_PER_HOUR = 6


def _too_many_tests(user_id: str, now: float | None = None) -> bool:
    now = time.time() if now is None else now
    recent = [t for t in _test_calls.get(user_id, []) if now - t < 3600]
    if len(recent) >= MAX_TESTS_PER_HOUR:
        _test_calls[user_id] = recent
        return True
    recent.append(now)
    _test_calls[user_id] = recent
    return False


def plain_verdict(tokens: int, accepted: int, errors: list[str], receipt_errors: list[str]) -> str:
    """What a test send means, in words the person can act on."""
    if tokens == 0:
        return "No phone is registered for notifications on your account yet. Open The Gap, allow notifications if asked, then try again."
    if errors or receipt_errors:
        shown = "; ".join((errors + receipt_errors)[:2])
        return f"A test was sent but it did not go through ({shown}). Send this to support so it can be fixed."
    if accepted == 0:
        return "The test wasn't accepted. Please try again in a minute."
    return "Test sent. It should arrive on your phone within a few seconds."


@router.get("/status")
async def push_status(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    """How many phones are registered for this account (0 means no notification can reach them yet)."""
    return JSONResponse(content={"tokens": len(await _get_tokens_for_user(user_id))})


@router.post("/test")
async def push_test(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    """Sends a test notification right now and reports, honestly, what happened."""
    if _too_many_tests(user_id):
        raise HTTPException(status_code=429, detail="That's a few tests already. Try again in an hour.")
    result = await send_push_detailed(user_id, "Test from The Gap", "If you can read this, notifications work on this phone.", {"kind": "test"}, respect_quiet=False)
    receipt_errors: list[str] = []
    if result["ticket_ids"]:
        await asyncio.sleep(4)  # delivery problems show up in Expo's receipts a moment later
        for receipt in (await get_receipts(result["ticket_ids"])).values():
            if receipt.get("status") == "error":
                receipt_errors.append(f"{(receipt.get('details') or {}).get('error', 'error')}: {receipt.get('message', '')}".strip())
    verdict = plain_verdict(result["tokens"], result["accepted"], result["errors"], receipt_errors)
    return JSONResponse(content={"tokens": result["tokens"], "accepted": result["accepted"], "errors": result["errors"] + receipt_errors, "verdict": verdict})


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

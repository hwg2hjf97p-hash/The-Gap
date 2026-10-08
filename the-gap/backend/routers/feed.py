"""
The Home feed.

  GET  /feed               -> the person's cards (goals reached, research cards, experiment results)
  POST /feed/{id}/seen     -> marks a card as seen
  POST /feed/{id}/dismiss  -> hides a card

Table DDL: see phase8.sql (feed_items).
"""

from __future__ import annotations

import logging
import hmac
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse

from auth import get_current_user_id
from utils.feed import attach_cards, list_feed, update_feed_item
from utils.feed_selector import build_round, generate_for_user, users_with_active_goals

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/feed", tags=["feed"])


@router.get("")
async def get_feed(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        items = await attach_cards(user_id, await list_feed(user_id))
    except Exception as exc:
        logger.warning("Loading feed failed for %s: %s", user_id[:8], exc)
        items = []
    return JSONResponse(content={"items": items})


async def _mark(user_id: str, item_id: str, field: str) -> JSONResponse:
    try:
        found = await update_feed_item(user_id, item_id, {field: datetime.now(timezone.utc).isoformat()})
    except Exception as exc:
        logger.error("Updating feed item failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Couldn't update that card.")
    if not found:
        raise HTTPException(status_code=404, detail="Card not found.")
    return JSONResponse(content={"success": True})


@router.post("/{item_id}/seen")
async def mark_seen(item_id: str, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    return await _mark(user_id, item_id, "seen_at")


@router.post("/{item_id}/dismiss")
async def dismiss(item_id: str, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    return await _mark(user_id, item_id, "dismissed_at")


@router.post("/refresh")
async def refresh(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    """The person asks for research on their goals now. Same rules as the scheduled round (no repeats within 60 days), at most two cards a day."""
    created, reason = await build_round(user_id, forced=True)
    return JSONResponse(content={"created": len(created), "reason": reason})


@router.post("/run")
async def run_round(x_sync_secret: str = Header(default="")) -> JSONResponse:
    """The scheduled round: new cards for everyone with an active goal (see .github/workflows/scheduled-sync.yml)."""
    expected = os.getenv("SYNC_SECRET", "")
    if not expected:
        logger.warning("SYNC_SECRET is not set: POST /feed/run is open to anyone. Set it in the environment.")
    elif not hmac.compare_digest(x_sync_secret.encode(), expected.encode()):
        raise HTTPException(status_code=403, detail="Invalid sync secret.")
    try:
        users = await users_with_active_goals()
    except Exception as exc:
        logger.error("Listing users for the feed round failed: %s", exc)
        raise HTTPException(status_code=503, detail="Database unavailable.")
    added = 0
    for uid in users:
        added += len(await generate_for_user(uid))
    logger.info("FEED_ROUND users=%d cards=%d", len(users), added)
    return JSONResponse(content={"users": len(users), "cards_added": added})

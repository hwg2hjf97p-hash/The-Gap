"""
The Home feed.

  GET  /feed               -> the person's cards (goals reached, research cards, experiment results)
  POST /feed/{id}/seen     -> marks a card as seen
  POST /feed/{id}/dismiss  -> hides a card

Table DDL: see phase8.sql (feed_items).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from auth import get_current_user_id
from utils.feed import list_feed, update_feed_item

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/feed", tags=["feed"])


@router.get("")
async def get_feed(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        items = await list_feed(user_id)
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

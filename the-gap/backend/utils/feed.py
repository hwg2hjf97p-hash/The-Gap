"""
The cards on a person's Home feed (table feed_items): goals they've reached
now, "Check this out" research cards and experiment results later.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


async def create_feed_item(
    user_id: str,
    *,
    kind: str,
    local_date: date,
    title: str,
    body: str = "",
    goal_id: Optional[str] = None,
    card_id: Optional[str] = None,
    payload: Optional[dict] = None,
) -> Optional[dict]:
    """Adds a card to the feed. Returns the new row, or None if it couldn't be saved (never raises)."""
    row = {
        "user_id": user_id,
        "kind": kind,
        "goal_id": goal_id,
        "card_id": card_id,
        "title": title,
        "body": body,
        "payload": payload or {},
        "local_date": local_date.isoformat(),
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(_sb_url("feed_items"), headers=_sb_headers("return=representation"), json=row)
            resp.raise_for_status()
            rows = resp.json() or []
            return rows[0] if rows else None
    except Exception as exc:
        logger.warning("Saving feed item failed for %s: %s", user_id[:8], exc)
        return None


async def list_feed(user_id: str, limit: int = 20) -> list[dict]:
    """The person's cards that they haven't dismissed, newest first."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            _sb_url("feed_items"),
            headers=_sb_headers(),
            params={"user_id": f"eq.{user_id}", "dismissed_at": "is.null", "select": "*", "order": "created_at.desc", "limit": str(limit)},
        )
        resp.raise_for_status()
        return resp.json() or []


async def update_feed_item(user_id: str, item_id: str, fields: dict) -> bool:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.patch(
            _sb_url("feed_items"),
            headers=_sb_headers("return=representation"),
            params={"id": f"eq.{item_id}", "user_id": f"eq.{user_id}"},
            json=fields,
        )
        resp.raise_for_status()
        return bool(resp.json())

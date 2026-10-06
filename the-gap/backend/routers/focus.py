"""
"Today's one thing" — a single recommendation that only unlocks once the
daily check-in is done, so the check-in is worth something beyond just
feeding the engine. Deliberately reuses data every other screen already
has (latest saved results, today's check-in, active interventions) rather
than computing anything new.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import date
from typing import Optional

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from auth import get_current_user_id
from db.supabase_client import get_latest_results
from routers.interventions import get_active_hypothesis_ids

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/focus", tags=["focus"])


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers() -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


async def _has_todays_checkin(user_id: str, today: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _sb_url("daily_checkins"),
                headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "date": f"eq.{today}", "select": "id", "limit": "1"},
            )
            resp.raise_for_status()
            return bool(resp.json())
    except Exception as exc:
        logger.warning("Today check-in lookup failed for %s: %s", user_id[:8], exc)
        return False


@router.get("/today")
async def get_todays_focus(user_id: str = Depends(get_current_user_id), local_date: Optional[str] = None) -> JSONResponse:
    today = local_date or date.today().isoformat()

    if not await _has_todays_checkin(user_id, today):
        return JSONResponse(content={"unlocked": False, "focus": None})

    latest = await asyncio.to_thread(get_latest_results, user_id)
    insights = (latest or {}).get("insights") or []
    active_ids = await get_active_hypothesis_ids(user_id)

    # Confirmed findings only: "today's one thing" is advice to act on, and
    # it shouldn't be built on a pattern that's still just an early signal.
    candidate = next(
        (i for i in insights if i.get("hypothesis_id") not in active_ids and i.get("confidence") != "weak" and not i.get("is_private")),
        None,
    )

    return JSONResponse(content={"unlocked": True, "focus": candidate})

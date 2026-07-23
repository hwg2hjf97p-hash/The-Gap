"""
Device Calendar (EventKit) ingestion — mirrors routers/apple_health.py.

Apple has no server-side OAuth Calendar API. EventKit only exists
on-device, so the native app reads whatever calendars are added at the
iOS system level (Settings -> Calendar -> Accounts — this can include
iCloud, Google, Outlook/Exchange, depending on what the user's added
there) and POSTs the aggregated daily data here.

Same fix pattern as Apple Health: persist first (so a later sync
triggered by a different source doesn't erase this), then route through
the same _sync_user function every other sync path uses, so everything
connected gets merged into one consistent result.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from sync.device_calendar_store import upsert_device_calendar_rows
from sync.daily_sync import _sync_user, _supabase_get

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/device-calendar", tags=["device-calendar"])


class DeviceCalendarSyncRequest(BaseModel):
    user_id: str
    daily_rows: dict[str, dict[str, float]]  # {"2026-07-14": {"calendar_events": 4, "meeting_hours": 2.5, ...}}


@router.post("/sync")
async def sync_device_calendar(body: DeviceCalendarSyncRequest) -> JSONResponse:
    if not body.daily_rows:
        return JSONResponse(content={"status": "no_data", "days": 0})

    # Persist first — survives future syncs triggered by other sources.
    await upsert_device_calendar_rows(body.user_id, body.daily_rows)

    try:
        connections = await _supabase_get(
            "user_connections",
            {"user_id": f"eq.{body.user_id}", "is_active": "eq.true", "select": "*"},
        )
    except Exception as exc:
        logger.error("Could not fetch connections for %s: %s", body.user_id, exc)
        connections = []

    result = await _sync_user(body.user_id, connections)

    if result.get("status") == "no_data":
        raise HTTPException(status_code=500, detail="Sync ran but produced no data — please try again.")

    logger.info(
        "DEVICE_CALENDAR_SYNC_DONE user=%s status=%s",
        body.user_id[:8], result.get("status"),
    )

    return JSONResponse(content={
        "status": result.get("status"),
        "session_id": result.get("session_id"),
        "days": result.get("days"),
        "insights": result.get("insights"),
    })

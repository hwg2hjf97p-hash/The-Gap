"""
Apple Health ingestion — the one genuinely different data path in this app.

Every OAuth provider (Whoop, Oura, Withings, Polar) is fetched server-side.
Apple Health has no server API at all — HealthKit only exists on-device.
So the native app reads HealthKit locally and POSTs the aggregated daily
data here.

This endpoint used to run its own separate merge-and-save pipeline,
completely disconnected from the OAuth-provider one — meaning connecting
Whoop and syncing Apple Health would each silently overwrite the other's
results, since neither knew the other's data existed. Fixed by: (1)
persisting Apple Health data (see sync/apple_health_store.py) so it isn't
thrown away after one request, and (2) routing through the exact same
_sync_user function the OAuth-provider path uses, so every sync — no
matter which source triggered it — merges everything the user has
connected into one consistent result.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from sync.apple_health_store import upsert_apple_health_rows
from sync.daily_sync import _sync_user, _supabase_get

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/apple-health", tags=["apple-health"])


class AppleHealthSyncRequest(BaseModel):
    user_id: str
    daily_rows: dict[str, dict[str, float]]  # {"2026-07-14": {"hrv": 45.2, "steps": 8000, ...}}


@router.post("/sync")
async def sync_apple_health(body: AppleHealthSyncRequest) -> JSONResponse:
    if not body.daily_rows:
        return JSONResponse(content={"status": "no_data", "days": 0})

    # Persist first — this is what makes the data survive future syncs
    # triggered by other sources (e.g. connecting a new OAuth provider
    # later shouldn't erase this).
    await upsert_apple_health_rows(body.user_id, body.daily_rows)

    # Fetch this user's active OAuth connections (same lookup the
    # OAuth-triggered sync endpoint uses) so this run merges everything —
    # Apple Health plus Whoop/Oura/etc — into one unified result, rather
    # than Apple Health running its own disconnected analysis.
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
        # Shouldn't normally happen since we just upserted real data above,
        # but surfaced honestly rather than silently returning success.
        raise HTTPException(status_code=500, detail="Sync ran but produced no data — please try again.")

    logger.info(
        "APPLE_HEALTH_SYNC_DONE user=%s status=%s",
        body.user_id[:8], result.get("status"),
    )

    return JSONResponse(content={
        "status": result.get("status"),
        "session_id": result.get("session_id"),
        "days": result.get("days"),
        "insights": result.get("insights"),
    })

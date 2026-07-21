from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from sync.environment_store import (
    save_user_location,
    get_user_location,
    fetch_and_store_weather,
    fetch_and_store_commute,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/environment", tags=["environment"])


class LocationRequest(BaseModel):
    user_id: str
    home_address: str
    work_address: str = ""


@router.post("/location")
async def set_location(body: LocationRequest) -> JSONResponse:
    if not body.home_address.strip():
        raise HTTPException(status_code=400, detail="Home address is required.")

    saved = await save_user_location(body.user_id, body.home_address.strip(), body.work_address.strip())
    if not saved:
        raise HTTPException(status_code=400, detail="Couldn't find that address — please try being more specific (e.g. add a city or country).")

    location = await get_user_location(body.user_id)
    if not location:
        raise HTTPException(status_code=500, detail="Location saved but couldn't be confirmed — please try again.")

    # Backfill weather immediately — this is the one part of environment
    # data with real history available right away.
    days_stored = await fetch_and_store_weather(body.user_id, location["home_lat"], location["home_lon"])

    return JSONResponse(content={
        "status": "ok",
        "home_address": location["home_address"],
        "work_address": location["work_address"],
        "weather_days_backfilled": days_stored,
    })


@router.get("/location/{user_id}")
async def get_location(user_id: str) -> JSONResponse:
    location = await get_user_location(user_id)
    if not location:
        return JSONResponse(content={"home_address": None, "work_address": None})
    return JSONResponse(content={
        "home_address": location.get("home_address"),
        "work_address": location.get("work_address"),
    })


@router.post("/sync/{user_id}")
async def sync_environment(user_id: str) -> JSONResponse:
    """
    Refreshes weather (backfills recent days) and commute (today's live
    estimate only — see environment_store.py for why commute can't be
    backfilled). Safe to call as often as needed; each field is
    independently fault-tolerant.
    """
    location = await get_user_location(user_id)
    if not location:
        raise HTTPException(status_code=404, detail="No saved location — set one in Settings first.")

    weather_days = await fetch_and_store_weather(user_id, location["home_lat"], location["home_lon"])
    commute_saved = False
    if location.get("work_address"):
        commute_saved = await fetch_and_store_commute(user_id, location["home_address"], location["work_address"])

    return JSONResponse(content={
        "status": "ok",
        "weather_days_updated": weather_days,
        "commute_updated": commute_saved,
    })

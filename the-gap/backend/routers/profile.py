from __future__ import annotations

import asyncio
import logging
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth import get_current_user_id
from sync.user_profile_store import save_user_profile, get_user_profile

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/profile", tags=["profile"])


class ProfileRequest(BaseModel):
    weight_kg: float | None = None
    height_cm: float | None = None
    age: int | None = None


@router.post("")
async def set_profile(body: ProfileRequest, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    saved = await save_user_profile(user_id, body.weight_kg, body.height_cm, body.age)
    if not saved:
        raise HTTPException(status_code=500, detail="Couldn't save profile — please try again.")
    return JSONResponse(content={"status": "ok"})


@router.get("")
async def read_profile(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    profile = await get_user_profile(user_id)
    if not profile:
        return JSONResponse(content={"weight_kg": None, "height_cm": None, "age": None})
    return JSONResponse(content=profile)


# ── Profile checklist ─────────────────────────────────────────────────────────
# What the person has already set up, for the "finish your profile" dial in the app. Whether a connection or a permission is
# in place is known on the phone itself (and depends on what the person owns), so this is only the part held on the server.

# What each answer is called, and where to look for it. A person counts as having done it once any matching row exists.
_CHECKLIST_TABLES: dict[str, tuple[str, dict[str, str]]] = {
    "checkin": ("daily_checkins", {}),
    "food": ("food_log", {}),
    "workout": ("workouts", {}),
    "goal": ("user_goals", {"status": "eq.active"}),
    "nutrition_goals": ("nutrition_goals", {"or": "(calorie_goal.not.is.null,protein_goal_g.not.is.null,water_goal_ml.not.is.null)"}),
    "body": ("user_profile", {"weight_kg": "not.is.null"}),
    "location": ("user_locations", {"home_address": "not.is.null"}),
    "diet_profile": ("health_profile", {"diet_goal": "not.is.null"}),
    "training_profile": ("health_profile", {"training_goal": "not.is.null"}),
}


def _rest(table: str) -> str:
    return f"{os.getenv('SUPABASE_URL', '').strip().rstrip('/')}/rest/v1/{table}"


def _rest_headers() -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    return {"apikey": key, "Authorization": f"Bearer {key}"}


async def _has_row(client: httpx.AsyncClient, user_id: str, table: str, extra: dict[str, str]) -> bool:
    try:
        resp = await client.get(
            _rest(table),
            headers=_rest_headers(),
            params={"user_id": f"eq.{user_id}", "select": "user_id", "limit": "1", **extra},
        )
        resp.raise_for_status()
        return bool(resp.json())
    except Exception as exc:
        logger.warning("Checklist lookup of %s failed for %s: %s", table, user_id[:8], exc)
        return False


@router.get("/checklist")
async def read_checklist(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    async with httpx.AsyncClient(timeout=10) as client:
        keys = list(_CHECKLIST_TABLES)
        found = await asyncio.gather(*(_has_row(client, user_id, *_CHECKLIST_TABLES[k]) for k in keys))
    done = dict(zip(keys, found))
    return JSONResponse(content=done)

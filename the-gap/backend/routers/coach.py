"""
Suggested targets (see utils/coaching.py).

  GET /coach/suggestions   ranges for protein, water, steps, sleep and workout days, each with a reason, based on the person's
                           weight, goal and current averages. Empty if they switched suggestions off.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from auth import get_current_user_id
from routers.suggestions import _load_profile, _sb_headers, _sb_url
from sync.user_profile_store import get_user_profile
from utils import coaching
from utils.goals import current_average
from utils.local_time import user_today

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/coach", tags=["coach"])


async def _latest_weight(user_id: str) -> Optional[float]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _sb_url("weight_log"), headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "select": "weight_kg", "order": "local_date.desc", "limit": "1"},
            )
            resp.raise_for_status()
            rows = resp.json() or []
            return float(rows[0]["weight_kg"]) if rows and rows[0].get("weight_kg") is not None else None
    except Exception as exc:
        logger.info("Latest weight unavailable for coaching (%s)", exc)
        return None


@router.get("/suggestions")
async def suggestions(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    async with httpx.AsyncClient(timeout=15) as client:
        profile = await _load_profile(client, user_id) or {}
    about = await get_user_profile(user_id) or {}
    weight = await _latest_weight(user_id) or about.get("weight_kg")
    today = await user_today(user_id)
    steps, _ = await current_average(user_id, "steps", today)
    sleep, _ = await current_average(user_id, "sleep_total_min", today)
    workouts, _ = await current_average(user_id, "workout_completed_flag", today)
    out = coaching.build(
        weight_kg=float(weight) if weight else None,
        height_cm=float(about["height_cm"]) if about.get("height_cm") else None,
        age=int(about["age"]) if about.get("age") else None,
        diet_goal=profile.get("diet_goal"),
        training_goal=profile.get("training_goal"),
        coach_off=bool(profile.get("coach_off")),
        current_steps=steps,
        current_sleep_hours=sleep,
        current_workouts=workouts,
    )
    return JSONResponse(content=out)

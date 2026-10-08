"""
Goals — a target to work towards, with progress measured as a 7-day rolling
average (see utils/goals.py) and a card on the Home feed when one is reached.

  GET    /goals/catalog              -> what goals can be set, by category
  GET    /goals/preview?metric=KEY   -> the person's current 7-day average for a metric
  POST   /goals/                     -> create a goal (checked for safety)
  GET    /goals/                     -> {"active": [...], "achieved": [...], "goals": [...active, older key]}
  DELETE /goals/{id}                 -> archive a goal
  GET    /goals/available-metrics    -> every readout shown on Home (used by Settings' Home picker, not for goals)

Table DDL: the original user_goals table plus phase8.sql (status, category, target_date, achieved_at).
"""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from auth import get_current_user_id
from utils.goal_catalog import CATEGORY_LABELS, get_metric, public_catalog
from utils.goals import (
    MAX_ACTIVE_GOALS,
    check_goal_achievements,
    compute_goal_progress,
    current_average,
    get_height_cm,
    list_goals as fetch_goals,
    validate_new_goal,
)
from utils.local_time import user_today
from utils.snapshot import METRIC_DISPLAY

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/goals", tags=["goals"])

# Not offered as goals at all, by design.
NUTRITION_KEYS = {"dietary_energy", "protein_g", "carbs_g", "fat_g"}


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


@router.get("/available-metrics")
async def available_metrics() -> JSONResponse:
    metrics = [
        {
            "metric_col": col,
            "label": meta["label"],
            "unit": meta["unit"],
            "suggested_direction": "increase" if meta["higher_is_better"] else "decrease" if meta["higher_is_better"] is False else None,
        }
        for col, meta in METRIC_DISPLAY.items()
    ]
    return JSONResponse(content={"metrics": metrics})


@router.get("/catalog")
async def catalog(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    height = await get_height_cm(user_id)
    return JSONResponse(content={"categories": public_catalog(has_height=bool(height)), "has_height": bool(height)})


@router.get("/preview")
async def preview(metric: str, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    m = get_metric(metric)
    if m is None:
        raise HTTPException(status_code=400, detail="That isn't available as a goal.")
    value, points = await current_average(user_id, metric)
    return JSONResponse(content={"metric_key": metric, "current": value, "points": points, "needed": m.min_points, "enough": value is not None})


class CreateGoalRequest(BaseModel):
    metric_col: str
    metric_label: Optional[str] = None
    unit: str = ""
    direction: str = Field(default="increase", pattern="^(increase|decrease|maintain)$")
    target_value: Optional[float] = None
    target_date: Optional[date] = None


def _refused(code: str, message: str, status: int = 422) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": message, "code": code})


@router.post("/")
async def create_goal(body: CreateGoalRequest, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    if body.metric_col in NUTRITION_KEYS:
        return _refused("not_offered", "The Gap doesn't offer calorie or nutrient targets.", 400)
    metric = get_metric(body.metric_col)
    if metric is None:
        return _refused("not_offered", "That isn't available as a goal.", 400)

    try:
        existing = await fetch_goals(user_id, "active")
    except Exception as exc:
        logger.error("Listing goals failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=503, detail="Couldn't check your goals. Please try again.")
    if len(existing) >= MAX_ACTIVE_GOALS:
        return _refused("too_many", f"You can work on {MAX_ACTIVE_GOALS} goals at once. Archive one to add another.", 409)
    if any(g.get("metric_col") == metric.key for g in existing):
        return _refused("duplicate", f"You already have a goal on {metric.label.lower()}.", 409)

    today = await user_today(user_id)
    baseline, _ = await current_average(user_id, metric.key, today)
    height = await get_height_cm(user_id) if metric.needs_height else None

    problem = validate_new_goal(metric, body.direction, body.target_value, baseline, body.target_date, height, today)
    if problem:
        return _refused(problem["code"], problem["message"])

    payload = {
        "user_id": user_id,
        "metric_col": metric.key,
        "metric_label": metric.label,
        "unit": metric.unit,
        "category": metric.category,
        "direction": body.direction,
        "baseline_value": round(baseline, 3) if baseline is not None else None,
        "target_value": body.target_value,
        "target_date": body.target_date.isoformat() if body.target_date else None,
        "status": "active",
        "active": True,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(_sb_url("user_goals"), headers=_sb_headers("return=representation"), json=payload)
            resp.raise_for_status()
            created = (resp.json() or [None])[0]
    except Exception as exc:
        logger.error("Creating goal failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Could not save that goal.")
    if created:
        created["progress"] = await compute_goal_progress(user_id, created)
    return JSONResponse(content={"goal": created})


@router.get("/")
async def list_goals(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    # A goal reached since the last sync is picked up here too, so the tab is never behind.
    await check_goal_achievements(user_id)
    try:
        goals = await fetch_goals(user_id)
    except Exception as exc:
        logger.error("Listing goals failed for %s: %s", user_id[:8], exc)
        return JSONResponse(content={"goals": [], "active": [], "achieved": []})

    active, achieved = [], []
    for goal in goals:
        status = goal.get("status") or ("active" if goal.get("active", True) else "archived")
        if status == "archived":
            continue
        metric = get_metric(goal.get("metric_col", ""))
        goal["status"] = status
        goal["metric_key"] = goal.get("metric_col")
        goal["category"] = goal.get("category") or (metric.category if metric else "")
        goal["category_label"] = CATEGORY_LABELS.get(goal["category"], "")
        goal["progress"] = await compute_goal_progress(user_id, goal)
        (achieved if status == "achieved" else active).append(goal)

    achieved.sort(key=lambda g: g.get("achieved_at") or "", reverse=True)
    return JSONResponse(content={"goals": active, "active": active, "achieved": achieved})


@router.delete("/{goal_id}")
async def delete_goal(goal_id: str, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.patch(
                _sb_url("user_goals"),
                headers=_sb_headers("return=minimal"),
                params={"id": f"eq.{goal_id}", "user_id": f"eq.{user_id}"},
                json={"status": "archived", "active": False},
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.error("Archiving goal failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Could not remove that goal.")
    return JSONResponse(content={"success": True})

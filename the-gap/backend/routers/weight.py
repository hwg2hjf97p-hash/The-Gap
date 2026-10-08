"""
Logging your weight in the app, for people without a connected scale.

  POST   /weight                  {"weight_kg": 72.4, "local_date": "2026-10-08" (optional)}
  GET    /weight?days=90          -> entries, the latest, and the 7-day average
  DELETE /weight/{local_date}     -> remove an entry

A logged weight counts like any other source (utils/source_merge.py): it feeds
the Weight goal, the weight chart and the analysis. Nothing here ranks, scores
or comments on the numbers.

Table DDL: see phase9.sql (weight_log).
"""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from auth import get_current_user_id
from utils.goals import check_goal_achievements, current_average
from utils.local_time import user_today

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/weight", tags=["weight"])

MAX_DAYS_BACK = 60
MIN_KG, MAX_KG = 20.0, 400.0


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


class WeightBody(BaseModel):
    weight_kg: float = Field(ge=MIN_KG, le=MAX_KG)
    local_date: Optional[date] = None


def valid_log_date(requested: Optional[date], today: date) -> Optional[str]:
    """None when the date is acceptable, otherwise why not."""
    if requested is None:
        return None
    if requested > today:
        return "You can't log a weight for a day that hasn't happened yet."
    if requested < today - timedelta(days=MAX_DAYS_BACK):
        return f"You can log a weight up to {MAX_DAYS_BACK} days back."
    return None


async def _summary(user_id: str, today: date) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            _sb_url("weight_log"),
            headers=_sb_headers(),
            params={"user_id": f"eq.{user_id}", "select": "local_date,weight_kg", "order": "local_date.desc", "limit": "1"},
        )
        resp.raise_for_status()
        rows = resp.json() or []
    average, points = await current_average(user_id, "weight_kg", today)
    return {"latest": rows[0] if rows else None, "average_7d": None if average is None else round(average, 2), "points_7d": points}


@router.post("")
async def log_weight(body: WeightBody, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    today = await user_today(user_id)
    problem = valid_log_date(body.local_date, today)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    day = (body.local_date or today).isoformat()
    kg = round(body.weight_kg, 2)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _sb_url("weight_log"),
                headers=_sb_headers("resolution=merge-duplicates,return=minimal"),
                params={"on_conflict": "user_id,local_date"},
                json={"user_id": user_id, "local_date": day, "weight_kg": kg},
            )
            resp.raise_for_status()
            # Goals read metric_history, so put it there now rather than waiting for the next sync.
            history = await client.post(
                _sb_url("metric_history"),
                headers=_sb_headers("resolution=merge-duplicates,return=minimal"),
                params={"on_conflict": "user_id,date,metric"},
                json=[{"user_id": user_id, "date": day, "metric": "weight_kg", "value": kg}],
            )
            history.raise_for_status()
    except Exception as exc:
        logger.error("Saving weight failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Couldn't save that weight. Please try again.")
    await check_goal_achievements(user_id)
    return JSONResponse(content={"saved": {"local_date": day, "weight_kg": kg}, **await _summary(user_id, today)})


@router.get("")
async def list_weight(days: int = 90, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    today = await user_today(user_id)
    since = (today - timedelta(days=min(max(days, 1), 400))).isoformat()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                _sb_url("weight_log"),
                headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "local_date": f"gte.{since}", "select": "local_date,weight_kg", "order": "local_date.desc"},
            )
            resp.raise_for_status()
            entries = resp.json() or []
        summary = await _summary(user_id, today)
    except Exception as exc:
        logger.warning("Listing weight failed for %s: %s", user_id[:8], exc)
        return JSONResponse(content={"entries": [], "latest": None, "average_7d": None, "points_7d": 0})
    return JSONResponse(content={"entries": entries, **summary})


@router.delete("/{local_date}")
async def delete_weight(local_date: date, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    day = local_date.isoformat()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            for table, params in (
                ("weight_log", {"user_id": f"eq.{user_id}", "local_date": f"eq.{day}"}),
                ("metric_history", {"user_id": f"eq.{user_id}", "date": f"eq.{day}", "metric": "eq.weight_kg"}),
            ):
                resp = await client.delete(_sb_url(table), headers=_sb_headers("return=minimal"), params=params)
                resp.raise_for_status()
    except Exception as exc:
        logger.error("Deleting weight failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Couldn't remove that entry.")
    return JSONResponse(content={"success": True})


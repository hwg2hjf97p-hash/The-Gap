"""
Weekly goals — a target to track progress against, so there's a reason to
open the app on a schedule rather than only when something dramatic
happens. Deliberately scoped to metrics already shown on Home
(utils/snapshot.METRIC_DISPLAY) rather than any arbitrary column, so every
goal is something the user already recognizes and can already see charted.

Table DDL (run once in Supabase SQL editor):
  CREATE TABLE IF NOT EXISTS user_goals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    metric_col TEXT NOT NULL,
    metric_label TEXT NOT NULL,
    unit TEXT DEFAULT '',
    direction TEXT NOT NULL DEFAULT 'increase',
    baseline_value NUMERIC,
    target_value NUMERIC,
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
  );
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
from utils.snapshot import METRIC_DISPLAY
from utils.goals import compute_goal_progress, PROGRESS_WINDOW_DAYS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/goals", tags=["goals"])


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


class CreateGoalRequest(BaseModel):
    metric_col: str
    metric_label: str
    unit: str = ""
    direction: str = Field(default="increase", pattern="^(increase|decrease)$")
    target_value: Optional[float] = None


@router.post("/")
async def create_goal(body: CreateGoalRequest, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    since = (date.today() - timedelta(days=PROGRESS_WINDOW_DAYS)).isoformat()
    baseline_value = None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                _sb_url("metric_history"),
                headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "metric": f"eq.{body.metric_col}", "date": f"gte.{since}", "select": "value"},
            )
            resp.raise_for_status()
            rows = resp.json() or []
            if rows:
                baseline_value = sum(r["value"] for r in rows) / len(rows)
    except Exception as exc:
        logger.warning("Goal baseline fetch failed for %s: %s", user_id[:8], exc)

    payload = {
        "user_id": user_id,
        "metric_col": body.metric_col,
        "metric_label": body.metric_label,
        "unit": body.unit,
        "direction": body.direction,
        "baseline_value": baseline_value,
        "target_value": body.target_value,
        "active": True,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _sb_url("user_goals"),
                headers={**_sb_headers(), "Prefer": "return=representation"},
                json=payload,
            )
            resp.raise_for_status()
            created = resp.json()
    except Exception as exc:
        logger.error("Creating goal failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Could not save that goal.")

    return JSONResponse(content={"goal": created[0] if created else None})


@router.get("/")
async def list_goals(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                _sb_url("user_goals"),
                headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "active": "eq.true", "select": "*", "order": "created_at.desc"},
            )
            resp.raise_for_status()
            goals = resp.json() or []
    except Exception as exc:
        logger.error("Listing goals failed for %s: %s", user_id[:8], exc)
        return JSONResponse(content={"goals": []})

    for goal in goals:
        goal["progress"] = await compute_goal_progress(user_id, goal)

    return JSONResponse(content={"goals": goals})


@router.delete("/{goal_id}")
async def delete_goal(goal_id: str, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.patch(
                _sb_url("user_goals"),
                headers={**_sb_headers(), "Prefer": "return=minimal"},
                params={"id": f"eq.{goal_id}", "user_id": f"eq.{user_id}"},
                json={"active": False},
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.error("Deleting goal failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Could not remove that goal.")
    return JSONResponse(content={"success": True})

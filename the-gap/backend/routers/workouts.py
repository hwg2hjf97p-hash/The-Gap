"""
Workout planning + logging — plan a workout, check it off, and feed
"did the workout you planned actually happen" into the causal engine as
workout_completed_flag (see causal/hypotheses.py's workout_hrv/workout_rhr/
workout_sleep hypotheses). Deliberately not a workout-detail tracker (sets,
reps, weight) — that's well covered by dedicated apps and by Whoop/Strava
auto-detection already synced elsewhere. This is specifically about
intent vs. outcome: did you do the thing you said you'd do.

Table DDL (run once in Supabase SQL editor):
  CREATE TABLE IF NOT EXISTS workouts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    workout_type TEXT NOT NULL,
    planned_date DATE NOT NULL,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'planned',
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
  );
  CREATE INDEX IF NOT EXISTS idx_workouts_user_date
    ON workouts (user_id, planned_date);
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from auth import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/workouts", tags=["workouts"])

WORKOUT_TYPES = ["Strength", "Cardio", "Run", "Yoga/Mobility", "Sport", "Other"]


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


@router.get("/types")
async def get_workout_types() -> JSONResponse:
    return JSONResponse(content={"types": WORKOUT_TYPES})


class CreateWorkoutRequest(BaseModel):
    workout_type: str
    planned_date: str
    notes: Optional[str] = None


@router.post("/")
async def create_workout(body: CreateWorkoutRequest, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    payload = {
        "user_id": user_id,
        "workout_type": body.workout_type,
        "planned_date": body.planned_date,
        "notes": body.notes,
        "status": "planned",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _sb_url("workouts"),
                headers={**_sb_headers(), "Prefer": "return=representation"},
                json=payload,
            )
            resp.raise_for_status()
            created = resp.json()
    except Exception as exc:
        logger.error("Creating workout failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Could not save that workout.")
    return JSONResponse(content={"workout": created[0] if created else None})


@router.get("/")
async def list_workouts(user_id: str = Depends(get_current_user_id), days: int = 30) -> JSONResponse:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                _sb_url("workouts"),
                headers=_sb_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "planned_date": f"gte.{since}",
                    "select": "*",
                    "order": "planned_date.desc",
                },
            )
            resp.raise_for_status()
            return JSONResponse(content={"workouts": resp.json() or []})
    except Exception as exc:
        logger.error("Listing workouts failed for %s: %s", user_id[:8], exc)
        return JSONResponse(content={"workouts": []})


@router.patch("/{workout_id}/complete")
async def complete_workout(workout_id: str, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.patch(
                _sb_url("workouts"),
                headers={**_sb_headers(), "Prefer": "return=minimal"},
                params={"id": f"eq.{workout_id}", "user_id": f"eq.{user_id}"},
                json={"status": "completed", "completed_at": datetime.now(timezone.utc).isoformat()},
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.error("Completing workout failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Could not update that workout.")
    return JSONResponse(content={"success": True})


@router.delete("/{workout_id}")
async def delete_workout(workout_id: str, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.delete(
                _sb_url("workouts"),
                headers={**_sb_headers(), "Prefer": "return=minimal"},
                params={"id": f"eq.{workout_id}", "user_id": f"eq.{user_id}"},
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.error("Deleting workout failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Could not remove that workout.")
    return JSONResponse(content={"success": True})


def get_workout_dataframe(user_id: str, days: int = 180) -> pd.DataFrame:
    """
    One row per planned_date with workout_completed_flag (1 if that day's
    workout was marked done, 0 if planned but not completed). Days with no
    planned workout at all are simply absent — this is a treatment signal,
    not an attendance log, so "no workout planned" shouldn't be coerced
    into a false 0 that the engine would read as "chose not to work out."
    """
    since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    try:
        resp = httpx.get(
            _sb_url("workouts"),
            headers=_sb_headers(),
            params={
                "user_id": f"eq.{user_id}",
                "planned_date": f"gte.{since}",
                "select": "planned_date,status",
            },
            timeout=10,
        )
        resp.raise_for_status()
        rows = resp.json() or []
        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["planned_date"])
        df["workout_completed_flag"] = (df["status"] == "completed").astype(int)
        df = df.groupby("date")["workout_completed_flag"].max().to_frame()
        return df.sort_index()
    except Exception as exc:
        logger.error("Workout dataframe fetch failed: %s", exc)
        return pd.DataFrame()

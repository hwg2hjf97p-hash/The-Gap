"""
Workouts — build a workout from an exercise library (exercise -> sets ->
reps/weight), plan it or check it off, and feed what actually happened into
the causal engine.

Each workout stores its exercises and sets as one JSON document (the
`exercises` column): a workout is always read and written whole, so
separate exercise/set tables would only add joins for no benefit.

Engine signals (see get_workout_dataframe and causal/hypotheses.py):
  workout_completed_flag — a completed workout that day (planned-but-not-done = 0)
  workout_volume_kg      — total weight x reps over the sets checked off
  leg_day_flag           — the workout trained lower body (vs. a completed
                           workout that didn't)
A workout can opt out of the engine with include_in_engine=false.

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

  -- Added with the exercise-library builder:
  ALTER TABLE workouts ADD COLUMN IF NOT EXISTS name TEXT;
  ALTER TABLE workouts ADD COLUMN IF NOT EXISTS exercises JSONB NOT NULL DEFAULT '[]'::jsonb;
  ALTER TABLE workouts ADD COLUMN IF NOT EXISTS duration_min INTEGER;
  ALTER TABLE workouts ADD COLUMN IF NOT EXISTS include_in_engine BOOLEAN NOT NULL DEFAULT true;
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

import httpx
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from auth import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/workouts", tags=["workouts"])

WORKOUT_TYPES = ["Strength", "Cardio", "Run", "Yoga/Mobility", "Sport", "Other"]

# Exercise groups (assigned in the app's bundled exercise library) that count
# as training the lower body for leg_day_flag.
LOWER_BODY_GROUPS = {"Quads", "Hamstrings", "Glutes & hips", "Calves"}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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


class SetModel(BaseModel):
    # reps / weight_kg / duration_min are the PLANNED values (what was
    # intended). What actually happened is in the actual_* fields; older
    # workouts have no actual_* values and are read as "actual == planned".
    reps: Optional[int] = Field(default=None, ge=0, le=1000)
    weight_kg: Optional[float] = Field(default=None, ge=0, le=1000)
    duration_min: Optional[float] = Field(default=None, ge=0, le=1000)
    done: bool = False

    actual_reps: Optional[int] = Field(default=None, ge=0, le=1000)
    actual_weight_kg: Optional[float] = Field(default=None, ge=0, le=1000)
    actual_duration_min: Optional[float] = Field(default=None, ge=0, le=1000)
    # When the set was started and stopped (UTC instants, ISO 8601).
    started_at: Optional[str] = Field(default=None, max_length=40)
    ended_at: Optional[str] = Field(default=None, max_length=40)
    # Heart rate read from Apple Health over the set's time window.
    hr_avg: Optional[float] = Field(default=None, ge=0, le=260)
    hr_peak: Optional[float] = Field(default=None, ge=0, le=260)
    # The suggestion shown for this set, kept so it can be shown again.
    tip: Optional[str] = Field(default=None, max_length=400)


class ExerciseModel(BaseModel):
    exercise_id: str = Field(max_length=100)
    name: str = Field(max_length=200)
    group: str = Field(default="Other", max_length=40)
    category: str = Field(default="strength", max_length=40)
    sets: list[SetModel] = Field(default_factory=list)


class WorkoutBody(BaseModel):
    workout_type: str = Field(max_length=40)
    planned_date: str
    name: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = Field(default=None, max_length=1000)
    exercises: list[ExerciseModel] = Field(default_factory=list)
    status: Literal["planned", "completed"] = "planned"
    duration_min: Optional[int] = Field(default=None, ge=0, le=1440)
    include_in_engine: bool = True


def _check_date(value: str) -> str:
    if not DATE_RE.match(value):
        raise HTTPException(status_code=400, detail="planned_date must be YYYY-MM-DD.")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="planned_date must be a real date.")
    return value


def _row_from_body(body: WorkoutBody, user_id: str) -> dict:
    # Limits checked here rather than as Field constraints, which are
    # spelled differently across pydantic major versions.
    if len(body.exercises) > 40 or any(len(e.sets) > 50 for e in body.exercises):
        raise HTTPException(status_code=400, detail="That workout is too large — max 40 exercises and 50 sets each.")
    return {
        "user_id": user_id,
        "workout_type": body.workout_type,
        "planned_date": _check_date(body.planned_date),
        "name": (body.name or "").strip() or None,
        "notes": (body.notes or "").strip() or None,
        "exercises": [e.model_dump() if hasattr(e, "model_dump") else e.dict() for e in body.exercises],
        "status": body.status,
        "duration_min": body.duration_min,
        "include_in_engine": body.include_in_engine,
    }


@router.post("/")
async def create_workout(body: WorkoutBody, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    payload = _row_from_body(body, user_id)
    if body.status == "completed":
        payload["completed_at"] = datetime.now(timezone.utc).isoformat()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _sb_url("workouts"),
                headers=_sb_headers("return=representation"),
                json=payload,
            )
            resp.raise_for_status()
            created = resp.json()
    except Exception as exc:
        logger.error("Creating workout failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Could not save that workout.")
    return JSONResponse(content={"workout": created[0] if created else None})


@router.put("/{workout_id}")
async def update_workout(workout_id: str, body: WorkoutBody, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    payload = _row_from_body(body, user_id)
    payload.pop("user_id")
    # completed_at tracks when it was actually finished: stamp it on the
    # first transition to completed, clear it if it goes back to planned.
    # (An already-completed workout being edited keeps its original stamp.)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            existing = await client.get(
                _sb_url("workouts"),
                headers=_sb_headers(),
                params={"id": f"eq.{workout_id}", "user_id": f"eq.{user_id}", "select": "completed_at"},
            )
            existing.raise_for_status()
            rows = existing.json() or []
            if not rows:
                raise HTTPException(status_code=404, detail="Workout not found.")
            if body.status == "completed":
                payload["completed_at"] = rows[0].get("completed_at") or datetime.now(timezone.utc).isoformat()
            else:
                payload["completed_at"] = None

            resp = await client.patch(
                _sb_url("workouts"),
                headers=_sb_headers("return=representation"),
                params={"id": f"eq.{workout_id}", "user_id": f"eq.{user_id}"},
                json=payload,
            )
            resp.raise_for_status()
            updated = resp.json()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Updating workout failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Could not save that workout.")
    return JSONResponse(content={"workout": updated[0] if updated else None})


@router.get("/")
async def list_workouts(user_id: str = Depends(get_current_user_id), days: int = 120) -> JSONResponse:
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
                    "order": "planned_date.desc,created_at.desc",
                },
            )
            resp.raise_for_status()
            return JSONResponse(content={"workouts": resp.json() or []})
    except Exception as exc:
        logger.error("Listing workouts failed for %s: %s", user_id[:8], exc)
        return JSONResponse(content={"workouts": []})


@router.patch("/{workout_id}/complete")
async def complete_workout(workout_id: str, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    """Quick "I did it" check-off. For a workout with exercises this counts
    every filled-in set as done — otherwise the engine would record zero
    volume and no leg day for a session that really happened."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            update: dict = {"status": "completed", "completed_at": datetime.now(timezone.utc).isoformat()}
            existing = await client.get(
                _sb_url("workouts"),
                headers=_sb_headers(),
                params={"id": f"eq.{workout_id}", "user_id": f"eq.{user_id}", "select": "exercises"},
            )
            existing.raise_for_status()
            rows = existing.json() or []
            exercises = (rows[0].get("exercises") if rows else None) or []
            if exercises and not any(s.get("done") for ex in exercises for s in (ex.get("sets") or [])):
                for ex in exercises:
                    for s in ex.get("sets") or []:
                        if s.get("reps") or s.get("duration_min"):
                            s["done"] = True
                update["exercises"] = exercises

            resp = await client.patch(
                _sb_url("workouts"),
                headers=_sb_headers("return=minimal"),
                params={"id": f"eq.{workout_id}", "user_id": f"eq.{user_id}"},
                json=update,
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
                headers=_sb_headers("return=minimal"),
                params={"id": f"eq.{workout_id}", "user_id": f"eq.{user_id}"},
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.error("Deleting workout failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Could not remove that workout.")
    return JSONResponse(content={"success": True})


def _volume_kg(exercises: list[dict]) -> float:
    """Total weight x reps over the sets that were checked off, using what
    was actually done (falling back to the planned numbers for sets that
    have no separate actual values, i.e. older workouts)."""
    total = 0.0
    for ex in exercises or []:
        for s in ex.get("sets") or []:
            if not s.get("done"):
                continue
            reps = s.get("actual_reps") if s.get("actual_reps") is not None else s.get("reps")
            weight = s.get("actual_weight_kg") if s.get("actual_weight_kg") is not None else s.get("weight_kg")
            if reps and weight:
                total += float(reps) * float(weight)
    return total


def _trained_lower_body(exercises: list[dict]) -> bool:
    return any(
        ex.get("group") in LOWER_BODY_GROUPS and any(s.get("done") for s in (ex.get("sets") or []))
        for ex in exercises or []
    )


def get_workout_dataframe(user_id: str, days: int = 180) -> pd.DataFrame:
    """
    Date-indexed daily workout signals for the engine. Only days with a
    workout that opted into the engine appear at all — "no workout logged"
    isn't the same as "chose not to work out", so it's left absent rather
    than coerced to a false 0.

      workout_completed_flag  1 if any workout was completed, 0 if only planned
      workout_volume_kg       total weight x reps over checked-off sets, on days
                              that logged any (NaN otherwise, e.g. cardio-only)
      leg_day_flag            1/0 on completed workouts that logged exercises
    """
    since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    try:
        resp = httpx.get(
            _sb_url("workouts"),
            headers=_sb_headers(),
            params={
                "user_id": f"eq.{user_id}",
                "planned_date": f"gte.{since}",
                "select": "planned_date,status,exercises,include_in_engine",
            },
            timeout=10,
        )
        resp.raise_for_status()
        rows = [r for r in (resp.json() or []) if r.get("include_in_engine", True)]
        if not rows:
            return pd.DataFrame()

        daily: dict[str, dict] = {}
        for r in rows:
            d = daily.setdefault(r["planned_date"], {"completed": False, "volume": 0.0, "has_ex": False, "lower": False})
            if r.get("status") != "completed":
                continue
            d["completed"] = True
            exercises = r.get("exercises") or []
            if exercises:
                d["has_ex"] = True
                d["volume"] += _volume_kg(exercises)
                d["lower"] = d["lower"] or _trained_lower_body(exercises)

        records = {}
        for date, d in daily.items():
            records[date] = {
                "workout_completed_flag": 1 if d["completed"] else 0,
                "workout_volume_kg": d["volume"] if d["volume"] > 0 else None,
                "leg_day_flag": (1 if d["lower"] else 0) if d["completed"] and d["has_ex"] else None,
            }
        df = pd.DataFrame.from_dict(records, orient="index")
        df.index = pd.to_datetime(df.index)
        return df.sort_index()
    except Exception as exc:
        logger.error("Workout dataframe fetch failed: %s", exc)
        return pd.DataFrame()

"""
My workout templates: a workout the person saved to start from again. It keeps
the movements with their planned sets, reps, weights and minutes (never what
happened on the day), the format (standard, for time, AMRAP) and the notes.

Table DDL (run once in the Supabase SQL editor, also in phase16.sql):
  CREATE TABLE IF NOT EXISTS workout_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    notes TEXT,
    format JSONB,
    exercises JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  );
  CREATE INDEX IF NOT EXISTS idx_workout_templates_user ON workout_templates (user_id, created_at DESC);
  ALTER TABLE workout_templates ENABLE ROW LEVEL SECURITY;
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from auth import get_current_user_id
from routers.workouts import ExerciseModel, FormatModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/workout-templates", tags=["workout-templates"])

MAX_TEMPLATES = 60


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


class TemplateBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    notes: Optional[str] = Field(default=None, max_length=1000)
    format: Optional[FormatModel] = None
    exercises: list[ExerciseModel] = Field(default_factory=list)


def planned_only(exercises: list[dict]) -> list[dict]:
    """A template keeps the plan, never what happened on the day: drop
    completion, actual numbers, timings, heart rate and tips."""
    out = []
    for ex in exercises:
        out.append(
            {
                "exercise_id": ex.get("exercise_id"),
                "name": ex.get("name"),
                "group": ex.get("group") or "Other",
                "category": ex.get("category") or "strength",
                "sets": [
                    {"reps": s.get("reps"), "weight_kg": s.get("weight_kg"), "duration_min": s.get("duration_min")}
                    for s in (ex.get("sets") or [])
                ],
            }
        )
    return out


def template_row(body: TemplateBody, user_id: str) -> dict:
    if len(body.exercises) == 0:
        raise HTTPException(status_code=400, detail="Add at least one exercise before saving a template.")
    if len(body.exercises) > 40 or any(len(e.sets) > 50 for e in body.exercises):
        raise HTTPException(status_code=400, detail="That workout is too large to save as a template.")
    exercises = [e.model_dump() if hasattr(e, "model_dump") else e.dict() for e in body.exercises]
    fmt = None
    if body.format is not None:
        # Only the style, time cap and split choice belong in a template; a result and laps do not.
        fmt = {"style": body.format.style, "cap_min": body.format.cap_min, "split": body.format.split}
    return {
        "user_id": user_id,
        "name": body.name.strip(),
        "notes": (body.notes or "").strip() or None,
        "format": fmt,
        "exercises": planned_only(exercises),
    }


@router.get("/")
async def list_templates(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                _sb_url("workout_templates"),
                headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "select": "*", "order": "created_at.desc"},
            )
            resp.raise_for_status()
            return JSONResponse(content={"templates": resp.json() or []})
    except Exception as exc:
        logger.error("Listing templates failed for %s: %s", user_id[:8], exc)
        return JSONResponse(content={"templates": []})


@router.post("/")
async def create_template(body: TemplateBody, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    row = template_row(body, user_id)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            existing = await client.get(
                _sb_url("workout_templates"),
                headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "select": "id"},
            )
            existing.raise_for_status()
            if len(existing.json() or []) >= MAX_TEMPLATES:
                raise HTTPException(status_code=400, detail=f"You can keep up to {MAX_TEMPLATES} templates. Delete one to make room.")
            resp = await client.post(
                _sb_url("workout_templates"),
                headers=_sb_headers("return=representation"),
                json=row,
            )
            resp.raise_for_status()
            created = resp.json()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Creating template failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Could not save that template.")
    return JSONResponse(content={"template": created[0] if created else None})


@router.delete("/{template_id}")
async def delete_template(template_id: str, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.delete(
                _sb_url("workout_templates"),
                headers=_sb_headers("return=minimal"),
                params={"id": f"eq.{template_id}", "user_id": f"eq.{user_id}"},
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.error("Deleting template failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Could not remove that template.")
    return JSONResponse(content={"success": True})

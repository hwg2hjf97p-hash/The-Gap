"""
Improvement-plan endpoint — same cache + daily-limit pattern as
routers/metric_insight.py and routers/hypothesis_explanation.py, kept as
its own small router/table since this generates a different kind of
content (a deeper plan for a CONFIRMED insight) than either of those.
See utils/improvement_plan.py for the generation logic.

Table DDL (run once in Supabase SQL editor):
  CREATE TABLE IF NOT EXISTS improvement_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    hypothesis_id TEXT NOT NULL,
    plan_text TEXT NOT NULL,
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, hypothesis_id)
  );

  CREATE TABLE IF NOT EXISTS improvement_plan_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    usage_date DATE NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    UNIQUE(user_id, usage_date)
  );
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth import get_current_user_id
import json
from typing import Optional

from utils.improvement_plan import generate_insight_story, parse_story, flatten_story, STORY_VERSION

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/improvement", tags=["improvement"])

DAILY_GENERATION_LIMIT = 15
CACHE_HOURS = 72  # a confirmed finding's story doesn't change from day to day


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


class ImprovementPlanRequest(BaseModel):
    hypothesis_id: str
    treatment_label: str
    outcome_label: str
    headline: str
    existing_tip: str
    metric_direction: str
    # Extra facts for the plain-English story; optional so older app builds
    # that don't send them keep working.
    metric_delta: Optional[str] = None
    metric_unit: Optional[str] = None
    confidence_label: Optional[str] = None
    n_observations: Optional[int] = None


async def _get_cached(user_id: str, hypothesis_id: str) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _sb_url("improvement_plans"),
                headers=_sb_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "hypothesis_id": f"eq.{hypothesis_id}",
                    "select": "plan_text,generated_at",
                    "limit": 1,
                },
            )
            resp.raise_for_status()
            rows = resp.json() or []
            return rows[0] if rows else None
    except Exception as exc:
        logger.warning("Improvement plan cache lookup failed: %s", exc)
        return None


async def _save_cache(user_id: str, hypothesis_id: str, plan_text: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                _sb_url("improvement_plans"),
                headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                params={"on_conflict": "user_id,hypothesis_id"},
                json=[{
                    "user_id": user_id,
                    "hypothesis_id": hypothesis_id,
                    "plan_text": plan_text,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }],
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("Improvement plan cache save failed (continuing anyway): %s", exc)


async def _get_today_count(user_id: str) -> int:
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _sb_url("improvement_plan_usage"),
                headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "usage_date": f"eq.{today}", "select": "count", "limit": 1},
            )
            resp.raise_for_status()
            rows = resp.json() or []
            return rows[0]["count"] if rows else 0
    except Exception as exc:
        logger.warning("Improvement plan usage lookup failed (assuming 0): %s", exc)
        return 0


async def _increment_today_count(user_id: str, current: int) -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                _sb_url("improvement_plan_usage"),
                headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                params={"on_conflict": "user_id,usage_date"},
                json=[{"user_id": user_id, "usage_date": today, "count": current + 1}],
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("Improvement plan usage increment failed (continuing anyway): %s", exc)


def _response(cached_text: str | None, story: dict | None, cached: bool, limit_reached: bool) -> JSONResponse:
    """`story` is the structured plain-English card; `plan_text` is a flat
    text rendering of it (or the old-style plan text) for older app builds."""
    plan_text = flatten_story(story) if story else cached_text
    return JSONResponse(content={"plan_text": plan_text, "story": story, "cached": cached, "limit_reached": limit_reached})


@router.post("")
async def get_improvement_plan(body: ImprovementPlanRequest, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    """
    The plain-English story for a confirmed finding. The cache table's
    plan_text column now holds the story as JSON (version-tagged); a row
    that's still old-style plain text is treated as a miss and regenerated,
    but is still returned if we can't generate a new one right now.
    """
    cached = await _get_cached(user_id, body.hypothesis_id)
    cached_story = parse_story(cached["plan_text"]) if cached else None

    if cached_story and cached:
        try:
            age_hours = (
                datetime.now(timezone.utc)
                - datetime.fromisoformat(cached["generated_at"].replace("Z", "+00:00"))
            ).total_seconds() / 3600
        except Exception as exc:
            logger.warning("Could not parse cached generated_at (%r) — treating as stale: %s", cached.get("generated_at"), exc)
            age_hours = CACHE_HOURS
        if age_hours < CACHE_HOURS:
            return _response(cached["plan_text"], cached_story, True, False)

    cached_text = cached["plan_text"] if cached else None

    today_count = await _get_today_count(user_id)
    if today_count >= DAILY_GENERATION_LIMIT:
        if cached:
            return _response(cached_text, cached_story, True, True)
        return JSONResponse(content={
            "plan_text": "You've reached today's limit for now — check back tomorrow.",
            "story": None,
            "cached": False,
            "limit_reached": True,
        })

    story = await generate_insight_story(
        treatment_label=body.treatment_label,
        outcome_label=body.outcome_label,
        headline=body.headline,
        existing_tip=body.existing_tip,
        metric_direction=body.metric_direction,
        metric_delta=body.metric_delta or "",
        metric_unit=body.metric_unit or "",
        confidence_label=body.confidence_label or "",
        n_observations=body.n_observations,
    )

    if story is None:
        return _response(cached_text, cached_story, bool(cached), False)

    await _save_cache(user_id, body.hypothesis_id, json.dumps(story))
    await _increment_today_count(user_id, today_count)

    return _response(None, story, False, False)

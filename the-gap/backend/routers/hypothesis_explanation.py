"""
Explanation endpoint for the "Running on you" experiment cards. Same
cost-control pattern as routers/metric_insight.py (1-hour cache, daily
generation cap) but with its own separate tables, so tapping experiment
cards doesn't compete with metric-icon taps for the same daily quota.

Table DDL (run once in Supabase SQL editor):
  CREATE TABLE IF NOT EXISTS hypothesis_explanations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    hypothesis_id TEXT NOT NULL,
    explanation_text TEXT NOT NULL,
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, hypothesis_id)
  );

  CREATE TABLE IF NOT EXISTS hypothesis_explanation_usage (
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
from causal.hypotheses import HYPOTHESES
from utils.hypothesis_explanation import generate_hypothesis_explanation, generate_raw_signal_explanation

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/hypothesis-explanation", tags=["hypothesis-explanation"])

DAILY_GENERATION_LIMIT = 15
CACHE_HOURS = 1


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


class HypothesisExplanationRequest(BaseModel):
    kind: str = "hypothesis"  # "hypothesis" | "raw_signal"
    # for kind="hypothesis":
    hypothesis_id: str | None = None
    current_days: int | None = None
    required_days: int | None = None
    # for kind="raw_signal" — CANDIDATE_PAIRS in snapshot.py is a fixed,
    # hardcoded list, so each pattern's description text is stable and
    # unique — safe to use directly as the cache key, same role
    # hypothesis_id plays for the other kind.
    description: str | None = None
    r: float | None = None
    direction: str | None = None
    n: int | None = None

    @property
    def cache_key(self) -> str:
        return self.hypothesis_id if self.kind == "hypothesis" else (self.description or "")


async def _get_cached(user_id: str, hypothesis_id: str) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _sb_url("hypothesis_explanations"),
                headers=_sb_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "hypothesis_id": f"eq.{hypothesis_id}",
                    "select": "explanation_text,generated_at",
                    "limit": 1,
                },
            )
            resp.raise_for_status()
            rows = resp.json() or []
            return rows[0] if rows else None
    except Exception as exc:
        logger.warning("Hypothesis explanation cache lookup failed: %s", exc)
        return None


async def _save_cache(user_id: str, hypothesis_id: str, explanation_text: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                _sb_url("hypothesis_explanations"),
                headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                params={"on_conflict": "user_id,hypothesis_id"},
                json=[{
                    "user_id": user_id,
                    "hypothesis_id": hypothesis_id,
                    "explanation_text": explanation_text,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }],
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("Hypothesis explanation cache save failed (continuing anyway): %s", exc)


async def _get_today_count(user_id: str) -> int:
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _sb_url("hypothesis_explanation_usage"),
                headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "usage_date": f"eq.{today}", "select": "count", "limit": 1},
            )
            resp.raise_for_status()
            rows = resp.json() or []
            return rows[0]["count"] if rows else 0
    except Exception as exc:
        logger.warning("Hypothesis explanation usage lookup failed (assuming 0): %s", exc)
        return 0


async def _increment_today_count(user_id: str, current: int) -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                _sb_url("hypothesis_explanation_usage"),
                headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                params={"on_conflict": "user_id,usage_date"},
                json=[{"user_id": user_id, "usage_date": today, "count": current + 1}],
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("Hypothesis explanation usage increment failed (continuing anyway): %s", exc)


@router.post("")
async def get_hypothesis_explanation(body: HypothesisExplanationRequest, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    cache_key = body.cache_key
    if not cache_key:
        return JSONResponse(content={"explanation_text": None, "cached": False, "limit_reached": False})

    hyp = None
    if body.kind == "hypothesis":
        hyp = next((h for h in HYPOTHESES if h.id == body.hypothesis_id), None)
        if hyp is None:
            return JSONResponse(content={"explanation_text": None, "cached": False, "limit_reached": False})

    cached = await _get_cached(user_id, cache_key)

    if cached:
        # Same fix as metric_insight.py's earlier bug: never let a
        # timestamp-parsing hiccup crash this endpoint outright.
        try:
            age_hours = (
                datetime.now(timezone.utc)
                - datetime.fromisoformat(cached["generated_at"].replace("Z", "+00:00"))
            ).total_seconds() / 3600
        except Exception as exc:
            logger.warning("Could not parse cached generated_at (%r) — treating as stale: %s", cached.get("generated_at"), exc)
            age_hours = CACHE_HOURS
        if age_hours < CACHE_HOURS:
            return JSONResponse(content={"explanation_text": cached["explanation_text"], "cached": True, "limit_reached": False})

    today_count = await _get_today_count(user_id)
    if today_count >= DAILY_GENERATION_LIMIT:
        if cached:
            return JSONResponse(content={"explanation_text": cached["explanation_text"], "cached": True, "limit_reached": True})
        return JSONResponse(content={
            "explanation_text": "You've reached today's explanation limit for now — check back tomorrow.",
            "cached": False,
            "limit_reached": True,
        })

    if body.kind == "hypothesis":
        explanation_text = await generate_hypothesis_explanation(
            treatment_label=hyp.treatment_label,
            outcome_label=hyp.outcome_label,
            category=hyp.category,
            current_days=body.current_days,
            required_days=body.required_days,
        )
    else:
        explanation_text = await generate_raw_signal_explanation(
            description=body.description or "",
            r=body.r or 0.0,
            direction=body.direction or "positive",
            n=body.n or 0,
        )

    if explanation_text is None:
        if cached:
            return JSONResponse(content={"explanation_text": cached["explanation_text"], "cached": True, "limit_reached": False})
        return JSONResponse(content={"explanation_text": None, "cached": False, "limit_reached": False})

    await _save_cache(user_id, cache_key, explanation_text)
    await _increment_today_count(user_id, today_count)

    return JSONResponse(content={"explanation_text": explanation_text, "cached": False, "limit_reached": False})

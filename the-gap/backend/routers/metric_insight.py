"""
Personalized per-metric insight, generated on-demand when someone taps a
metric card on Home. Two cost controls, both requested by the product
owner before building this:

1. **1-hour cache per (user, metric)** — tapping the same metric again
   within an hour shows the same text instead of generating a new one.
2. **Daily cap per user** — once a user has triggered this many *new*
   generations today, further taps fall back to their last cached
   insight (or a plain message if they have none yet) instead of calling
   the LLM again. Resets naturally at UTC midnight since it's counted
   per calendar date, not a rolling window.

Table DDL (run once in Supabase SQL editor):
  CREATE TABLE IF NOT EXISTS metric_insights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    insight_text TEXT NOT NULL,
    reading_value NUMERIC,
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, metric)
  );

  CREATE TABLE IF NOT EXISTS metric_insight_usage (
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
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from causal.hypotheses import HYPOTHESES
from utils.metric_personal_insight import generate_personal_insight

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/metric-insight", tags=["metric-insight"])

# Adjust freely — this is the one number that controls worst-case daily
# LLM cost per user. At Haiku 4.5 pricing for ~200-token responses, this
# is a very small, bounded cost even at the cap.
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


class MetricInsightRequest(BaseModel):
    user_id: str
    metric: str
    metric_label: str
    reading_value: float
    unit: str
    comparison_text: str


def _relevant_hypothesis_labels(metric: str) -> list[str]:
    """Real lookup against the actual hypothesis list — never invented,
    so the LLM can't claim a metric affects a hypothesis that doesn't
    exist (this is exactly the gap that turned up for sleep_score)."""
    labels = []
    for h in HYPOTHESES:
        if h.treatment_col == metric or h.outcome_col == metric:
            labels.append(f"{h.treatment_label} → {h.outcome_label}")
    return labels


async def _get_cached(user_id: str, metric: str) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _sb_url("metric_insights"),
                headers=_sb_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "metric": f"eq.{metric}",
                    "select": "insight_text,generated_at",
                    "limit": 1,
                },
            )
            resp.raise_for_status()
            rows = resp.json() or []
            return rows[0] if rows else None
    except Exception as exc:
        logger.warning("Metric insight cache lookup failed: %s", exc)
        return None


async def _save_cache(user_id: str, metric: str, reading_value: float, insight_text: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                _sb_url("metric_insights"),
                headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                params={"on_conflict": "user_id,metric"},
                json=[{
                    "user_id": user_id,
                    "metric": metric,
                    "insight_text": insight_text,
                    "reading_value": reading_value,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }],
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("Metric insight cache save failed (continuing anyway): %s", exc)


async def _get_today_count(user_id: str) -> int:
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _sb_url("metric_insight_usage"),
                headers=_sb_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "usage_date": f"eq.{today}",
                    "select": "count",
                    "limit": 1,
                },
            )
            resp.raise_for_status()
            rows = resp.json() or []
            return rows[0]["count"] if rows else 0
    except Exception as exc:
        logger.warning("Metric insight usage lookup failed (assuming 0): %s", exc)
        return 0


async def _increment_today_count(user_id: str, current: int) -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                _sb_url("metric_insight_usage"),
                headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                params={"on_conflict": "user_id,usage_date"},
                json=[{"user_id": user_id, "usage_date": today, "count": current + 1}],
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("Metric insight usage increment failed (continuing anyway): %s", exc)


@router.post("")
async def get_metric_insight(body: MetricInsightRequest) -> JSONResponse:
    cached = await _get_cached(body.user_id, body.metric)

    # 1. Fresh cache (< 1 hour old) — return it, no LLM call, no cost.
    if cached:
        age_hours = (
            datetime.now(timezone.utc)
            - datetime.fromisoformat(cached["generated_at"].replace("Z", "+00:00"))
        ).total_seconds() / 3600
        if age_hours < CACHE_HOURS:
            return JSONResponse(content={
                "insight_text": cached["insight_text"],
                "cached": True,
                "limit_reached": False,
            })

    # 2. Cache is stale or missing — check the daily cap before calling the LLM.
    today_count = await _get_today_count(body.user_id)
    if today_count >= DAILY_GENERATION_LIMIT:
        if cached:
            return JSONResponse(content={
                "insight_text": cached["insight_text"],
                "cached": True,
                "limit_reached": True,
            })
        return JSONResponse(content={
            "insight_text": "You've reached today's insight limit for now — check back tomorrow for a fresh read on this metric.",
            "cached": False,
            "limit_reached": True,
        })

    # 3. Under the cap — generate a fresh one, grounded in real hypothesis data.
    relevant = _relevant_hypothesis_labels(body.metric)
    insight_text = await generate_personal_insight(
        metric_label=body.metric_label,
        reading_value=str(body.reading_value),
        unit=body.unit,
        comparison_text=body.comparison_text,
        relevant_hypotheses=relevant,
    )

    if insight_text is None:
        # Generation failed — fall back to old cache if we have it, don't
        # charge this failed attempt against the daily count.
        if cached:
            return JSONResponse(content={
                "insight_text": cached["insight_text"],
                "cached": True,
                "limit_reached": False,
            })
        return JSONResponse(content={
            "insight_text": None,
            "cached": False,
            "limit_reached": False,
        })

    await _save_cache(body.user_id, body.metric, body.reading_value, insight_text)
    await _increment_today_count(body.user_id, today_count)

    return JSONResponse(content={
        "insight_text": insight_text,
        "cached": False,
        "limit_reached": False,
    })

"""
Starting a "test it on yourself" experiment from an approved research card.

  POST /evidence/experiment   {"card_id": "...", "metric_key": "sleep_total_min"}

The person tries the card's everyday habit for its number of days (14). The
reading they chose (one of the card's metrics) is compared afterwards with the
days before (utils/experiments.py). Only approved cards that name a behaviour
can be tested, and never a supplement.
"""

from __future__ import annotations

import logging
import os
from datetime import timedelta

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth import get_current_user_id
from routers.interventions import get_active_hypothesis_ids
from utils.evidence import get_verified_card
from utils.experiments import BASELINE_DAYS, MIN_BEFORE
from utils.goal_catalog import get_metric
from utils.goals import fetch_points, fmt
from utils.local_time import user_today

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/evidence", tags=["evidence"])


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


class ExperimentBody(BaseModel):
    card_id: str
    metric_key: str


def _refused(code: str, message: str, status: int = 400) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": message, "code": code})


@router.post("/experiment")
async def start_experiment(body: ExperimentBody, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        card = await get_verified_card(body.card_id)
    except Exception as exc:
        logger.error("Loading card failed for %s: %s", user_id[:8], exc)
        return _refused("unavailable", "Couldn't load that card. Please try again.", 503)
    if not card:
        return _refused("no_card", "That card isn't available.", 404)
    if not (card.get("experiment_label") or "").strip():
        return _refused("no_experiment", "This card doesn't suggest something to test.")
    metric = get_metric(body.metric_key)
    if metric is None or body.metric_key not in (card.get("metric_tags") or []):
        return _refused("bad_metric", "That reading isn't one this card speaks to.")

    hypothesis_id = f"card:{card['id']}"
    if hypothesis_id in await get_active_hypothesis_ids(user_id):
        return _refused("already", "You're already testing this one.", 409)

    today = await user_today(user_id)
    points = await fetch_points(user_id, metric.key, today - timedelta(days=BASELINE_DAYS))
    before = [v for d, v in points if d < today]
    if len(before) < MIN_BEFORE:
        return _refused(
            "no_baseline",
            f"We need at least {MIN_BEFORE} days of {metric.label.lower()} from the last two weeks to compare against ({len(before)} so far). Check your device is syncing, then try again.",
            422,
        )
    baseline = sum(before) / len(before) * (7 if metric.per_week else 1) / metric.scale

    days = int(card.get("experiment_days") or 14)
    row = {
        "user_id": user_id,
        "hypothesis_id": hypothesis_id,
        "treatment_label": card["experiment_label"].strip(),
        "outcome_label": metric.label,
        "outcome_col": metric.key,
        "metric_unit": metric.unit,
        "baseline_value": round(baseline, 3),
        "started_date": today.isoformat(),
        "follow_up_days": days,
        "status": "active",
        "card_id": card["id"],
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(_sb_url("active_interventions"), headers=_sb_headers("return=representation"), json=row)
            resp.raise_for_status()
            created = (resp.json() or [None])[0]
    except Exception as exc:
        logger.error("Starting card experiment failed for %s: %s", user_id[:8], exc)
        return _refused("save_failed", "Couldn't start the test. Please try again.", 500)

    finish = today + timedelta(days=days)
    return JSONResponse(content={"intervention": created, "days": days, "finishes": finish.isoformat(), "baseline": fmt(baseline, metric.decimals)})

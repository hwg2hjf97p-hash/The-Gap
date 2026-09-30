"""
"I'll try this" tracking — lets a user commit to acting on a confirmed
insight, then get a follow-up days later on whether it actually worked.
Closes the loop that the rest of the app leaves open: insights and
improvement plans currently just tell you something, with no memory of
whether you acted on it or what happened next.

Table DDL (run once in Supabase SQL editor):
  CREATE TABLE IF NOT EXISTS active_interventions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    hypothesis_id TEXT NOT NULL,
    treatment_label TEXT NOT NULL,
    outcome_label TEXT NOT NULL,
    outcome_col TEXT NOT NULL,
    metric_unit TEXT DEFAULT '',
    baseline_value NUMERIC,
    started_date DATE NOT NULL,
    follow_up_days INTEGER NOT NULL DEFAULT 7,
    status TEXT NOT NULL DEFAULT 'active',
    result_value NUMERIC,
    result_improved BOOLEAN,
    created_at TIMESTAMPTZ DEFAULT NOW()
  );
  CREATE INDEX IF NOT EXISTS idx_active_interventions_user
    ON active_interventions (user_id, status);
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from auth import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/interventions", tags=["interventions"])

FOLLOW_UP_DAYS_DEFAULT = 7
BASELINE_WINDOW_DAYS = 14


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


def base_metric(outcome_col: str) -> str:
    """Strip a lag/lead suffix so an outcome column maps back to the plain
    metric that's actually tracked in metric_history (e.g. hrv_next -> hrv,
    resting_hr_next -> resting_hr; anything without a known suffix is
    already a bare metric name)."""
    return outcome_col.removesuffix("_next")


async def _mean_metric(user_id: str, metric: str, start: str, end: str) -> float | None:
    """Mean of metric_history rows for `metric` in [start, end] (inclusive)."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                _sb_url("metric_history"),
                headers=_sb_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "metric": f"eq.{metric}",
                    "date": f"gte.{start}",
                    "select": "date,value",
                },
            )
            resp.raise_for_status()
            rows = [r for r in (resp.json() or []) if r["date"] <= end]
            if not rows:
                return None
            return sum(r["value"] for r in rows) / len(rows)
    except Exception as exc:
        logger.warning("Metric history mean fetch failed for %s/%s: %s", user_id[:8], metric, exc)
        return None


class CreateInterventionRequest(BaseModel):
    hypothesis_id: str
    treatment_label: str
    outcome_label: str
    outcome_col: str
    metric_unit: str = ""
    follow_up_days: int = Field(default=FOLLOW_UP_DAYS_DEFAULT, ge=1, le=30)


@router.post("/")
async def create_intervention(body: CreateInterventionRequest, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    today = date.today().isoformat()
    window_start = (date.today() - timedelta(days=BASELINE_WINDOW_DAYS)).isoformat()
    baseline_value = await _mean_metric(user_id, base_metric(body.outcome_col), window_start, today)

    payload = {
        "user_id": user_id,
        "hypothesis_id": body.hypothesis_id,
        "treatment_label": body.treatment_label,
        "outcome_label": body.outcome_label,
        "outcome_col": body.outcome_col,
        "metric_unit": body.metric_unit,
        "baseline_value": baseline_value,
        "started_date": today,
        "follow_up_days": body.follow_up_days,
        "status": "active",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _sb_url("active_interventions"),
                headers={**_sb_headers(), "Prefer": "return=representation"},
                json=payload,
            )
            resp.raise_for_status()
            created = resp.json()
    except Exception as exc:
        logger.error("Creating intervention failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Could not start tracking that.")

    return JSONResponse(content={"intervention": created[0] if created else None})


@router.get("/")
async def list_interventions(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                _sb_url("active_interventions"),
                headers=_sb_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "select": "*",
                    "order": "created_at.desc",
                    "limit": "20",
                },
            )
            resp.raise_for_status()
            return JSONResponse(content={"interventions": resp.json() or []})
    except Exception as exc:
        logger.error("Listing interventions failed for %s: %s", user_id[:8], exc)
        return JSONResponse(content={"interventions": []})


@router.delete("/{intervention_id}")
async def delete_intervention(intervention_id: str, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.delete(
                _sb_url("active_interventions"),
                headers={**_sb_headers(), "Prefer": "return=minimal"},
                params={"id": f"eq.{intervention_id}", "user_id": f"eq.{user_id}"},
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.error("Deleting intervention failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Could not remove that.")
    return JSONResponse(content={"success": True})


async def get_active_hypothesis_ids(user_id: str) -> set[str]:
    """Hypothesis IDs the user is currently tracking as an active
    intervention — used to avoid nudging or recommending something they're
    already trying."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                _sb_url("active_interventions"),
                headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "status": "eq.active", "select": "hypothesis_id"},
            )
            resp.raise_for_status()
            return {r["hypothesis_id"] for r in (resp.json() or [])}
    except Exception as exc:
        logger.warning("Fetching active hypothesis ids failed for %s: %s", user_id[:8], exc)
        return set()


async def check_intervention_followups(user_id: str) -> None:
    """
    Best-effort — for every active intervention whose follow-up window has
    elapsed, compare the outcome metric's mean since it started against its
    pre-start baseline, mark it followed-up, and push the result. Called
    from daily_sync right after each sync so the check happens on real,
    fresh data rather than needing its own schedule.
    """
    from causal.interpreter import OUTCOME_HIGHER_IS_BETTER
    from utils.push import send_push

    today = date.today()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                _sb_url("active_interventions"),
                headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "status": "eq.active", "select": "*"},
            )
            resp.raise_for_status()
            active = resp.json() or []
    except Exception as exc:
        logger.warning("Fetching active interventions failed for %s: %s", user_id[:8], exc)
        return

    for iv in active:
        try:
            started = datetime.strptime(iv["started_date"], "%Y-%m-%d").date()
            due = started + timedelta(days=iv.get("follow_up_days") or FOLLOW_UP_DAYS_DEFAULT)
            if today < due:
                continue

            metric = base_metric(iv["outcome_col"])
            current_value = await _mean_metric(user_id, metric, iv["started_date"], today.isoformat())
            baseline_value = iv.get("baseline_value")

            result_improved = None
            if current_value is not None and baseline_value is not None:
                higher_is_better = OUTCOME_HIGHER_IS_BETTER.get(iv["outcome_col"], True)
                went_up = current_value > baseline_value
                result_improved = went_up if higher_is_better else not went_up

            async with httpx.AsyncClient(timeout=15) as client:
                await client.patch(
                    _sb_url("active_interventions"),
                    headers={**_sb_headers(), "Prefer": "return=minimal"},
                    params={"id": f"eq.{iv['id']}"},
                    json={
                        "status": "followed_up",
                        "result_value": current_value,
                        "result_improved": result_improved,
                    },
                )

            if current_value is not None and baseline_value is not None:
                unit = iv.get("metric_unit") or ""
                verdict = "improved" if result_improved else "didn't really change"
                body = (
                    f"{iv['treatment_label']} — {iv['outcome_label']} {verdict}: "
                    f"{round(baseline_value, 1)}{unit} → {round(current_value, 1)}{unit}"
                )
            else:
                body = f"Following up on {iv['treatment_label']} — not quite enough fresh data yet to say for sure."

            await send_push(
                user_id,
                title="Here's how it went",
                body=body,
                data={"kind": "intervention_followup", "intervention_id": iv["id"]},
            )
        except Exception as exc:
            logger.warning("Intervention follow-up failed for %s/%s: %s", user_id[:8], iv.get("id"), exc)

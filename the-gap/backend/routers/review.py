"""
GET /review/week — the weekly review shown on Home and in the review screen.

Reads the last 7 complete days (ending yesterday, on the phone's own calendar)
and the 7 before from tables that are already kept up to date, and hands the
numbers to utils/weekly_review.py to turn into a review. Nothing here calls
the AI service.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from auth import get_current_user_id
from db.supabase_client import get_latest_results
from routers.journal import _get_streak as _get_journal_streak
from utils.weekly_review import REVIEW_METRICS, build_review_payload, split_by_week

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/review", tags=["review"])

DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers() -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


async def _rows(client: httpx.AsyncClient, table: str, params) -> list[dict]:
    """A table read that never raises: a missing table or a hiccup just means no rows."""
    try:
        resp = await client.get(_sb_url(table), headers=_sb_headers(), params=params)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []
    except Exception as exc:
        logger.warning("Review read of %s failed: %s", table, exc)
        return []


async def build_review(user_id: str, today: date) -> dict:
    """The review for the 7 days ending the day before `today`."""
    end = today - timedelta(days=1)
    start = end - timedelta(days=6)
    prev_start = start - timedelta(days=7)
    s, e, ps = start.isoformat(), end.isoformat(), prev_start.isoformat()

    async with httpx.AsyncClient(timeout=15) as client:
        metric_rows, checkin_rows, workout_rows, food_rows, schedule_rows = await asyncio.gather(
            _rows(client, "metric_history", [
                ("user_id", f"eq.{user_id}"),
                ("metric", "in.(" + ",".join(m[0] for m in REVIEW_METRICS) + ")"),
                ("date", f"gte.{ps}"), ("date", f"lte.{e}"),
                ("select", "date,metric,value"), ("limit", "400"),
            ]),
            _rows(client, "daily_checkins", [
                ("user_id", f"eq.{user_id}"), ("date", f"gte.{s}"), ("date", f"lte.{e}"), ("select", "date"),
            ]),
            _rows(client, "workouts", [
                ("user_id", f"eq.{user_id}"), ("planned_date", f"gte.{s}"), ("planned_date", f"lte.{e}"),
                ("select", "planned_date,status"),
            ]),
            _rows(client, "food_log", [
                ("user_id", f"eq.{user_id}"), ("local_date", f"gte.{s}"), ("local_date", f"lte.{e}"), ("select", "local_date"),
            ]),
            _rows(client, "training_schedule", [("user_id", f"eq.{user_id}"), ("select", "days"), ("limit", "1")]),
        )

    this_week, last_week = split_by_week(metric_rows, s, e)

    planned_days = 0
    if schedule_rows:
        days = schedule_rows[0].get("days") or {}
        planned_days = sum(1 for i in range(7) if days.get(DAY_KEYS[(start + timedelta(days=i)).weekday()]) == "train")

    habits = {
        "checkins": len({r["date"] for r in checkin_rows if r.get("date")}),
        "workouts_done": sum(1 for r in workout_rows if r.get("status") == "completed"),
        "workouts_planned": max(planned_days, sum(1 for r in workout_rows if r.get("status") == "planned")),
        "food_days": len({r["local_date"] for r in food_rows if r.get("local_date")}),
    }

    try:
        streak = await _get_journal_streak(user_id)
    except Exception:
        streak = 0
    latest = await asyncio.to_thread(get_latest_results, user_id)
    insights = (latest or {}).get("insights") or []
    confirmed = sum(1 for i in insights if i.get("confidence") != "weak" and not i.get("is_private"))
    early = sum(1 for i in insights if i.get("confidence") == "weak" and not i.get("is_private"))

    return build_review_payload(this_week, last_week, habits, streak, confirmed, early, s, e)


@router.get("/week")
async def weekly_review(local_date: Optional[str] = None, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    # The phone's own date: the server runs on UTC, a different day for part of every day in Queensland.
    today = date.today()
    if local_date:
        try:
            today = datetime.strptime(local_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="local_date must be YYYY-MM-DD.")
    return JSONResponse(content=await build_review(user_id, today))

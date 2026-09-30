"""
Shared goal-progress computation — used by routers/goals.py (the live
progress bar) and routers/digest.py (the weekly recap line), so both read
the exact same numbers rather than computing them independently.
"""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta

import httpx

logger = logging.getLogger(__name__)

PROGRESS_WINDOW_DAYS = 7


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers() -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


async def _mean_metric(user_id: str, metric: str, since: str) -> float | None:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                _sb_url("metric_history"),
                headers=_sb_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "metric": f"eq.{metric}",
                    "date": f"gte.{since}",
                    "select": "value",
                },
            )
            resp.raise_for_status()
            rows = resp.json() or []
            if not rows:
                return None
            return sum(r["value"] for r in rows) / len(rows)
    except Exception as exc:
        logger.warning("Goal progress metric fetch failed for %s/%s: %s", user_id[:8], metric, exc)
        return None


async def compute_goal_progress(user_id: str, goal: dict) -> dict:
    """
    Returns {current_avg, baseline_value, target_value, direction,
    on_track} — current_avg is the mean of the last PROGRESS_WINDOW_DAYS
    days; on_track compares current_avg to target_value if set, else to
    baseline_value, using `direction` ('increase'|'decrease').
    """
    since = (date.today() - timedelta(days=PROGRESS_WINDOW_DAYS)).isoformat()
    current_avg = await _mean_metric(user_id, goal["metric_col"], since)

    baseline_value = goal.get("baseline_value")
    target_value = goal.get("target_value")
    direction = goal.get("direction", "increase")
    reference = target_value if target_value is not None else baseline_value

    on_track = None
    if current_avg is not None and reference is not None:
        on_track = current_avg >= reference if direction == "increase" else current_avg <= reference

    return {
        "current_avg": current_avg,
        "baseline_value": baseline_value,
        "target_value": target_value,
        "direction": direction,
        "on_track": on_track,
    }

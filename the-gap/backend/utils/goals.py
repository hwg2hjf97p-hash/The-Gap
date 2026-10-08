"""
Goals: how a goal's progress is measured, what targets are allowed, and when a
goal counts as reached. Shared by routers/goals.py (the Goals tab), the sync
(which marks goals reached) and routers/digest.py (the weekly recap line).

Progress is always a 7-day rolling average, never a single reading: one great
night shouldn't tick a goal off, and one bad one shouldn't undo a week. An
average only counts once enough of those 7 days have a reading (see
GoalMetric.min_points). Days are the person's own calendar days.

Safety: a weight goal needs a height on file, and a target that would put the
person's BMI under 18.5 is refused. No dates on weight goals, and no calorie or
rate-of-loss goals exist at all (see utils/goal_catalog.py).
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import httpx

from utils.goal_catalog import GoalMetric, get_metric
from utils.local_time import user_today

logger = logging.getLogger(__name__)

WINDOW_DAYS = 7
PROGRESS_WINDOW_DAYS = WINDOW_DAYS  # name used by older callers
MAX_ACTIVE_GOALS = 6
BMI_FLOOR = 18.5


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


# ── pure maths ───────────────────────────────────────────────────────────────

def bmi(weight_kg: float, height_cm: float) -> float:
    m = height_cm / 100.0
    return weight_kg / (m * m)


def lowest_weight_for_bmi(height_cm: float, floor: float = BMI_FLOOR) -> float:
    m = height_cm / 100.0
    return floor * m * m


def fmt(value: Optional[float], decimals: int = 0) -> str:
    if value is None:
        return "–"
    text = f"{value:,.{decimals}f}"
    if decimals:
        text = text.rstrip("0").rstrip(".")
    return text


def window_average(points: list[tuple[date, float]], today: date, metric: GoalMetric) -> tuple[Optional[float], int]:
    """(7-day average in display units, number of days with a reading); the average is None when there are too few days."""
    start = today - timedelta(days=WINDOW_DAYS - 1)
    values = [v for d, v in points if start <= d <= today and v == v]
    if len(values) < metric.min_points:
        return None, len(values)
    mean = sum(values) / len(values)
    if metric.per_week:
        mean *= 7
    return mean / metric.scale, len(values)


def reached(direction: str, current: float, target: float) -> bool:
    if direction == "increase":
        return current >= target - 1e-9
    if direction == "decrease":
        return current <= target + 1e-9
    return False  # "maintain" is a state to stay in, not something reached


def tolerance(metric: GoalMetric, target: float) -> float:
    return max(metric.step, 0.05 * abs(target))


def evaluate_goal(goal: dict, points: list[tuple[date, float]], today: date) -> dict:
    """
    {current, baseline, target, fraction, points, needed, state, direction}

    state: not_enough_data | building | achieved | holding | drifting
    fraction (0..1) is how far the average has moved from the baseline to the target.
    """
    metric = get_metric(goal.get("metric_col", ""))
    direction = goal.get("direction") or "increase"
    baseline = goal.get("baseline_value")
    target = goal.get("target_value")
    if metric is None:
        return {"current": None, "baseline": baseline, "target": target, "fraction": None, "points": 0, "needed": 0, "state": "not_enough_data", "direction": direction}

    current, n = window_average(points, today, metric)
    out = {"current": current, "baseline": baseline, "target": target, "fraction": None, "points": n, "needed": metric.min_points, "state": "not_enough_data", "direction": direction}
    if goal.get("status") == "achieved":
        out["state"] = "achieved"
        out["fraction"] = 1.0
        return out
    if current is None or target is None:
        return out

    if direction == "maintain":
        out["state"] = "holding" if abs(current - target) <= tolerance(metric, target) else "drifting"
        return out

    if reached(direction, current, target):
        out["state"] = "achieved"
        out["fraction"] = 1.0
        return out
    out["state"] = "building"
    if baseline is not None and abs(target - baseline) > 1e-9:
        out["fraction"] = max(0.0, min(1.0, (current - baseline) / (target - baseline)))
    return out


def validate_new_goal(
    metric: GoalMetric,
    direction: str,
    target: Optional[float],
    baseline: Optional[float],
    target_date: Optional[date],
    height_cm: Optional[float],
    today: date,
) -> Optional[dict]:
    """None when the goal is acceptable; otherwise {"code", "message"} explaining why not, in plain words."""
    if direction not in metric.directions:
        allowed = " or ".join(metric.directions)
        return {"code": "direction", "message": f"A goal on {metric.label.lower()} can be to {allowed}."}
    if target is None:
        return {"code": "target_needed", "message": "Pick a target."}
    if not (metric.minimum <= target <= metric.maximum):
        return {"code": "target_range", "message": f"Choose a target between {fmt(metric.minimum, metric.decimals)} and {fmt(metric.maximum, metric.decimals)} {metric.unit}."}

    if target_date is not None:
        if not metric.allow_target_date:
            return {"code": "no_date", "message": "Weight goals don't use dates. Go at the pace that suits you."}
        if target_date <= today:
            return {"code": "date_past", "message": "Pick a date in the future, or leave the date off."}

    if metric.needs_height:
        if not height_cm:
            return {"code": "height_needed", "message": "Add your height in Settings, under About you, so we can check a healthy range for a weight goal."}
        floor_kg = lowest_weight_for_bmi(height_cm)
        if target < floor_kg:
            return {
                "code": "bmi_floor",
                "message": f"That target is below the healthy range for your height. Choose {fmt(floor_kg + 0.05, 1)} kg or more, or talk with your doctor about a healthy weight for you.",
            }

    if direction != "maintain":
        if baseline is None:
            return {"code": "no_baseline", "message": f"We need at least {metric.min_points} days of {metric.label.lower()} in the last week before we can set this goal. Check your device is syncing, then try again."}
        if direction == "increase" and target <= baseline:
            return {"code": "target_side", "message": f"Your 7-day average is already {fmt(baseline, metric.decimals)} {metric.unit}. Pick a target above it, or choose Keep it steady."}
        if direction == "decrease" and target >= baseline:
            return {"code": "target_side", "message": f"Your 7-day average is already {fmt(baseline, metric.decimals)} {metric.unit}. Pick a target below it, or choose Keep it steady."}
    return None


# ── database access ──────────────────────────────────────────────────────────

async def fetch_points(user_id: str, metric_key: str, since: date) -> list[tuple[date, float]]:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                _sb_url("metric_history"),
                headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "metric": f"eq.{metric_key}", "date": f"gte.{since.isoformat()}", "select": "date,value", "order": "date.asc"},
            )
            resp.raise_for_status()
            return [(date.fromisoformat(r["date"]), float(r["value"])) for r in (resp.json() or []) if r.get("value") is not None]
    except Exception as exc:
        logger.warning("Goal history fetch failed for %s/%s: %s", user_id[:8], metric_key, exc)
        return []


async def current_average(user_id: str, metric_key: str, today: Optional[date] = None) -> tuple[Optional[float], int]:
    metric = get_metric(metric_key)
    if metric is None:
        return None, 0
    today = today or await user_today(user_id)
    points = await fetch_points(user_id, metric_key, today - timedelta(days=WINDOW_DAYS - 1))
    return window_average(points, today, metric)


async def goal_progress(user_id: str, goal: dict, today: Optional[date] = None) -> dict:
    today = today or await user_today(user_id)
    points = await fetch_points(user_id, goal.get("metric_col", ""), today - timedelta(days=WINDOW_DAYS - 1))
    return evaluate_goal(goal, points, today)


async def compute_goal_progress(user_id: str, goal: dict) -> dict:
    """The progress block the app and the weekly recap read. Keeps the older keys (current_avg, on_track) alongside the new ones."""
    p = await goal_progress(user_id, goal)
    on_track = None
    if p["state"] in ("achieved", "holding"):
        on_track = True
    elif p["state"] == "drifting":
        on_track = False
    elif p["state"] == "building" and p["current"] is not None and p["target"] is not None:
        on_track = p["current"] >= p["target"] if p["direction"] == "increase" else p["current"] <= p["target"]
    return {**p, "current_avg": p["current"], "baseline_value": p["baseline"], "target_value": p["target"], "on_track": on_track}


async def get_height_cm(user_id: str) -> Optional[float]:
    from sync.user_profile_store import get_user_profile

    try:
        profile = await get_user_profile(user_id)
    except Exception:
        return None
    height = (profile or {}).get("height_cm")
    return float(height) if height else None


async def list_goals(user_id: str, status: Optional[str] = None) -> list[dict]:
    params = {"user_id": f"eq.{user_id}", "select": "*", "order": "created_at.desc"}
    if status:
        params["status"] = f"eq.{status}"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(_sb_url("user_goals"), headers=_sb_headers(), params=params)
        resp.raise_for_status()
        return resp.json() or []


async def _create_feed_item(user_id: str, goal: dict, current: float, metric: GoalMetric, today: date) -> None:
    from utils.feed import create_feed_item

    baseline = goal.get("baseline_value")
    unit = f" {metric.unit}" if metric.unit and not metric.unit.startswith("/") else metric.unit
    body = f"Your 7-day average reached {fmt(current, metric.decimals)}{unit}."
    if baseline is not None:
        body += f" You started at {fmt(baseline, metric.decimals)}{unit} and set out for {fmt(goal.get('target_value'), metric.decimals)}{unit}."
    await create_feed_item(
        user_id,
        kind="goal_achieved",
        goal_id=goal["id"],
        title=f"Goal reached: {goal.get('metric_label') or metric.label}",
        body=body,
        payload={"metric_key": metric.key, "baseline": baseline, "current": round(current, 2), "target": goal.get("target_value"), "unit": metric.unit},
        local_date=today,
    )


async def check_goal_achievements(user_id: str) -> list[dict]:
    """
    Marks any active goal whose 7-day average has reached its target as
    achieved, and posts a celebration card to the person's feed. Safe to call
    as often as wanted: a goal can only become achieved once. Never raises.
    """
    achieved: list[dict] = []
    try:
        goals = [g for g in await list_goals(user_id, "active") if g.get("direction") != "maintain" and g.get("target_value") is not None]
        if not goals:
            return []
        today = await user_today(user_id)
        for goal in goals:
            metric = get_metric(goal.get("metric_col", ""))
            if metric is None:
                continue
            p = await goal_progress(user_id, goal, today)
            if p["state"] != "achieved" or p["current"] is None:
                continue
            async with httpx.AsyncClient(timeout=15) as client:
                # Only moves a goal that is still active, so two overlapping checks can't both celebrate it.
                resp = await client.patch(
                    _sb_url("user_goals"),
                    headers=_sb_headers("return=representation"),
                    params={"id": f"eq.{goal['id']}", "user_id": f"eq.{user_id}", "status": "eq.active"},
                    json={"status": "achieved", "achieved_at": datetime.now(timezone.utc).isoformat()},
                )
                resp.raise_for_status()
                moved = resp.json() or []
            if not moved:
                continue
            achieved.append(goal)
            await _create_feed_item(user_id, goal, p["current"], metric, today)
            logger.info("GOAL_ACHIEVED user=%s metric=%s", user_id[:8], metric.key)
    except Exception as exc:
        logger.warning("Goal achievement check failed for %s: %s", user_id[:8], exc)
    return achieved

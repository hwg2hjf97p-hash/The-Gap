"""
Health plan — the overall suggestion at the top of the "Your Health" tab, and
the weekly workout schedule it takes into account.

Two layers, deliberately separate:
  1. Rules decide WHAT to suggest (train / rest / go light / optional
     session, plus any nutrition nudges), from the person's own schedule,
     their recovery compared with their own 30-day normal (routers/readiness
     .py), whether they've already worked out, and how today's food and water
     are going against their goals. The rules never guess: no data means no
     claim.
  2. Claude only PHRASES the decision, from the facts the rules produced, so
     the wording varies and reads naturally. If Claude is unavailable (or its
     daily cap for the person is reached) a plain written fallback is used,
     so the card always works. General guidance, not medical advice.

Table DDL (run once in the Supabase SQL editor — see phase2.sql):
  CREATE TABLE IF NOT EXISTS training_schedule (
    user_id TEXT PRIMARY KEY,
    days JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ DEFAULT NOW()
  );
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth import get_current_user_id
from routers.readiness import compute_readiness

from utils.consent import ai_allowed  # noqa: E402

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/health-plan", tags=["health-plan"])

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"

DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]  # date.weekday(): Monday == 0

TEXT_CACHE_SECONDS = 12 * 3600
MAX_GENERATIONS_PER_DAY = 15
_text_cache: dict[str, tuple[float, str]] = {}
_generation_count: dict[tuple[str, str], int] = {}


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


# ── Weekly schedule ──────────────────────────────────────────────────────────

class ScheduleBody(BaseModel):
    days: dict[str, Optional[Literal["train", "rest"]]]


def _clean_days(days: dict) -> dict:
    return {k: days.get(k) if days.get(k) in ("train", "rest") else None for k in DAY_KEYS}


async def _load_schedule(client: httpx.AsyncClient, user_id: str) -> Optional[dict]:
    """The saved week, or None if there isn't one (or the table isn't there yet)."""
    try:
        resp = await client.get(
            _sb_url("training_schedule"), headers=_sb_headers(),
            params={"user_id": f"eq.{user_id}", "select": "days", "limit": "1"},
        )
        resp.raise_for_status()
        rows = resp.json() or []
        return _clean_days(rows[0].get("days") or {}) if rows else None
    except Exception as exc:
        logger.warning("Loading training schedule failed for %s: %s", user_id[:8], exc)
        return None


@router.get("/schedule")
async def get_schedule(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    async with httpx.AsyncClient(timeout=15) as client:
        days = await _load_schedule(client, user_id)
    return JSONResponse(content={"days": days})


@router.put("/schedule")
async def put_schedule(body: ScheduleBody, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    days = _clean_days(body.days)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _sb_url("training_schedule"),
                headers=_sb_headers("resolution=merge-duplicates,return=minimal"),
                params={"on_conflict": "user_id"},
                json={"user_id": user_id, "days": days, "updated_at": datetime.now(timezone.utc).isoformat()},
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.error("Saving training schedule failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Couldn't save your schedule — please try again.")
    return JSONResponse(content={"days": days})


# ── Facts gathering ──────────────────────────────────────────────────────────

async def _completed_workout_dates(client: httpx.AsyncClient, user_id: str, since: date, until: date) -> set[str]:
    try:
        resp = await client.get(
            _sb_url("workouts"), headers=_sb_headers(),
            params=[
                ("user_id", f"eq.{user_id}"),
                ("status", "eq.completed"),
                ("planned_date", f"gte.{since.isoformat()}"),
                ("planned_date", f"lte.{until.isoformat()}"),
                ("select", "planned_date"),
            ],
        )
        resp.raise_for_status()
        return {r["planned_date"] for r in (resp.json() or [])}
    except Exception as exc:
        logger.warning("Workout lookup failed for %s: %s", user_id[:8], exc)
        return set()


async def _average_steps(client: httpx.AsyncClient, user_id: str, today: date) -> Optional[float]:
    try:
        resp = await client.get(
            _sb_url("metric_history"), headers=_sb_headers(),
            params=[
                ("user_id", f"eq.{user_id}"),
                ("metric", "eq.steps"),
                ("date", f"gte.{(today - timedelta(days=30)).isoformat()}"),
                ("date", f"lt.{today.isoformat()}"),
                ("select", "value"),
                ("limit", "60"),
            ],
        )
        resp.raise_for_status()
        values = [float(r["value"]) for r in (resp.json() or []) if r.get("value") and float(r["value"]) > 0]
        return sum(values) / len(values) if len(values) >= 7 else None
    except Exception as exc:
        logger.warning("Steps average failed for %s: %s", user_id[:8], exc)
        return None


async def _nutrition_today(client: httpx.AsyncClient, user_id: str, today: date) -> dict:
    out = {"calories": 0.0, "protein_g": 0.0, "water_ml": 0.0, "goals": {}}
    day = today.isoformat()
    try:
        food, water, goals = await asyncio.gather(
            client.get(_sb_url("food_log"), headers=_sb_headers(),
                       params={"user_id": f"eq.{user_id}", "local_date": f"eq.{day}", "select": "calories,protein_g"}),
            client.get(_sb_url("water_log"), headers=_sb_headers(),
                       params={"user_id": f"eq.{user_id}", "local_date": f"eq.{day}", "select": "amount_ml"}),
            client.get(_sb_url("nutrition_goals"), headers=_sb_headers(),
                       params={"user_id": f"eq.{user_id}", "select": "calorie_goal,protein_goal_g,water_goal_ml", "limit": "1"}),
        )
        for r in food.json() or []:
            out["calories"] += float(r.get("calories") or 0)
            out["protein_g"] += float(r.get("protein_g") or 0)
        for r in water.json() or []:
            out["water_ml"] += float(r.get("amount_ml") or 0)
        grows = goals.json() or []
        out["goals"] = grows[0] if grows else {}
    except Exception as exc:
        logger.warning("Nutrition lookup failed for %s: %s", user_id[:8], exc)
    return out


# ── Decisions (rules) ────────────────────────────────────────────────────────

HEADLINES = {
    "done": "Nice work today",
    "rest": "Rest day",
    "rest_but_ready": "Rest day, but you're primed",
    "train": "Train today",
    "train_controlled": "Train, but keep it controlled",
    "train_easy": "Go light today",
    "train_unknown": "Training day",
    "train_suggested": "Good day to train",
    "rest_suggested": "Take it easy today",
    "no_plan": "Today's plan",
}
WORKOUT_BUTTON_ACTIONS = {"train", "train_controlled", "train_easy", "train_unknown", "train_suggested", "rest_but_ready"}


def _round_steps(value: float) -> int:
    return int(round(value / 500.0) * 500)


def _decide_training(planned: Optional[str], level: str, signals: dict, trained_today: bool, trained_yesterday: bool) -> str:
    if trained_today:
        return "done"
    hrv_pct, sleep_pct = signals.get("hrv_pct"), signals.get("sleep_pct")
    # "Strong" = high recovery with nothing known to be below their normal.
    strong = level == "high" and (hrv_pct is None or hrv_pct >= 0) and (sleep_pct is None or sleep_pct >= 0)
    if planned == "rest":
        return "rest_but_ready" if strong and not trained_yesterday else "rest"
    if planned == "train":
        return {"low": "train_easy", "moderate": "train_controlled", "high": "train"}.get(level, "train_unknown")
    if level == "high":
        return "train_suggested"
    if level == "low":
        return "rest_suggested"
    return "no_plan"


def _nutrition_flags(nutrition: dict, hour: int) -> list[str]:
    goals = nutrition.get("goals") or {}
    pace = min(1.0, max(0.0, (hour - 7) / 14.0))  # 0 at 7am, 1 at 9pm
    flags: list[str] = []
    if hour >= 13 and nutrition["calories"] < 100:
        return ["nothing_logged"]
    protein_goal, water_goal, calorie_goal = goals.get("protein_goal_g"), goals.get("water_goal_ml"), goals.get("calorie_goal")
    if protein_goal and hour >= 14 and nutrition["protein_g"] < protein_goal * pace * 0.75:
        flags.append("protein_behind")
    if water_goal and hour >= 12 and nutrition["water_ml"] < water_goal * pace * 0.75:
        flags.append("water_behind")
    if calorie_goal and hour >= 19 and nutrition["calories"] < calorie_goal * 0.6:
        flags.append("calories_low")
    return flags


def _part_of_day(hour: int) -> str:
    return "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"


# ── Wording ──────────────────────────────────────────────────────────────────

_TRAINING_FALLBACK = {
    "done": "You've trained today. Focus on food, water and sleep so it pays off.",
    "rest": "Rest day today. Keep moving lightly{steps}.",
    "rest_but_ready": "Rest day planned, but you didn't log a workout yesterday and your recovery looks strong, so a steady session would suit you today.",
    "train": "Train today. Your recovery looks good for it.",
    "train_controlled": "Train today, but keep it controlled and leave a rep or two in reserve.",
    "train_easy": "Your recovery is low today. Go light or swap in an easy session or a walk.",
    "train_unknown": "Training day today. Listen to how you feel as you warm up.",
    "train_suggested": "Your recovery looks strong, so today would be a good day for a session.",
    "rest_suggested": "Your recovery is on the low side today. Take it easy and keep movement light.",
    "no_plan": "Set your workout days below and this card will plan around them.",
}
_NUTRITION_FALLBACK = {
    "nothing_logged": "Log what you've eaten so far so your day adds up.",
    "protein_behind": "Aim for some extra protein",
    "water_behind": "drink more water",
    "calories_low": "you're well under your calorie goal, so make sure you eat enough",
}


def _fallback_text(action: str, steps_range: Optional[list[int]], flags: list[str]) -> str:
    steps = f" (around {steps_range[0]:,}-{steps_range[1]:,} steps)" if steps_range else ""
    text = _TRAINING_FALLBACK[action].format(steps=steps)
    if "nothing_logged" in flags:
        return f"{text} {_NUTRITION_FALLBACK['nothing_logged']}"
    parts = [_NUTRITION_FALLBACK[f] for f in flags if f in ("protein_behind", "water_behind")]
    if parts:
        joined = parts[0] if len(parts) == 1 else f"{parts[0]} and {parts[1]}"
        text = f"{text} {joined[0].upper()}{joined[1:]} today."
    return text


SYSTEM_PROMPT = """You write the daily suggestion card at the top of a health app called The Gap. A set of rules has already decided what to suggest; your job is only to put it into natural words.

Rules:
- Use ONLY the facts given. Never invent a number, a reason or a fact that isn't in them.
- At most 2 short sentences, under 45 words in total.
- Lead with the training decision ("decision") in your own words and give the reason in plain language (for example that their HRV is above their own average). Only mention recovery data that appears in "recovery_notes".
- If "rest_day_step_range" is given, mention it as a light-movement target.
- Mention nutrition only if "nutrition_flags" is not empty, and only the flagged items, in one short clause. "nothing_logged" means they haven't logged food yet today.
- Warm, direct, never preachy or guilt-inducing. No emojis, no markdown. Vary your phrasing from day to day.
- Never diagnose and never give medical advice.

Examples of the style (do not copy them word for word):
"Rest day today. Aim for light movement, around 4,500-5,500 steps."
"Train today, your HRV is above your average. Eat more protein and drink more water to stay on track."

Respond with ONLY the suggestion text."""


async def _claude_text(user_id: str, today: date, facts: dict) -> Optional[str]:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return None
    if not await ai_allowed(user_id):
        return None  # AI is off for this person: the plain written version is used
    count_key = (user_id, today.isoformat())
    if _generation_count.get(count_key, 0) >= MAX_GENERATIONS_PER_DAY:
        return None
    _generation_count[count_key] = _generation_count.get(count_key, 0) + 1
    if len(_generation_count) > 5000:  # forget old days
        for k in [k for k in _generation_count if k[1] != today.isoformat()]:
            _generation_count.pop(k, None)
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.post(
                ANTHROPIC_API_URL,
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={
                    "model": MODEL,
                    "max_tokens": 160,
                    "system": SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": "Facts:\n" + json.dumps(facts, indent=1)}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip().strip('"')
        return text if 10 <= len(text) <= 400 else None
    except Exception as exc:
        logger.warning("Health plan wording failed for %s: %s", user_id[:8], exc)
        return None


# ── Endpoint ─────────────────────────────────────────────────────────────────

@router.get("/today")
async def plan_today(
    local_date: Optional[str] = None,
    local_hour: Optional[int] = None,
    user_id: str = Depends(get_current_user_id),
) -> JSONResponse:
    # The phone's own date and hour: the server runs on UTC, which is a
    # different calendar day (and hour) from Queensland for much of every day.
    today = date.today()
    if local_date:
        try:
            today = datetime.strptime(local_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="local_date must be YYYY-MM-DD.")
    hour = local_hour if local_hour is not None and 0 <= local_hour <= 23 else datetime.now().hour

    async with httpx.AsyncClient(timeout=15) as client:
        readiness, schedule, workout_dates, avg_steps, nutrition = await asyncio.gather(
            compute_readiness(user_id, today),
            _load_schedule(client, user_id),
            _completed_workout_dates(client, user_id, today - timedelta(days=1), today),
            _average_steps(client, user_id, today),
            _nutrition_today(client, user_id, today),
        )

    planned = (schedule or {}).get(DAY_KEYS[today.weekday()])
    level = readiness.get("level", "unknown")
    signals = readiness.get("signals") or {}
    trained_today = today.isoformat() in workout_dates
    trained_yesterday = (today - timedelta(days=1)).isoformat() in workout_dates

    action = _decide_training(planned, level, signals, trained_today, trained_yesterday)

    steps_range: Optional[list[int]] = None
    if action in ("rest", "rest_suggested") and avg_steps:
        low, high = max(2000, _round_steps(avg_steps * 0.55)), max(3000, _round_steps(avg_steps * 0.75))
        if high > low:
            steps_range = [low, high]

    flags = _nutrition_flags(nutrition, hour)
    goals = nutrition.get("goals") or {}

    facts = {
        "decision": action.replace("_", " "),
        "planned_today": planned or "not set",
        "recovery_level": level,
        "recovery_notes": readiness.get("reasons") or [],
        "workout_logged_yesterday": trained_yesterday,
        "workout_logged_today": trained_today,
        "rest_day_step_range": steps_range,
        "time_of_day": _part_of_day(hour),
        "nutrition_flags": flags,
        "protein_so_far_g": round(nutrition["protein_g"]),
        "protein_goal_g": goals.get("protein_goal_g"),
        "water_so_far_ml": round(nutrition["water_ml"]),
        "water_goal_ml": goals.get("water_goal_ml"),
    }

    # Same facts => same wording, so the card doesn't reword itself (or cost
    # a model call) every time the screen is opened.
    signature = hashlib.sha1(json.dumps([today.isoformat(), facts], sort_keys=True, default=str).encode()).hexdigest()[:16]
    cache_key = f"{user_id}:{signature}"
    cached = _text_cache.get(cache_key)
    text, generated_by = None, "template"
    if cached and time.time() - cached[0] < TEXT_CACHE_SECONDS:
        text, generated_by = cached[1], "claude"
    else:
        text = await _claude_text(user_id, today, facts)
        if text:
            generated_by = "claude"
            if len(_text_cache) > 3000:
                _text_cache.clear()
            _text_cache[cache_key] = (time.time(), text)
    if not text:
        text = _fallback_text(action, steps_range, flags)

    return JSONResponse(content={
        "headline": HEADLINES[action],
        "text": text,
        "action": action,
        "planned": planned,
        "level": level,
        "reasons": (readiness.get("reasons") or [])[:4],
        "show_workout_button": action in WORKOUT_BUTTON_ACTIONS,
        "steps_range": steps_range,
        "nutrition_flags": flags,
        "schedule_set": schedule is not None and any(schedule.values()),
        "generated_by": generated_by,
    })

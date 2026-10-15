"""
Heads-ups: a coach with a light touch.

Short messages built from where today is compared with the person's own usual
(their last two weeks), such as "16,000 steps already, 60% over your usual".
They are not insights: nothing here is tested for cause and effect. When the
engine has found a pattern for this person (say big step days and next-morning
HRV), the message mentions it, worded as "has tended to". Otherwise it sticks to
the numbers and a sensible easy-evening kind of suggestion.

Kept calm on purpose: a handful of kinds, each with a "real change" bar rather than
any small wobble, one card per kind per day, at most ONE push a day, never during
quiet hours (send_push holds it), never anything about substances or gambling, and
no medical advice. The wording is plain templates (no AI, no cost) with a few
variants so it doesn't read the same every day.

Table DDL: see phase13.sql (headsups, notification_prefs.headsups_enabled).
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import date, datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import httpx
import pandas as pd

from utils.local_time import DEFAULT_TZ

logger = logging.getLogger(__name__)

BASELINE_DAYS = 14
MIN_BASELINE_DAYS = 7
PUSH_START_HOUR = 8.0
PUSH_END_HOUR = 20.5
RECOVERY_GOAL_COLS = {"hrv", "recovery_score", "resting_hr", "sleep_total_min"}


# ── small helpers ────────────────────────────────────────────────────────────

def _num(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number != number else number


def _pick(options: list[str], seed: str) -> str:
    """A stable choice per person and day, so it varies from day to day but never flips within a day."""
    index = int(hashlib.sha256(seed.encode()).hexdigest(), 16) % len(options)
    return options[index]


def _int(n: float) -> str:
    return f"{round(n):,}"


def _duration(minutes: float) -> str:
    total = int(round(minutes))
    hours, mins = divmod(total, 60)
    return f"{hours}h {mins:02d}m" if hours else f"{mins}m"


def _insight_for(insights: list[dict], treatment: str, outcome: str) -> Optional[dict]:
    for insight in insights or []:
        if insight.get("treatment_col") == treatment and insight.get("outcome_col") == outcome and not insight.get("is_private"):
            return insight
    return None


def baseline_for(df: pd.DataFrame, day: date, columns: list[str]) -> dict[str, float]:
    """The person's usual for each column: the mean of the days before `day`, when there are enough of them."""
    out: dict[str, float] = {}
    if df is None or df.empty:
        return out
    index = pd.to_datetime(df.index).normalize()
    previous = df[(index < pd.Timestamp(day)) & (index >= pd.Timestamp(day) - pd.Timedelta(days=BASELINE_DAYS))]
    for col in columns:
        if col in previous.columns:
            values = pd.to_numeric(previous[col], errors="coerce").dropna()
            if len(values) >= MIN_BASELINE_DAYS:
                out[col] = float(values.mean())
    return out


def today_values(df: pd.DataFrame, day: date, columns: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    if df is None or df.empty:
        return out
    index = pd.to_datetime(df.index).normalize()
    rows = df[index == pd.Timestamp(day)]
    if rows.empty:
        return out
    row = rows.iloc[-1]
    for col in columns:
        if col in row.index:
            value = _num(row[col])
            if value is not None:
                out[col] = value
    return out


# ── the rules ────────────────────────────────────────────────────────────────

def build_headsups(
    *,
    today: dict[str, float],
    usual: dict[str, float],
    hour: float,
    day: date,
    user_key: str = "",
    nutrition: Optional[dict] = None,
    nutrition_goals: Optional[dict] = None,
    insights: Optional[list[dict]] = None,
    goal_cols: Optional[set[str]] = None,
) -> list[dict]:
    """
    The heads-ups that apply right now. `today` and `usual` hold steps, sleep_total_min, strain; `nutrition`
    holds water_ml and protein_g so far today; `hour` is the person's local hour (e.g. 15.5).
    """
    items: list[dict] = []
    seed = f"{user_key}:{day.isoformat()}"
    goal_clause = " and it keeps your recovery goal on track" if (goal_cols or set()) & RECOVERY_GOAL_COLS else ""

    # Big step day
    steps, usual_steps = today.get("steps"), usual.get("steps")
    if steps and usual_steps and hour >= 10 and steps >= 6000 and steps >= max(usual_steps * 1.3, usual_steps + 2500):
        pct = round((steps / usual_steps - 1) * 100)
        extra = steps - usual_steps
        pattern = ""
        insight = _insight_for(insights or [], "steps", "hrv_next")
        if insight and insight.get("ate") is not None:
            sure = insight.get("confidence") in ("moderate", "strong")
            verb = "has tended to" if sure else "has seemed to"
            expected = float(insight["ate"]) * (extra / 2000.0)
            if expected <= -1.0:
                pattern = f" On big step days your next-morning HRV {verb} dip, by about {abs(expected):.0f} ms."
            elif expected >= 1.0:
                pattern = f" On big step days your next-morning HRV {verb} hold up well."
        opener = _pick(["Look at you go.", "Okay, step machine.", "Those legs have been busy.", "Big mover alert."], seed + "steps_high")
        advice = _pick([
            f"Go easy tonight and get to bed early; recovery is where the gains get made{goal_clause}.",
            f"Treat tonight like a cooldown lap: easy evening, early night{goal_clause}.",
            f"Your body just did a lot. Pay it back with an early night{goal_clause}.",
        ], seed + "steps_advice")
        items.append({
            "kind": "steps_high",
            "title": "Big step day",
            "body": f"{opener} {_int(steps)} steps so far is {pct}% over your usual {_int(usual_steps)}.{pattern} {advice}",
            "tone": "easy", "priority": 80, "push": True, "window": (11.0, 20.5),
        })

    # Quiet day (cards only)
    if steps is not None and usual_steps and usual_steps >= 4000 and hour >= 17 and steps < usual_steps * 0.55:
        pct = round(steps / usual_steps * 100)
        items.append({
            "kind": "steps_low",
            "title": "Quiet day",
            "body": _pick([
                f"Only {_int(steps)} steps so far, about {pct}% of your usual. A ten-minute lap around the block would do you good. No pressure.",
                f"{_int(steps)} steps today, {pct}% of your usual pace. A short walk after dinner is an easy win.",
            ], seed + "steps_low"),
            "tone": "nudge", "priority": 40, "push": False,
        })

    # Short night
    sleep, usual_sleep = today.get("sleep_total_min"), usual.get("sleep_total_min")
    if sleep and usual_sleep and 6 <= hour < 17 and sleep <= usual_sleep - 60 and sleep <= 405:
        items.append({
            "kind": "sleep_short",
            "title": "Short night",
            "body": _pick([
                f"Short night: {_duration(sleep)}, which is {_duration(usual_sleep - sleep)} under your usual {_duration(usual_sleep)}. Be kind to yourself today. Easy effort, plenty of water, earlier night tonight.",
                f"Only {_duration(sleep)} of sleep, {_duration(usual_sleep - sleep)} short of your usual. Go gentle today and book yourself an early one tonight{goal_clause}.",
                f"{_duration(sleep)} of sleep, so you're running a bit low on battery. Keep today's effort easy and aim for bed early tonight{goal_clause}.",
            ], seed + "sleep_short"),
            "tone": "easy", "priority": 70, "push": True, "window": (8.0, 11.5),
        })

    # Big training day
    strain, usual_strain = today.get("strain"), usual.get("strain")
    if strain and usual_strain and hour >= 11 and strain >= 14 and strain >= max(usual_strain * 1.3, usual_strain + 3):
        items.append({
            "kind": "strain_high",
            "title": "Big training day",
            "body": f"Strain {strain:.1f} today, well above your usual {usual_strain:.1f}. Eat properly, drink up, and get to bed early so tomorrow's recovery has something to work with{goal_clause}.",
            "tone": "easy", "priority": 75, "push": True, "window": (14.0, 20.5),
        })

    nutrition = nutrition or {}
    goals = nutrition_goals or {}

    # Water behind (cards only: water reminders already exist)
    water, water_goal = nutrition.get("water_ml"), goals.get("water_goal_ml")
    if water_goal and hour >= 14:
        target = 0.4 if hour < 18 else 0.6
        if (water or 0) < water_goal * target:
            pct = round((water or 0) / water_goal * 100)
            items.append({
                "kind": "water_behind",
                "title": "Water check",
                "body": _pick([
                    f"{_int(water or 0)} ml down, {pct}% of today's {_int(water_goal)} ml goal. Your water bottle is feeling neglected. Big glass now, another with dinner.",
                    f"Water check: {_int(water or 0)} ml so far, {pct}% of your {_int(water_goal)} ml goal. Top up now and you'll thank yourself tonight.",
                ], seed + "water_behind"),
                "tone": "nudge", "priority": 50, "push": False,
            })

    # Protein behind (cards only)
    protein, protein_goal = nutrition.get("protein_g"), goals.get("protein_goal_g")
    if protein_goal and hour >= 17 and (protein or 0) < protein_goal * 0.5:
        pct = round((protein or 0) / protein_goal * 100)
        items.append({
            "kind": "protein_behind",
            "title": "Protein check",
            "body": _pick([
                f"{_int(protein or 0)} g of protein so far, {pct}% of your {_int(protein_goal)} g goal. Dinner is your chance to catch up. Make it a protein-forward one.",
                f"Protein's running behind: {_int(protein or 0)} g so far, {pct}% of your {_int(protein_goal)} g goal. Plan a proper protein hit for dinner.",
            ], seed + "protein_behind"),
            "tone": "nudge", "priority": 45, "push": False,
        })

    items.sort(key=lambda i: -i["priority"])
    return items


# ── storing, showing and pushing them ────────────────────────────────────────

def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


async def headsups_enabled(user_id: str) -> bool:
    """On unless the person switched it off (and on if that can't be read: the default is on)."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _sb_url("notification_prefs"), headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "select": "headsups_enabled", "limit": "1"},
            )
            resp.raise_for_status()
            rows = resp.json() or []
    except Exception:
        return True
    return not (rows and rows[0].get("headsups_enabled") is False)


async def _nutrition_today(user_id: str, local_date: str) -> dict:
    out: dict = {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            water = await client.get(_sb_url("water_log"), headers=_sb_headers(), params={"user_id": f"eq.{user_id}", "local_date": f"eq.{local_date}", "select": "amount_ml"})
            water.raise_for_status()
            out["water_ml"] = sum(float(r.get("amount_ml") or 0) for r in (water.json() or []))
            food = await client.get(_sb_url("food_log"), headers=_sb_headers(), params={"user_id": f"eq.{user_id}", "local_date": f"eq.{local_date}", "select": "protein_g"})
            food.raise_for_status()
            out["protein_g"] = sum(float(r.get("protein_g") or 0) for r in (food.json() or []))
    except Exception as exc:
        logger.warning("Today's nutrition for heads-ups failed for %s: %s", user_id[:8], exc)
    return out


async def _nutrition_goals(user_id: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(_sb_url("nutrition_goals"), headers=_sb_headers(), params={"user_id": f"eq.{user_id}", "select": "protein_goal_g,water_goal_ml", "limit": "1"})
            resp.raise_for_status()
            rows = resp.json() or []
            return rows[0] if rows else {}
    except Exception:
        return {}


async def _save(user_id: str, local_date: str, items: list[dict]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        {"user_id": user_id, "headsup_date": local_date, "kind": i["kind"], "title": i["title"], "body": i["body"], "tone": i["tone"], "priority": i["priority"], "updated_at": now}
        for i in items
    ]
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            _sb_url("headsups"),
            headers=_sb_headers("resolution=merge-duplicates,return=minimal"),
            params={"on_conflict": "user_id,headsup_date,kind"},
            json=rows,
        )
        resp.raise_for_status()


async def _todays_rows(user_id: str, local_date: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            _sb_url("headsups"), headers=_sb_headers(),
            params={"user_id": f"eq.{user_id}", "headsup_date": f"eq.{local_date}", "select": "id,kind,title,body,pushed_at,dismissed_at,priority"},
        )
        resp.raise_for_status()
        return resp.json() or []


def choose_push(items: list[dict], rows: list[dict], hour: float) -> Optional[dict]:
    """The one heads-up worth a push right now, or None: nothing pushed yet today, not dismissed, inside its window."""
    if any(r.get("pushed_at") for r in rows):
        return None
    dismissed = {r["kind"] for r in rows if r.get("dismissed_at")}
    for item in items:  # already highest priority first
        start, end = item.get("window", (PUSH_START_HOUR, PUSH_END_HOUR))
        if item.get("push") and item["kind"] not in dismissed and start <= hour <= end:
            return item
    return None


async def run_headsups(user_id: str, df: pd.DataFrame, insights: list[dict]) -> int:
    """Called after each sync. Works out today's heads-ups, stores them, and sends at most one push. Never raises."""
    try:
        if not await headsups_enabled(user_id):
            return 0
        from utils.push import get_prefs, send_push

        prefs = await get_prefs(user_id)
        try:
            tz = ZoneInfo((prefs or {}).get("tz") or DEFAULT_TZ)
        except Exception:
            tz = ZoneInfo(DEFAULT_TZ)
        local_now = datetime.now(timezone.utc).astimezone(tz)
        day = local_now.date()
        hour = local_now.hour + local_now.minute / 60.0

        columns = ["steps", "sleep_total_min", "strain"]
        today = today_values(df, day, columns)
        usual = baseline_for(df, day, columns)
        nutrition = await _nutrition_today(user_id, day.isoformat())
        goals = await _nutrition_goals(user_id)
        goal_cols: set[str] = set()
        try:
            from utils.goals import list_goals

            goal_cols = {str(g["metric_col"]) for g in await list_goals(user_id, "active") if g.get("metric_col")}
        except Exception:
            pass

        items = build_headsups(
            today=today, usual=usual, hour=hour, day=day, user_key=user_id[:8],
            nutrition=nutrition, nutrition_goals=goals, insights=insights, goal_cols=goal_cols,
        )
        if not items:
            return 0
        await _save(user_id, day.isoformat(), items)

        rows = await _todays_rows(user_id, day.isoformat())
        chosen = choose_push(items, rows, hour)
        if chosen:
            await send_push(user_id, chosen["title"], chosen["body"], data={"kind": "headsup", "headsup_kind": chosen["kind"]})
            row = next((r for r in rows if r["kind"] == chosen["kind"]), None)
            if row:
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.patch(
                        _sb_url("headsups"), headers=_sb_headers("return=minimal"),
                        params={"id": f"eq.{row['id']}"}, json={"pushed_at": datetime.now(timezone.utc).isoformat()},
                    )
        return len(items)
    except Exception as exc:
        logger.warning("Heads-ups failed for %s (continuing): %s", user_id[:8], exc)
        return 0

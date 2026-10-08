"""
Choosing which approved research cards to put in a person's feed.

Rules:
  - Only approved cards (utils/evidence.py reads nothing else).
  - A card must speak to one of the person's active goals (its metric_tags
    include the goal's metric).
  - Never a card shown to them in the last 60 days.
  - At most two cards per round, and a round at most every two days. A round
    prefers one card per goal.
  - Cards about body weight only reach people whose BMI is in the overweight
    range or above; nobody else sees them.
  - Dates are the person's own calendar days (Australia/Brisbane when unknown).
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import date, timedelta
from typing import Optional

import httpx

from utils.evidence import list_verified_cards
from utils.feed import create_feed_item
from utils.feed_intro import make_intro
from utils.goal_catalog import get_metric
from utils.goals import bmi, current_average, fetch_points, get_height_cm, list_goals
from utils.local_time import user_today

logger = logging.getLogger(__name__)

NO_REPEAT_DAYS = 60
MIN_GAP_DAYS = 2
MAX_PER_ROUND = 2
MAX_FORCED_PER_DAY = 2
WEIGHT_CARD_MIN_BMI = 25.0


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers() -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


# ── pure rules ───────────────────────────────────────────────────────────────

def due_for_round(last_dates: list[date], today: date, forced: bool, created_today: int = 0) -> bool:
    """Whether a new round of cards may be added now."""
    if forced:
        return created_today < MAX_FORCED_PER_DAY
    return not any(today - d < timedelta(days=MIN_GAP_DAYS) for d in last_dates)


def card_score(card: dict, metric_key: str, seed: str) -> float:
    """Higher is better: meta-analyses over single trials, newer over older, a card about this exact metric first."""
    tags = card.get("metric_tags") or []
    score = 100.0
    score += 20 if card.get("study_type") == "meta-analysis" else 10 if card.get("study_type") == "RCT" else 0
    score += max(0, (card.get("year") or 2000) - 2000) / 10.0
    if tags and tags[0] == metric_key:
        score += 15
    # A steady per-person tie-break, so two people with the same goal don't all see the same card first.
    score += int(hashlib.sha256(f"{seed}|{card.get('id')}".encode()).hexdigest()[:4], 16) / 65535.0
    return score


def pick_cards(goals: list[dict], cards: list[dict], recent_card_ids: set[str], weight_ok: bool, seed: str, limit: int = MAX_PER_ROUND) -> list[tuple[dict, dict]]:
    """(card, goal) pairs to show: one per goal first, then more for goals that still have a card left."""
    usable = [c for c in cards if c.get("id") not in recent_card_ids and (weight_ok or not c.get("weight_related"))]
    ranked_by_goal: list[tuple[dict, list[dict]]] = []
    for goal in goals:
        key = goal.get("metric_col")
        matches = [c for c in usable if key in (c.get("metric_tags") or [])]
        matches.sort(key=lambda c: card_score(c, key, seed), reverse=True)
        if matches:
            ranked_by_goal.append((goal, matches))
    # The goal with the best available card goes first.
    ranked_by_goal.sort(key=lambda g: card_score(g[1][0], g[0]["metric_col"], seed), reverse=True)

    chosen: list[tuple[dict, dict]] = []
    used: set[str] = set()
    for goal, matches in ranked_by_goal:
        card = next((c for c in matches if c["id"] not in used), None)
        if card:
            chosen.append((card, goal))
            used.add(card["id"])
        if len(chosen) >= limit:
            return chosen
    # Still room: a second card for a goal that has one.
    for goal, matches in ranked_by_goal:
        card = next((c for c in matches if c["id"] not in used), None)
        if card:
            chosen.append((card, goal))
            used.add(card["id"])
        if len(chosen) >= limit:
            break
    return chosen


# ── database access ──────────────────────────────────────────────────────────

async def _recent_items(user_id: str, today: date) -> list[dict]:
    since = today - timedelta(days=NO_REPEAT_DAYS)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            _sb_url("feed_items"),
            headers=_sb_headers(),
            params={"user_id": f"eq.{user_id}", "kind": "eq.check_this_out", "local_date": f"gte.{since.isoformat()}", "select": "card_id,local_date"},
        )
        resp.raise_for_status()
        return resp.json() or []


async def weight_cards_allowed(user_id: str, today: date) -> bool:
    """True only when height and a recent weight are known and the BMI is at least 25."""
    height = await get_height_cm(user_id)
    if not height:
        return False
    points = await fetch_points(user_id, "weight_kg", today - timedelta(days=21))
    if not points:
        return False
    return bmi(points[-1][1], height) >= WEIGHT_CARD_MIN_BMI


async def generate_for_user(user_id: str, forced: bool = False) -> list[dict]:
    """Adds this round's cards to one person's feed. Returns the feed items created (never raises)."""
    try:
        today = await user_today(user_id)
        goals = [g for g in await list_goals(user_id, "active") if get_metric(g.get("metric_col", ""))]
        if not goals:
            return []
        recent = await _recent_items(user_id, today)
        dates = [date.fromisoformat(r["local_date"]) for r in recent if r.get("local_date")]
        created_today = sum(1 for d in dates if d == today)
        if not due_for_round(dates, today, forced, created_today):
            return []

        tags = sorted({g["metric_col"] for g in goals})
        cards = await list_verified_cards(tags=tags, limit=300)
        if not cards:
            return []
        weight_ok = await weight_cards_allowed(user_id, today) if any(c.get("weight_related") for c in cards) else False
        picks = pick_cards(goals, cards, {r["card_id"] for r in recent if r.get("card_id")}, weight_ok, seed=f"{user_id}|{today.isoformat()}")

        items = []
        for card, goal in picks:
            metric = get_metric(goal["metric_col"])
            if metric is None:
                continue
            current, _ = await current_average(user_id, metric.key, today)
            intro = await make_intro(user_id, metric, goal.get("direction") or "increase", current, goal.get("target_value"))
            item = await create_feed_item(
                user_id,
                kind="check_this_out",
                local_date=today,
                title=card["title"],
                body=intro,
                goal_id=goal["id"],
                card_id=card["id"],
                payload={"metric_key": metric.key, "goal_label": goal.get("metric_label") or metric.label},
            )
            if item:
                items.append(item)
        return items
    except Exception as exc:
        logger.warning("Building feed cards failed for %s: %s", user_id[:8], exc)
        return []


async def users_with_active_goals() -> list[str]:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(_sb_url("user_goals"), headers=_sb_headers(), params={"status": "eq.active", "select": "user_id", "limit": "5000"})
        resp.raise_for_status()
        return sorted({r["user_id"] for r in resp.json() or [] if r.get("user_id")})

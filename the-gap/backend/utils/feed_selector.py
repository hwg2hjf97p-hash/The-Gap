"""
Choosing which approved research cards to put in a person's feed.

The feed is mostly research on the person's own goals, with a few other
studies mixed in to read and learn from.

Rules:
  - Only approved cards (utils/evidence.py reads nothing else).
  - Goal cards speak to one of the person's active goals (the card's
    metric_tags include the goal's metric). About three in four cards.
  - The rest are "explore" cards: other approved studies picked at random,
    preferring subjects that aren't about a goal they already have, from
    different categories. People with no goal get these only.
  - Never a card shown to them in the last 60 days.
  - The feed keeps a stock of cards the person hasn't looked at yet: whenever
    fewer than 8 are waiting it is topped up to 12 (about three goal cards for
    every other study). Otherwise a round of 4 (3 goal, 1 explore) is added at
    most every two days. No more than 16 cards are added in a day.
  - Cards are created so they appear in the feed as goal, goal, explore, goal ...
  - Cards about body weight only reach people whose BMI is 25 or above.
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
ROUND_GOAL_CARDS = 3
ROUND_EXPLORE_CARDS = 1
FIRST_ROUND_GOAL_CARDS = 4
FIRST_ROUND_EXPLORE_CARDS = 2
NO_GOAL_ROUND_CARDS = 2
NO_GOAL_FIRST_ROUND_CARDS = 3
MAX_PER_ROUND = ROUND_GOAL_CARDS  # goal cards in a normal round (kept for older callers)
MAX_FORCED_PER_DAY = 4  # older name, no longer used
RESERVOIR_MIN = 8
RESERVOIR_TARGET = 12
DAILY_CAP = 16
WEIGHT_CARD_MIN_BMI = 25.0


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers() -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


# ── pure rules ───────────────────────────────────────────────────────────────

def decide_round(unseen: int, created_today: int, last_dates: list[date], today: date, forced: bool, top_up: bool) -> tuple[bool, Optional[int]]:
    """
    (whether to add cards now, how many; None means the usual round size).

    A feed running low is always topped up; a person asking for research gets at
    least a normal round; otherwise a round comes at most every two days.
    """
    room = DAILY_CAP - created_today
    if room <= 0:
        return False, None
    if unseen < RESERVOIR_MIN:
        return True, min(RESERVOIR_TARGET - unseen, room)
    if forced:
        return True, min(max(4, RESERVOIR_TARGET - unseen), room)
    if top_up:
        return False, None
    if any(today - d < timedelta(days=MIN_GAP_DAYS) for d in last_dates):
        return False, None
    return True, None


def due_for_round(last_dates: list[date], today: date, forced: bool, created_today: int = 0) -> bool:
    """Whether a new round of cards may be added now."""
    if forced:
        return created_today < MAX_FORCED_PER_DAY
    return not any(today - d < timedelta(days=MIN_GAP_DAYS) for d in last_dates)


def _tie_break(seed: str, card_id: Optional[str]) -> float:
    return int(hashlib.sha256(f"{seed}|{card_id}".encode()).hexdigest()[:4], 16) / 65535.0


def card_score(card: dict, metric_key: str, seed: str) -> float:
    """Higher is better: meta-analyses over single trials, newer over older, a card about this exact metric first."""
    tags = card.get("metric_tags") or []
    score = 100.0
    score += 20 if card.get("study_type") == "meta-analysis" else 10 if card.get("study_type") == "RCT" else 0
    score += max(0, (card.get("year") or 2000) - 2000) / 10.0
    if tags and tags[0] == metric_key:
        score += 15
    # A steady per-person tie-break, so two people with the same goal don't all see the same card first.
    score += _tie_break(seed, card.get("id"))
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
    while len(chosen) < limit:
        added = False
        for goal, matches in ranked_by_goal:
            card = next((c for c in matches if c["id"] not in used), None)
            if card:
                chosen.append((card, goal))
                used.add(card["id"])
                added = True
            if len(chosen) >= limit:
                break
        if not added:
            break
    return chosen


def pick_explore(cards: list[dict], goals: list[dict], recent_card_ids: set[str], taken: set[str], weight_ok: bool, seed: str, limit: int) -> list[dict]:
    """
    Other approved studies for the person to learn from: random, from different
    categories where possible, preferring ones that aren't about a goal they
    already have (those are covered above).
    """
    goal_metrics = {g.get("metric_col") for g in goals}
    usable = [c for c in cards if c.get("id") not in recent_card_ids and c["id"] not in taken and (weight_ok or not c.get("weight_related"))]
    usable.sort(key=lambda c: (bool(goal_metrics & set(c.get("metric_tags") or [])), _tie_break(seed + "|explore", c.get("id"))))
    chosen: list[dict] = []
    seen_categories: set[str] = set()
    for card in usable:  # first pass: one per category
        if len(chosen) >= limit:
            break
        if card.get("category") not in seen_categories:
            chosen.append(card)
            seen_categories.add(card.get("category") or "")
    for card in usable:  # second pass: fill up from what is left
        if len(chosen) >= limit:
            break
        if card not in chosen:
            chosen.append(card)
    return chosen


def interleave(goal_items: list, explore_items: list) -> list:
    """goal, goal, explore, goal, goal, explore ... with any left over at the end."""
    out: list = []
    g, e = list(goal_items), list(explore_items)
    while g or e:
        out.extend(g[:2])
        g = g[2:]
        if e:
            out.append(e.pop(0))
        if not g and e:
            out.extend(e)
            e = []
    return out


def plan_round(goals: list[dict], cards: list[dict], recent_card_ids: set[str], weight_ok: bool, seed: str, first_round: bool, room: Optional[int] = None, size: Optional[int] = None) -> list[tuple[dict, Optional[dict]]]:
    """
    This round's cards in the order they should appear in the feed, as (card, goal)
    where goal is None for an explore card. `room` caps how many may be added.
    """
    if size is not None:
        # A top-up of a given size: about three goal cards for every other study.
        explore_n = size // 4 if goals else size
        goal_n = size - explore_n if goals else 0
    elif goals:
        goal_n = FIRST_ROUND_GOAL_CARDS if first_round else ROUND_GOAL_CARDS
        explore_n = FIRST_ROUND_EXPLORE_CARDS if first_round else ROUND_EXPLORE_CARDS
    else:
        goal_n, explore_n = 0, NO_GOAL_FIRST_ROUND_CARDS if first_round else NO_GOAL_ROUND_CARDS
    if room is not None:
        goal_n = min(goal_n, room)
        explore_n = min(explore_n, max(0, room - goal_n))

    goal_picks = pick_cards(goals, cards, recent_card_ids, weight_ok, seed, limit=goal_n) if goal_n else []
    taken = {c["id"] for c, _ in goal_picks}
    explore_picks = pick_explore(cards, goals, recent_card_ids, taken, weight_ok, seed, explore_n) if explore_n else []
    # If there weren't enough goal cards, explore cards make up the numbers.
    shortfall = goal_n - len(goal_picks)
    if room is not None:
        shortfall = min(shortfall, room - len(goal_picks) - len(explore_picks))
    if shortfall > 0:
        extra = pick_explore(cards, goals, recent_card_ids, taken | {c["id"] for c in explore_picks}, weight_ok, seed + "|fill", shortfall)
        explore_picks += extra
    return interleave(goal_picks, [(c, None) for c in explore_picks])


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


async def unseen_count(user_id: str) -> int:
    """How many research cards are waiting in the feed that the person hasn't looked at or dismissed."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            _sb_url("feed_items"),
            headers=_sb_headers(),
            params={"user_id": f"eq.{user_id}", "kind": "eq.check_this_out", "seen_at": "is.null", "dismissed_at": "is.null", "select": "id", "limit": "200"},
        )
        resp.raise_for_status()
        return len(resp.json() or [])


async def weight_cards_allowed(user_id: str, today: date) -> bool:
    """True only when height and a recent weight are known and the BMI is at least 25."""
    height = await get_height_cm(user_id)
    if not height:
        return False
    points = await fetch_points(user_id, "weight_kg", today - timedelta(days=21))
    if not points:
        return False
    return bmi(points[-1][1], height) >= WEIGHT_CARD_MIN_BMI


async def build_round(user_id: str, forced: bool = False, top_up: bool = False) -> tuple[list[dict], str]:
    """
    Adds this round's cards to one person's feed. Returns (the feed items created, why it is empty or "ok").
    reason: ok | not_due | no_cards | no_match | error. Never raises.
    """
    try:
        today = await user_today(user_id)
        goals = [g for g in await list_goals(user_id, "active") if get_metric(g.get("metric_col", ""))]
        recent = await _recent_items(user_id, today)
        dates = [date.fromisoformat(r["local_date"]) for r in recent if r.get("local_date")]
        created_today = sum(1 for d in dates if d == today)
        due, size = decide_round(await unseen_count(user_id), created_today, dates, today, forced, top_up)
        if not due:
            return [], "not_due"

        # Goal cards need a tag match; explore cards can be anything, so the whole approved library is read.
        cards = await list_verified_cards(limit=500)
        if not cards:
            return [], "no_cards"
        weight_ok = await weight_cards_allowed(user_id, today) if any(c.get("weight_related") for c in cards) else False
        room = DAILY_CAP - created_today
        plan = plan_round(goals, cards, {r["card_id"] for r in recent if r.get("card_id")}, weight_ok, f"{user_id}|{today.isoformat()}|{created_today}", first_round=not recent, room=room, size=size)
        if not plan:
            return [], "no_match"

        # The feed shows newest first, so the last card in the plan is created first.
        items = []
        for card, goal in reversed(plan):
            if goal is not None:
                metric = get_metric(goal["metric_col"])
                if metric is None:
                    continue
                current, _ = await current_average(user_id, metric.key, today)
                intro = await make_intro(user_id, metric, goal.get("direction") or "increase", current, goal.get("target_value"))
                payload = {"metric_key": metric.key, "goal_label": goal.get("metric_label") or metric.label, "reason": "goal"}
                goal_id = goal["id"]
            else:
                intro, goal_id = "", None
                payload = {"metric_key": (card.get("metric_tags") or [None])[0], "goal_label": None, "reason": "explore"}
            item = await create_feed_item(user_id, kind="check_this_out", local_date=today, title=card["title"], body=intro, goal_id=goal_id, card_id=card["id"], payload=payload)
            if item:
                items.append(item)
        return items, "ok" if items else "error"
    except Exception as exc:
        logger.warning("Building feed cards failed for %s: %s", user_id[:8], exc)
        return [], "error"


async def generate_for_user(user_id: str, forced: bool = False) -> list[dict]:
    items, _ = await build_round(user_id, forced)
    return items


async def users_for_feed() -> list[str]:
    """Everyone with data to work from: anyone with a goal, plus anyone with an analysis."""
    ids: set[str] = set()
    async with httpx.AsyncClient(timeout=20) as client:
        for table, params in (("user_goals", {"status": "eq.active", "select": "user_id", "limit": "5000"}), ("results", {"select": "user_id", "limit": "5000"})):
            resp = await client.get(_sb_url(table), headers=_sb_headers(), params=params)
            resp.raise_for_status()
            ids |= {r["user_id"] for r in resp.json() or [] if r.get("user_id")}
    return sorted(ids)


_TOP_UP_GAP_SECONDS = 600
_last_top_up: dict[str, float] = {}
_tasks: set = set()


async def start_top_up_if_low(user_id: str) -> bool:
    """
    Opening the feed with fewer than a handful of unseen cards starts a top-up in
    the background and says so, so the app can look again in a few seconds. Tried
    at most every ten minutes per person, so a library with nothing left to show
    isn't searched on every visit.
    """
    import asyncio
    import time

    now = time.time()
    if now - _last_top_up.get(user_id, 0.0) < _TOP_UP_GAP_SECONDS:
        return False
    try:
        if await unseen_count(user_id) >= RESERVOIR_MIN:
            return False
    except Exception:
        return False
    _last_top_up[user_id] = now
    task = asyncio.create_task(build_round(user_id, top_up=True))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return True


# Older name, kept so existing imports keep working.
users_with_active_goals = users_for_feed

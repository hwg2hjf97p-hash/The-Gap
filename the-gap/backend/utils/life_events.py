"""
Life events: big changes a person tells The Gap about themselves (lost a job, moved house, a new baby ...).

Why: a bad month for HRV and sleep often has a reason the wearable can't see. With the date of the change, the app can
say "since you logged this, your sleep has averaged X, against Y before", and Gappy can talk about it sensibly instead
of guessing.

Rules this file keeps:
  - Only what the person enters. Nothing is picked up from anywhere else; the app may SUGGEST adding one when a note
    mentions it, but only the person's tap adds it.
  - The before/after is a description of their own readings around a date. It never says the event caused the change
    (lots changes around big events), and says so.
  - What goes to the AI is the type of event and its date. The optional note stays on the person's account and is never
    sent to the AI, to a push, or onto a share card.
"""

from __future__ import annotations

import math
import os
import statistics
from datetime import date, timedelta
from typing import Optional

import httpx

from utils.goal_catalog import get_metric
from utils.goals import fetch_points, fmt

KINDS: dict[str, str] = {
    "job_lost": "Lost or left a job",
    "job_new": "Started a new job",
    "moved": "Moved house",
    "relationship": "Relationship change",
    "baby": "New baby",
    "injury_illness": "Injury or illness",
    "loss": "Loss of someone close",
    "other": "Another big change",
}

MAX_EVENTS = 50
MAX_NOTE = 140
MAX_AGE_DAYS = 400

# What is compared (keys in metric_history) and how to say it.
METRICS: list[tuple[str, str]] = [
    ("hrv", "HRV"),
    ("sleep_total_min", "sleep"),
    ("resting_hr", "resting heart rate"),
    ("steps", "daily steps"),
]
WINDOW_DAYS = 14        # days compared on each side
MIN_BEFORE = 8          # days with a reading before the event
MIN_AFTER = 7           # and after it
MIN_SD_SHIFT = 0.6      # the averages must differ by this much of the person's own usual day-to-day swing...
MIN_T = 2.2             # ...and be unlikely to be luck


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


def validate(kind: str, event_date: str, note: Optional[str], today: date) -> tuple[Optional[dict], Optional[str]]:
    """(the row's fields, None) or (None, what to tell the person)."""
    if kind not in KINDS:
        return None, "Pick what changed from the list."
    try:
        day = date.fromisoformat(event_date)
    except ValueError:
        return None, "That date doesn't look right."
    if day > today:
        return None, "A life event can't be in the future."
    if (today - day).days > MAX_AGE_DAYS:
        return None, "That's more than a year ago, which is further back than The Gap looks."
    cleaned = (note or "").strip()[:MAX_NOTE] or None
    return {"kind": kind, "event_date": day.isoformat(), "note": cleaned}, None


def compare(points: list[tuple[date, float]], event_date: date, today: date) -> Optional[tuple[float, float, int, int]]:
    """
    (average before, average after, days before, days after) in the raw units, when there are enough days on each
    side and the change is both large (against this person's own day-to-day swing) and unlikely to be luck.
    The event day itself is left out.
    """
    if today < event_date + timedelta(days=MIN_AFTER):
        return None
    before = [v for d, v in points if event_date - timedelta(days=WINDOW_DAYS) <= d < event_date]
    after = [v for d, v in points if event_date < d <= min(today, event_date + timedelta(days=WINDOW_DAYS))]
    if len(before) < MIN_BEFORE or len(after) < MIN_AFTER:
        return None
    mean_before, mean_after = statistics.fmean(before), statistics.fmean(after)
    sd_before = statistics.pstdev(before)
    if sd_before <= 0:
        return None
    var_b, var_a = statistics.variance(before), statistics.variance(after)
    se = math.sqrt(var_b / len(before) + var_a / len(after))
    if se <= 0:
        return None
    t = abs(mean_after - mean_before) / se
    if abs(mean_after - mean_before) / sd_before < MIN_SD_SHIFT or t < MIN_T:
        return None
    return mean_before, mean_after, len(before), len(after)


def sentence(metric_key: str, noun: str, before: float, after: float, n_before: int, n_after: int) -> str:
    metric = get_metric(metric_key)
    scale = metric.scale if metric else 1.0
    decimals = metric.decimals if metric else 0
    unit = f" {metric.unit}" if metric and metric.unit else ""
    return (
        f"Your {noun} averaged {fmt(after / scale, decimals)}{unit} over the {n_after} days after, "
        f"against {fmt(before / scale, decimals)}{unit} over the {n_before} days before."
    )


async def effects_for(user_id: str, events: list[dict], today: date) -> dict[str, list[str]]:
    """Event id -> what changed around it, in plain sentences (empty when nothing clear shows)."""
    out: dict[str, list[str]] = {e["id"]: [] for e in events}
    if not events:
        return out
    earliest = min(date.fromisoformat(e["event_date"]) for e in events) - timedelta(days=WINDOW_DAYS)
    for key, noun in METRICS:
        points = await fetch_points(user_id, key, earliest)
        if not points:
            continue
        for e in events:
            found = compare(points, date.fromisoformat(e["event_date"]), today)
            if found:
                out[e["id"]].append(sentence(key, noun, *found))
    return out


async def list_events(user_id: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            _sb_url("life_events"), headers=_sb_headers(),
            params={"user_id": f"eq.{user_id}", "select": "id,kind,event_date,note,created_at", "order": "event_date.desc", "limit": str(MAX_EVENTS)},
        )
        resp.raise_for_status()
        return resp.json() or []


async def for_assistant(user_id: str) -> str:
    """One short line per event for Gappy: the type and the date only (never the note). Empty if none or unreadable."""
    try:
        events = await list_events(user_id)
    except Exception:
        return ""
    lines = [f"- {KINDS.get(e['kind'], 'A big change')} (around {e['event_date']})" for e in events[:8]]
    return "\n".join(lines)

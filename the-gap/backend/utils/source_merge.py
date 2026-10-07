"""
One main source per kind of reading.

When more than one connected source reports the same thing (say sleep from
both Whoop and Apple Health), they don't agree: each defines "sleep" its own
way. The old behaviour let whichever source happened to load first win, and
let others fill the gaps, so a single sleep series could switch source from
one night to the next, which makes trends meaningless.

Now each group of readings (sleep, recovery, activity, body) comes from ONE
source, chosen by the person or by a sensible default order. Another source
is used for a group only if the main one has no data for it at all, or if the
person has switched on "fill gaps from other sources" for that group.
Anything not in a group (workout stats, strain, and so on) is merged in the
default order, as before.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

GROUPS: dict[str, list[str]] = {
    "sleep": ["sleep_total_min", "sleep_deep_min", "sleep_score"],
    "recovery": ["hrv", "resting_hr", "recovery_score"],
    "activity": ["steps", "active_energy", "vo2max"],
    "body": ["weight_kg"],
}

GROUP_LABELS = {
    "sleep": "Sleep",
    "recovery": "HRV, resting heart rate and recovery",
    "activity": "Steps and activity",
    "body": "Weight",
}

SOURCE_LABELS = {
    "whoop": "Whoop",
    "oura": "Oura",
    "polar": "Polar",
    "withings": "Withings",
    "strava": "Strava",
    "apple_health": "Apple Health",
}

# Used when the person hasn't chosen. Wearables built for sleep and recovery
# come first for those; Apple Health leads for steps and activity.
DEFAULT_PRIORITY: dict[str, list[str]] = {
    "sleep": ["whoop", "oura", "polar", "withings", "apple_health"],
    "recovery": ["whoop", "oura", "polar", "withings", "apple_health"],
    "activity": ["apple_health", "oura", "withings", "strava", "polar", "whoop"],
    "body": ["withings", "apple_health"],
}
GENERAL_ORDER = ["whoop", "oura", "polar", "withings", "strava", "apple_health"]

# Mixing sources inside one series is bad for sleep and recovery (different
# definitions); harmless for steps and weight. These are the defaults.
DEFAULT_FILL_GAPS = {"sleep": False, "recovery": False, "activity": True, "body": True}


def _ordered(group: str, frames: dict[str, pd.DataFrame], chosen: Optional[str]) -> list[str]:
    """Sources for a group, best first: the person's choice, then the default order, then any others."""
    order: list[str] = []
    if chosen and chosen in frames:
        order.append(chosen)
    for s in DEFAULT_PRIORITY.get(group, []) + GENERAL_ORDER:
        if s in frames and s not in order:
            order.append(s)
    for s in frames:
        if s not in order:
            order.append(s)
    return order


def merge_sources(frames: dict[str, pd.DataFrame], prefs: Optional[dict]) -> Optional[pd.DataFrame]:
    """Combine each source's daily table into one, one main source per group."""
    frames = {name: f for name, f in frames.items() if f is not None and not f.empty}
    if not frames:
        return None
    prefs = prefs or {}
    primary = prefs.get("primary") or {}
    fill = {**DEFAULT_FILL_GAPS, **(prefs.get("fill_gaps") or {})}

    prepared: dict[str, pd.DataFrame] = {}
    for name, f in frames.items():
        f = f.copy()
        f.index = pd.to_datetime(f.index)
        prepared[name] = f

    index = sorted(set().union(*[set(f.index) for f in prepared.values()]))
    out = pd.DataFrame(index=pd.DatetimeIndex(index))
    owned: set[str] = set()

    for group, cols in GROUPS.items():
        order = _ordered(group, prepared, primary.get(group))
        for col in cols:
            owned.add(col)
            sources = [s for s in order if col in prepared[s].columns and prepared[s][col].notna().any()]
            if not sources:
                continue
            series = prepared[sources[0]][col].reindex(out.index)
            if fill.get(group):
                for other in sources[1:]:
                    series = series.combine_first(prepared[other][col].reindex(out.index))
            out[col] = series

    # Everything that isn't a group reading: first source in the general order wins, gaps filled by the rest.
    extras: Optional[pd.DataFrame] = None
    for name in [s for s in GENERAL_ORDER if s in prepared] + [s for s in prepared if s not in GENERAL_ORDER]:
        f = prepared[name]
        extra = f[[c for c in f.columns if c not in owned]]
        if extra.empty or len(extra.columns) == 0:
            continue
        extra = extra.reindex(out.index)
        extras = extra if extras is None else extras.combine_first(extra)
    if extras is not None and not extras.empty:
        out = pd.concat([out, extras], axis=1)

    out.index.name = "date"
    return out.sort_index()


async def load_source_prefs(user_id: str) -> Optional[dict]:
    """The person's saved source choices, or None (also when the table isn't there yet)."""
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{base}/rest/v1/source_prefs",
                headers={"apikey": key, "Authorization": f"Bearer {key}"},
                params={"user_id": f"eq.{user_id}", "select": "prefs", "limit": "1"},
            )
            resp.raise_for_status()
            rows = resp.json() or []
            return rows[0].get("prefs") if rows else None
    except Exception as exc:
        logger.warning("Loading source preferences failed for %s: %s", user_id[:8], exc)
        return None

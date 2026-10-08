"""
One main source per kind of reading.

When more than one connected source reports the same thing (say sleep from
both Whoop and Apple Health), they don't agree: each defines "sleep" its own
way. The old behaviour let whichever source happened to load first win, and
let others fill the gaps, so a single sleep series could switch source from
one night to the next, which makes trends meaningless.

Now each group of readings (sleep, recovery, activity, body) has ONE main
source, chosen by the person or by a sensible default order. Where the main
source has no reading for a day, another source fills in (the person can
switch that off per group). For sleep and recovery the filler is first lined
up with the main source (see _aligned), so a switch of device doesn't show up
as a sudden jump in someone's numbers.

Filling gaps is the default because the analysis needs days: a person who
connected Whoop three weeks ago but has a year of Apple Health would otherwise
lose almost all of it for sleep and HRV, and most findings would disappear.
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
    "activity": ["steps", "vo2max"],
    "energy": ["active_energy"],
    "body": ["weight_kg"],
}

GROUP_LABELS = {
    "sleep": "Sleep",
    "recovery": "HRV, resting heart rate and recovery",
    "activity": "Steps",
    "energy": "Calories burned",
    "body": "Weight",
}

SOURCE_LABELS = {
    "whoop": "Whoop",
    "oura": "Oura",
    "polar": "Polar",
    "withings": "Withings",
    "manual": "Logged in the app",
    "strava": "Strava",
    "apple_health": "Apple Health",
}

# Used when the person hasn't chosen. Wearables built for sleep and recovery
# come first for those; Apple Health leads for steps and activity.
DEFAULT_PRIORITY: dict[str, list[str]] = {
    "sleep": ["whoop", "oura", "polar", "withings", "apple_health"],
    "recovery": ["whoop", "oura", "polar", "withings", "apple_health"],
    "activity": ["apple_health", "oura", "withings", "strava", "polar", "whoop"],
    "energy": ["apple_health", "oura", "whoop", "withings", "strava", "polar"],
    "body": ["manual", "withings", "apple_health"],
}
GENERAL_ORDER = ["whoop", "oura", "polar", "withings", "strava", "apple_health"]

# Whether a group fills days its main source is missing from the other sources.
DEFAULT_FILL_GAPS = {"sleep": True, "recovery": True, "activity": True, "energy": True, "body": True}

# Sleep and recovery readings differ by device (each defines them its own way),
# so a filler source is lined up with the main one using the days both have.
# Calories burned is here because Whoop reports the whole day's energy use while Apple Health and Oura report only
# the active part: the level differs a lot, but day-to-day changes track each other, so a fixed shift lines them up.
ALIGN_GROUPS = {"sleep", "recovery", "energy"}
ALIGN_MIN_OVERLAP = 7
RATIO_COLUMNS = {"hrv"}  # scales with the person's level; the rest differ by a roughly fixed amount


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


def _aligned(main: pd.Series, other: pd.Series, col: str) -> pd.Series:
    """
    The filler series, shifted (or scaled, for HRV) so that on the days both
    sources reported, it matches the main source on average. With fewer than
    ALIGN_MIN_OVERLAP shared days there's nothing to line up against, so it is
    returned unchanged.
    """
    both = pd.concat([main, other], axis=1, keys=["main", "other"]).dropna()
    if len(both) < ALIGN_MIN_OVERLAP:
        return other
    if col in RATIO_COLUMNS:
        other_mean = float(both["other"].mean())
        if other_mean <= 0:
            return other
        ratio = float(both["main"].mean()) / other_mean
        return other * min(2.0, max(0.5, ratio))
    shift = float((both["main"] - both["other"]).mean())
    return (other + shift).clip(lower=0)


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
            main_series = series
            if fill.get(group):
                for other in sources[1:]:
                    filler = prepared[other][col].reindex(out.index)
                    if group in ALIGN_GROUPS:
                        filler = _aligned(main_series, filler, col)
                    series = series.combine_first(filler)
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

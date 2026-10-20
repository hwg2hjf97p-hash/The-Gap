"""
"On days with X, Y usually happened too": the plain counting version of "something happens, then something follows".

The formal findings (causal/engine.py) test habits against next-morning readings such as HRV and sleep. They can't say
"on days you had a run-in with the boss you tend to skip lunch", because that is one behaviour following another inside
the same day, and the engine works one day at a time. This counts it directly: on the days someone logged X, how often
did Y also happen, compared with all their other days?

Honest limits, all stated where the app shows it:
  - it is a count of what went together on the same day. The app can't tell which came first.
  - it needs several days of X (4 or more) before it says anything, and Y has to be much more common on those days.
  - it is a pattern in their own days, not a cause and not a prediction.

Private subjects (gambling, other substances) are never used.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from utils.patterns import _fisher_p

MIN_EVENT_DAYS = 4
MIN_OTHER_DAYS = 8
MIN_EVENT_RATE = 0.6      # Y happened on at least this share of the X days...
MIN_DIFFERENCE = 0.3      # ...and at least this much more often than on other days
MAX_P = 0.02              # and it is unlikely to be luck (exact test)
MAX_ITEMS = 2

# column in the daily table -> how to say it
EVENTS: list[tuple[str, str]] = [
    ("conflict_event", "an argument or conflict"),
    ("argument_flag", "an argument"),
    ("stress_event", "a stressful event"),
    ("high_stress_flag", "a high-stress rating"),
    ("work_late_flag", "working late"),
    ("travel_flag", "travel"),
    ("illness_event", "feeling unwell"),
    ("alcohol_flag", "alcohol"),
    ("late_screen_flag", "phone use after 11 pm"),
    ("afternoon_caffeine", "caffeine after 2 pm"),
]
BEHAVIOURS: list[tuple[str, str]] = [
    ("skipped_lunch", "no lunch logged"),
    ("skipped_breakfast", "no breakfast logged"),
    ("alcohol_flag", "alcohol"),
    ("late_screen_flag", "phone use after 11 pm"),
]

CAVEAT = "These are counts of what happened on the same days. The app can't tell which came first, and they don't prove one led to the other."


def _count(series: pd.Series) -> tuple[int, int]:
    """(days it happened, days it was recorded)."""
    answered = series.dropna()
    return int((answered > 0).sum()), int(len(answered))


def follow_ons(df: pd.DataFrame) -> list[dict]:
    if df is None or df.empty:
        return []
    found: list[dict] = []
    for event_col, event_words in EVENTS:
        if event_col not in df.columns:
            continue
        for behaviour_col, behaviour_words in BEHAVIOURS:
            if behaviour_col == event_col or behaviour_col not in df.columns:
                continue
            both = df[[event_col, behaviour_col]].dropna()
            if both.empty:
                continue
            event_days = both[both[event_col] > 0]
            other_days = both[both[event_col] <= 0]
            if len(event_days) < MIN_EVENT_DAYS or len(other_days) < MIN_OTHER_DAYS:
                continue
            k_event, n_event = int((event_days[behaviour_col] > 0).sum()), len(event_days)
            k_other, n_other = int((other_days[behaviour_col] > 0).sum()), len(other_days)
            rate_event, rate_other = k_event / n_event, k_other / n_other
            if rate_event < MIN_EVENT_RATE or rate_event - rate_other < MIN_DIFFERENCE:
                continue
            p = _fisher_p(k_event, n_event - k_event, k_other, n_other - k_other)
            if p > MAX_P:
                continue
            found.append(
                {
                    "event": event_col,
                    "behaviour": behaviour_col,
                    "headline": f"On the {n_event} days you logged {event_words}, {k_event} also had {behaviour_words}.",
                    "detail": f"On your other {n_other} days it was {k_other}. Same-day pattern: the order isn't known.",
                    "n_event": n_event,
                    "k_event": k_event,
                    "n_other": n_other,
                    "k_other": k_other,
                    "_p": p,
                }
            )

    # Most convincing first, one per behaviour and one per habit so the same story isn't told twice.
    found.sort(key=lambda f: (f["_p"], -(f["k_event"] / f["n_event"])))
    chosen: list[dict] = []
    used_events: set[str] = set()
    used_behaviours: set[str] = set()
    for f in found:
        if f["event"] in used_events or f["behaviour"] in used_behaviours:
            continue
        chosen.append({k: v for k, v in f.items() if not k.startswith("_")})
        used_events.add(f["event"])
        used_behaviours.add(f["behaviour"])
        if len(chosen) >= MAX_ITEMS:
            break
    return chosen


def meal_skips(entries: pd.DataFrame) -> Optional[pd.DataFrame]:
    """
    From food entries (columns local_date, local_hour): per day, whether breakfast (4:00 to 10:30) or lunch (11:00 to 15:00)
    has no food logged in it. A day where any entry has no time is left out, since a meal might have been logged without one.
    """
    if entries is None or entries.empty or "local_hour" not in entries.columns:
        return None
    rows: dict = {}
    for day, group in entries.groupby("local_date"):
        hours = pd.to_numeric(group["local_hour"], errors="coerce")
        if hours.isna().any():
            continue
        rows[day] = {
            "skipped_breakfast": 0.0 if ((hours >= 4) & (hours < 10.5)).any() else 1.0,
            "skipped_lunch": 0.0 if ((hours >= 11) & (hours < 15)).any() else 1.0,
        }
    return pd.DataFrame.from_dict(rows, orient="index") if rows else None

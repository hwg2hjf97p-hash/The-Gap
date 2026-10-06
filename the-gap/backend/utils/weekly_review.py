"""
The weekly review: how the last 7 days compare with the 7 before, how well
the habits that feed the insights were kept up, and one thing to focus on.

Everything here is plain arithmetic and fixed wording (no AI), so it is
predictable, free to run, and doesn't depend on anyone's AI consent. The
database reads live in routers/review.py; this file only turns numbers into
the review.
"""

from __future__ import annotations

from typing import Optional

# key in metric_history, label, unit shown, divisor to display units,
# higher is better, smallest change worth mentioning (in display units)
REVIEW_METRICS = [
    ("sleep_total_min", "Sleep", "hrs a night", 60.0, True, 10 / 60),
    ("hrv", "HRV", "ms", 1.0, True, 2.0),
    ("resting_hr", "Resting heart rate", "bpm", 1.0, False, 1.0),
    ("steps", "Steps", "steps a day", 1.0, True, 500.0),
    ("recovery_score", "Recovery", "%", 1.0, True, 3.0),
]
MIN_DAYS = 3  # days of readings needed in a week before it is compared


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _sign(x: float) -> str:
    return "+" if x > 0 else "−"


def delta_text(key: str, delta: float) -> str:
    sign = _sign(delta)
    if key == "sleep_total_min":
        return f"{sign}{abs(round(delta * 60))} min a night"
    if key == "steps":
        return f"{sign}{abs(round(delta)):,} a day"
    if key == "recovery_score":
        return f"{sign}{abs(round(delta))} points"
    unit = "ms" if key == "hrv" else "bpm"
    return f"{sign}{abs(round(delta, 1))} {unit}"


def summarise_metrics(this_week: dict[str, list[float]], last_week: dict[str, list[float]]) -> list[dict]:
    """One entry per metric that has enough days this week. `good` is True/False
    when the change is big enough to mention and None otherwise."""
    out: list[dict] = []
    for key, label, unit, divisor, higher_is_better, min_change in REVIEW_METRICS:
        current_days = this_week.get(key, [])
        if len(current_days) < MIN_DAYS:
            continue
        current = _mean(current_days) / divisor
        item: dict = {
            "key": key,
            "label": label,
            "unit": unit,
            "value": round(current) if key == "steps" else round(current, 1),
            "days": len(current_days),
            "delta_text": None,
            "good": None,
        }
        previous_days = last_week.get(key, [])
        if len(previous_days) >= MIN_DAYS:
            delta = current - _mean(previous_days) / divisor
            if abs(delta) >= min_change:
                item["good"] = (delta > 0) == higher_is_better
                item["delta_text"] = delta_text(key, delta)
            else:
                item["delta_text"] = "About the same"
        out.append(item)
    return out


def _names(items: list[dict]) -> str:
    names = [i["label"].lower() for i in items[:2]]
    return " and ".join(names)


def headline(stats: list[dict]) -> str:
    improved = [s for s in stats if s["good"] is True]
    slipped = [s for s in stats if s["good"] is False]
    if improved and slipped:
        return f"Mixed week: your {_names(improved[:1])} improved and your {_names(slipped[:1])} slipped."
    if improved:
        return f"A good week: your {_names(improved)} improved."
    if slipped:
        return f"A tougher week: your {_names(slipped)} slipped."
    return "A steady week, with no big changes."


def habit_line(checkins: int, days: int = 7) -> str:
    if checkins >= 5:
        return f"You checked in on {checkins} of {days} days. That consistency is what makes your insights accurate."
    if checkins >= 1:
        return f"You checked in on {checkins} of {days} days. More days means sharper insights."
    return "You didn't log a check-in this week. Even 30 seconds a day makes your insights better."


def highlights(stats: list[dict], habits: dict) -> list[str]:
    lines: list[str] = []
    best = next((s for s in stats if s["good"] is True), None)
    worst = next((s for s in stats if s["good"] is False), None)
    if best:
        lines.append(f"{best['label']}: {best['value']:,} {best['unit']}, {best['delta_text']}.")
    if worst:
        lines.append(f"{worst['label']}: {worst['value']:,} {worst['unit']}, {worst['delta_text']}.")
    lines.append(habit_line(habits.get("checkins", 0)))
    return lines[:3]


_SLIP_ADVICE = {
    "sleep_total_min": "Protect your sleep this week: aim for a steady bedtime.",
    "hrv": "Make one of your harder days easier and see whether your recovery bounces back.",
    "recovery_score": "Make one of your harder days easier and see whether your recovery bounces back.",
    "resting_hr": "A higher resting heart rate can mean you're run down. Go gently and look after your sleep.",
    "steps": "Add a short walk on your quietest day.",
}


def choose_focus(stats: list[dict], habits: dict) -> str:
    """The single thing to work on next. The first rule that applies wins."""
    if habits.get("checkins", 0) < 4:
        return "Aim for 5 check-ins this week. It's the fastest way to unlock new insights."
    food_days = habits.get("food_days", 0)
    if 0 < food_days < 4:
        return "Log your meals on 5 days this week so your food insights can start to show."
    planned, done = habits.get("workouts_planned", 0), habits.get("workouts_done", 0)
    if planned > done:
        return f"You planned {planned} workouts and finished {done}. Start with the one that's easiest to fit in."
    slip = next((s for s in stats if s["good"] is False), None)
    if slip:
        return _SLIP_ADVICE.get(slip["key"], "Keep an eye on it this week.")
    return "Keep going. Consistency is what turns early hints into confirmed insights."


def is_ready(stats: list[dict], habits: dict) -> bool:
    """Enough data for a review to say something real."""
    return bool(stats) or habits.get("checkins", 0) >= 2


def build_review_payload(
    this_week: dict[str, list[float]],
    last_week: dict[str, list[float]],
    habits: dict,
    streak: int,
    confirmed_count: int,
    early_count: int,
    start: str,
    end: str,
) -> dict:
    stats = summarise_metrics(this_week, last_week)
    if not is_ready(stats, habits):
        return {
            "ready": False,
            "message": "A few more days of data and your first weekly review will appear here.",
            "week_start": start,
            "week_end": end,
        }
    return {
        "ready": True,
        "week_start": start,
        "week_end": end,
        "headline": headline(stats) if stats else "Here's how you did this week.",
        "stats": stats,
        "habits": habits,
        "highlights": highlights(stats, habits),
        "focus": choose_focus(stats, habits),
        "streak": streak,
        "confirmed_count": confirmed_count,
        "early_count": early_count,
    }


def split_by_week(rows: list[dict], this_start: str, this_end: str) -> tuple[dict[str, list[float]], dict[str, list[float]]]:
    """Group metric_history rows into this week's and the previous week's readings by metric.
    Dates are YYYY-MM-DD strings, so they compare correctly as text."""
    this_week: dict[str, list[float]] = {}
    last_week: dict[str, list[float]] = {}
    for r in rows:
        try:
            value = float(r["value"])
        except (TypeError, ValueError, KeyError):
            continue
        day = r.get("date", "")
        target: Optional[dict[str, list[float]]] = None
        if this_start <= day <= this_end:
            target = this_week
        elif day < this_start:
            target = last_week
        if target is not None:
            target.setdefault(r["metric"], []).append(value)
    return this_week, last_week

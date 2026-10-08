"""
What a person can set a goal on.

Only readings the app really tracks, grouped as the Goals tab shows them. Each
has sensible limits so a goal can't be set to something unrealistic or unsafe,
and some only allow certain directions (alcohol: down or hold, never up).

Values are stored and shown in the display unit (hours of sleep, not minutes).
`scale` converts the stored daily history into it. Habits counted per week
(workout days, drinks) are the average logged day times seven.

Deliberately NOT offered: calories, macros, and any rate-of-loss target. Weight
is offered with a safety check (utils/goals.py).
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

CATEGORIES: list[tuple[str, str]] = [
    ("sleep", "Sleep"),
    ("body", "Body"),
    ("fitness", "Fitness"),
    ("recovery", "Recovery"),
    ("stress_mood", "Stress & Mood"),
    ("habits", "Habits"),
]
CATEGORY_LABELS = dict(CATEGORIES)


@dataclass(frozen=True)
class GoalMetric:
    key: str                       # the column in metric_history
    label: str
    unit: str
    category: str
    minimum: float                 # lowest / highest target accepted, in display units
    maximum: float
    step: float                    # how the target is nudged in the app
    default_direction: str = "increase"
    directions: tuple[str, ...] = ("increase", "decrease", "maintain")
    scale: float = 1.0             # history value / scale = display value
    per_week: bool = False         # shown as the average logged day times 7
    min_points: int = 5            # days with a reading, within the last 7, before an average counts
    decimals: int = 0
    needs_height: bool = False     # weight: a height is needed to check a healthy range
    allow_target_date: bool = True
    hint: str = ""


GOAL_METRICS: dict[str, GoalMetric] = {m.key: m for m in [
    # Sleep
    GoalMetric("sleep_total_min", "Sleep per night", "hrs", "sleep", 5.0, 10.0, 0.25, scale=60.0, decimals=1, directions=("increase", "maintain"), hint="Your 7-day average of time asleep."),
    GoalMetric("sleep_deep_min", "Deep sleep", "min", "sleep", 20, 150, 5, hint="Needs a device that reports sleep stages."),
    GoalMetric("sleep_score", "Sleep performance", "%", "sleep", 40, 100, 1, hint="From Whoop or Polar."),
    # Body
    GoalMetric("weight_kg", "Weight", "kg", "body", 35, 250, 0.5, default_direction="maintain", min_points=2, decimals=1, needs_height=True, allow_target_date=False,
               hint="Your 7-day average, from a connected scale. We check targets against a healthy range for your height."),
    # Fitness
    GoalMetric("steps", "Daily steps", "steps", "fitness", 2000, 30000, 500, hint="Your 7-day average."),
    GoalMetric("active_energy", "Active calories", "kcal", "fitness", 100, 2500, 50, hint="Calories burned through activity, 7-day average."),
    GoalMetric("vo2max", "VO2 max", "ml/kg/min", "fitness", 15, 75, 0.5, min_points=3, decimals=1, directions=("increase", "maintain"), hint="Updates only now and then, so it needs 3 readings in a week."),
    GoalMetric("workout_completed_flag", "Workout days per week", "days", "fitness", 1, 7, 1, per_week=True, min_points=4, decimals=1, directions=("increase", "maintain"), hint="Workouts you mark as done."),
    # Recovery
    GoalMetric("hrv", "HRV", "ms", "recovery", 15, 200, 1, hint="Your 7-day average."),
    GoalMetric("resting_hr", "Resting heart rate", "bpm", "recovery", 35, 100, 1, default_direction="decrease", directions=("decrease", "maintain")),
    GoalMetric("recovery_score", "Recovery score", "%", "recovery", 20, 100, 1, hint="From Whoop, Oura or Polar."),
    # Stress & mood
    GoalMetric("stress_score", "Daily stress rating", "/10", "stress_mood", 1, 9, 0.5, default_direction="decrease", min_points=4, decimals=1, directions=("decrease", "maintain"), hint="From your daily check-in."),
    # Habits
    GoalMetric("screen_hours", "Screen time", "hrs/day", "habits", 0.5, 14, 0.5, default_direction="decrease", min_points=4, decimals=1, directions=("decrease", "maintain"), hint="From your daily check-in."),
    GoalMetric("alcohol_drinks", "Alcoholic drinks per week", "drinks", "habits", 0, 40, 1, default_direction="decrease", per_week=True, min_points=4, decimals=1, directions=("decrease", "maintain"), hint="From your daily check-in."),
    GoalMetric("afternoon_caffeine", "Days with caffeine after 2 pm", "days/week", "habits", 0, 7, 1, default_direction="decrease", per_week=True, min_points=4, decimals=1, directions=("decrease", "maintain"), hint="From your daily check-in."),
    GoalMetric("water_ml", "Water per day", "ml", "habits", 500, 6000, 250, min_points=4, directions=("increase", "maintain"), hint="From your water log."),
]}

# History columns the goals need saved each sync (beyond what the Home cards already store).
GOAL_HISTORY_COLUMNS = list(GOAL_METRICS)


def public_catalog(has_height: bool = False) -> list[dict]:
    """The catalog as the app lists it: categories in order, each with its metrics."""
    out = []
    for key, label in CATEGORIES:
        metrics = []
        for m in GOAL_METRICS.values():
            if m.category != key:
                continue
            d = asdict(m)
            d["metric_key"] = d.pop("key")
            d["directions"] = list(m.directions)
            d["available"] = has_height or not m.needs_height
            metrics.append(d)
        out.append({"key": key, "label": label, "metrics": metrics})
    return out


def get_metric(key: str) -> Optional[GoalMetric]:
    return GOAL_METRICS.get(key)

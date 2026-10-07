"""
"Best days versus worst days": what the person's best and worst readings had
in common.

The formal findings (causal/engine.py) need weeks of data and only report
effects that are both real and large enough to matter, so early on there are
often none. This looks at the same data more plainly: take the person's best
few nights (or mornings) and their worst few, and see which habits differ
between the two groups. It is a description of what tends to go together, not a
test of cause, and the app says so wherever it shows these.

To keep it from reporting coincidences, a habit is only shown when the two
groups differ by a lot AND the difference is statistically unlikely to be luck
(an exact test for yes/no habits, a t statistic for amounts). At most a few
patterns are shown.

Also reports which habits the person has logged on too few recent days for any
pattern to show up, so the app can suggest logging them.
"""

from __future__ import annotations

import math
from typing import Optional

import pandas as pd

MIN_DAYS = 28            # rows that have the outcome before any pattern is attempted
GROUP_FRACTION = 0.25    # the best and worst quarter of days
MIN_GROUP = 7
MIN_ANSWERED = 6         # days with the habit logged, within each group
MIN_RATE_DIFFERENCE = 0.35
MAX_FISHER_P = 0.03
MIN_T = 2.7
MIN_SD_DIFFERENCE = 0.8  # amounts: the groups' averages differ by this many standard deviations of the habit
MAX_PATTERNS = 4
MAX_PER_OUTCOME = 2
COVERAGE_WINDOW = 28
COVERAGE_ENOUGH = 14

CAVEAT = "These are things that tend to go together in your data. They don't prove one causes the other."


def _hours(minutes: float) -> str:
    h, m = divmod(int(round(minutes)), 60)
    return f"{h} h {m:02d} min" if h else f"{m} min"


def _amount(unit: str, digits: int = 1):
    def fmt(v: float) -> str:
        text = f"{v:,.{digits}f}".rstrip("0").rstrip(".") if digits else f"{v:,.0f}"
        return f"{text} {unit}".strip()

    return fmt


def _clock(hour: float) -> str:
    total = int(round(hour * 60)) % (24 * 60)
    h, m = divmod(total, 60)
    suffix = "am" if h < 12 else "pm"
    return f"{(h % 12) or 12}:{m:02d} {suffix}"


# outcome column -> how to talk about its best and worst days, and when the habit happened
OUTCOMES: dict[str, dict] = {
    "sleep_total_min": {"best": "longest-sleep nights", "worst": "shortest-sleep nights", "higher_is_better": True, "when": " that day", "fmt": _hours},
    "sleep_deep_min": {"best": "deepest-sleep nights", "worst": "lightest-sleep nights", "higher_is_better": True, "when": " that day", "fmt": _amount("min", 0)},
    "hrv_next": {"best": "highest-HRV mornings", "worst": "lowest-HRV mornings", "higher_is_better": True, "when": " the day before", "fmt": _amount("ms", 0)},
    "resting_hr_next": {"best": "lowest resting-heart-rate mornings", "worst": "highest resting-heart-rate mornings", "higher_is_better": False, "when": " the day before", "fmt": _amount("bpm", 0)},
}

# Habits: a yes/no ("binary") or an amount. Private ones (other substances, gambling) are never used here.
DRIVERS: list[dict] = [
    {"col": "alcohol_flag", "kind": "binary", "noun": "Alcohol"},
    {"col": "afternoon_caffeine", "kind": "binary", "noun": "Caffeine after 2 pm"},
    {"col": "late_screen_flag", "kind": "binary", "noun": "Phone use after 11 pm"},
    {"col": "high_stress_flag", "kind": "binary", "noun": "A high-stress day"},
    {"col": "workout_completed_flag", "kind": "binary", "noun": "A logged workout"},
    {"col": "energy_drink_late_flag", "kind": "binary", "noun": "A late energy drink"},
    {"col": "work_late_flag", "kind": "binary", "noun": "Working late"},
    {"col": "steps", "kind": "amount", "noun": "Steps", "fmt": _amount("", 0)},
    {"col": "active_energy", "kind": "amount", "noun": "Active calories", "fmt": _amount("kcal", 0)},
    {"col": "screen_hours", "kind": "amount", "noun": "Screen time", "fmt": _amount("h", 1)},
    {"col": "work_hours", "kind": "amount", "noun": "Work hours", "fmt": _amount("h", 1)},
    {"col": "stress_score", "kind": "amount", "noun": "Stress rating", "fmt": _amount("/10", 1)},
    {"col": "calendar_events", "kind": "amount", "noun": "Calendar events", "fmt": _amount("", 1)},
    {"col": "last_meal_hour", "kind": "amount", "noun": "Time of last meal", "fmt": _clock},
    {"col": "dietary_energy", "kind": "amount", "noun": "Calories eaten", "fmt": _amount("kcal", 0)},
]

# What to suggest logging when it's been logged on too few days: column -> (label, where to log it)
LOGGABLE: list[tuple[str, str, str]] = [
    ("alcohol_flag", "Alcohol", "answer the alcohol question in your daily check-in"),
    ("screen_hours", "Screen time", "add your screen time in your daily check-in"),
    ("afternoon_caffeine", "Caffeine", "answer the caffeine question in your daily check-in"),
    ("stress_score", "Stress", "rate your stress in your daily check-in"),
    ("last_meal_hour", "Meal times", "log your food, including what time you ate"),
    ("workout_completed_flag", "Workouts", "log your workouts"),
]


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _fisher_p(a: int, b: int, c: int, d: int) -> float:
    """Two-sided exact p for [[a, b], [c, d]]."""
    n = a + b + c + d
    r1, c1 = a + b, a + c

    def prob(x: int) -> float:
        return math.comb(r1, x) * math.comb(n - r1, c1 - x) / math.comb(n, c1)

    observed = prob(a)
    lo, hi = max(0, c1 - (n - r1)), min(r1, c1)
    return min(1.0, sum(prob(x) for x in range(lo, hi + 1) if prob(x) <= observed * (1 + 1e-9)))


def _binary_pattern(best: pd.Series, worst: pd.Series) -> Optional[dict]:
    best, worst = best.dropna(), worst.dropna()
    if len(best) < MIN_ANSWERED or len(worst) < MIN_ANSWERED:
        return None
    b_yes, w_yes = int((best > 0).sum()), int((worst > 0).sum())
    pb, pw = b_yes / len(best), w_yes / len(worst)
    if abs(pb - pw) < MIN_RATE_DIFFERENCE:
        return None
    p = _fisher_p(b_yes, len(best) - b_yes, w_yes, len(worst) - w_yes)
    if p > MAX_FISHER_P:
        return None
    return {"best": pb, "worst": pw, "p": p, "n_best": len(best), "n_worst": len(worst), "size": abs(pb - pw)}


def _amount_pattern(best: pd.Series, worst: pd.Series, everyone: pd.Series) -> Optional[dict]:
    best, worst = best.dropna(), worst.dropna()
    if len(best) < MIN_ANSWERED or len(worst) < MIN_ANSWERED:
        return None
    sd = float(everyone.dropna().std())
    if not sd or sd != sd:
        return None
    mb, mw = float(best.mean()), float(worst.mean())
    difference = abs(mb - mw) / sd
    if difference < MIN_SD_DIFFERENCE:
        return None
    se = math.sqrt(float(best.var()) / len(best) + float(worst.var()) / len(worst))
    if not se or se != se:
        return None
    t = abs(mb - mw) / se
    if t < MIN_T:
        return None
    return {"best": mb, "worst": mw, "p": 2 * (1 - _normal_cdf(t)), "n_best": len(best), "n_worst": len(worst), "size": difference}


def _headline(driver: dict, outcome: dict, found: dict) -> str:
    when = outcome["when"]
    if driver["kind"] == "binary":
        pb, pw = round(found["best"] * 100), round(found["worst"] * 100)
        return f"{driver['noun']}{when}: {pb}% of your {outcome['best']} vs {pw}% of your {outcome['worst']}"
    fmt = driver["fmt"]
    return f"{driver['noun']}{when}: averaged {fmt(found['best'])} on your {outcome['best']} vs {fmt(found['worst'])} on your {outcome['worst']}"


def best_vs_worst(df: pd.DataFrame) -> list[dict]:
    """The strongest few patterns separating the person's best days from their worst."""
    if df is None or df.empty:
        return []
    found_all: list[dict] = []
    for out_col, outcome in OUTCOMES.items():
        if out_col not in df.columns:
            continue
        series = df[out_col].dropna()
        n = len(series)
        if n < MIN_DAYS:
            continue
        k = max(MIN_GROUP, min(int(round(n * GROUP_FRACTION)), n // 3))
        ranked = series.sort_values(ascending=not outcome["higher_is_better"], kind="stable")
        best_days, worst_days = ranked.index[:k], ranked.index[-k:]
        best_mean, worst_mean = float(series.loc[best_days].mean()), float(series.loc[worst_days].mean())
        for driver in DRIVERS:
            col = driver["col"]
            if col not in df.columns or col == out_col:
                continue
            if driver["kind"] == "binary":
                found = _binary_pattern(df.loc[best_days, col], df.loc[worst_days, col])
            else:
                found = _amount_pattern(df.loc[best_days, col], df.loc[worst_days, col], df[col])
            if not found:
                continue
            found_all.append(
                {
                    "outcome": out_col,
                    "driver": col,
                    "kind": "binary" if driver["kind"] == "binary" else "amount",
                    "headline": _headline(driver, outcome, found),
                    "detail": (
                        f"Your {k} {outcome['best']} averaged {outcome['fmt'](best_mean)}; "
                        f"your {k} {outcome['worst']} averaged {outcome['fmt'](worst_mean)}."
                    ),
                    "best_value": round(found["best"], 3),
                    "worst_value": round(found["worst"], 3),
                    "n_best": found["n_best"],
                    "n_worst": found["n_worst"],
                    "_p": found["p"],
                    "_size": found["size"],
                }
            )

    # Most convincing first; one per habit, and a couple per kind of reading at most.
    found_all.sort(key=lambda f: (f["_p"], -f["_size"]))
    chosen: list[dict] = []
    used_drivers: set[str] = set()
    per_outcome: dict[str, int] = {}
    for f in found_all:
        if f["driver"] in used_drivers or per_outcome.get(f["outcome"], 0) >= MAX_PER_OUTCOME:
            continue
        chosen.append({k: v for k, v in f.items() if not k.startswith("_")})
        used_drivers.add(f["driver"])
        per_outcome[f["outcome"]] = per_outcome.get(f["outcome"], 0) + 1
        if len(chosen) >= MAX_PATTERNS:
            break
    return chosen


def tracking_suggestions(df: pd.DataFrame, limit: int = 3) -> list[dict]:
    """Habits logged on fewer than half of the last 28 days, most useful first."""
    if df is None or df.empty:
        return []
    window = df.tail(COVERAGE_WINDOW)
    out = []
    for col, label, hint in LOGGABLE:
        answered = int(window[col].notna().sum()) if col in window.columns else 0
        if answered < COVERAGE_ENOUGH:
            out.append({"label": label, "answered": answered, "window": len(window), "hint": hint})
        if len(out) >= limit:
            break
    return out


def build_patterns(df: pd.DataFrame) -> dict:
    """What the Insights screen shows: patterns, what to log next, and the honest caveat."""
    return {"items": best_vs_worst(df), "suggestions": tracking_suggestions(df), "caveat": CAVEAT, "days": int(len(df)) if df is not None else 0}

"""
The evidence behind a finding: what the person's own days looked like, and how the engine got from them to its number.

A bare "+5 ms" is an anticlimax: nobody can tell whether 5 ms is a lot, where it came from, or what their good and bad days look
like. This builds, from the exact days the engine used:

  - outcome:  the person's usual range for the reading (middle 80% of their days), their best and worst day, and their average
  - size:     the effect as a share of their own day-to-day swing, and a plain word for it ("small", "modest", "clear", "large")
  - groups:   for a yes/no habit, the reading on days WITH it and days WITHOUT, each as a range (typical, best, worst) and an average
  - bins:     for an amount, the reading on their lower, middle and higher days of it, plus a sample of their days for a scatter plot
  - timeline: their last six weeks of the reading, with the days that had the habit marked
  - how:      the steps the engine took, with the real numbers (how many days, what it accounted for, the range it found)

Nothing here is a new calculation of the effect: the effect and its range come from the estimator. This only describes the
data around them. Numbers are in the same units as the finding.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd

TIMELINE_DAYS = 45
SCATTER_POINTS = 60

# What was adjusted for, in words a person recognises.
COVARIATE_WORDS = {
    "hrv_lag1": "your HRV the day before",
    "sleep_lag1": "the night before's sleep",
    "sleep_total_min": "how long you slept",
    "resting_hr": "your resting heart rate",
    "day_of_week": "the day of the week",
    "is_weekend": "weekends versus weekdays",
    "steps": "how much you walked",
    "alcohol_flag": "whether you drank",
}


def _clean(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if not math.isfinite(number) else number


def _round(value, digits: int = 1):
    number = _clean(value)
    return None if number is None else round(number, digits)


def _stats(series: pd.Series, digits: int = 1) -> dict:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return {"n": 0}
    return {
        "n": int(len(s)),
        "mean": _round(s.mean(), digits),
        "median": _round(s.median(), digits),
        "p10": _round(s.quantile(0.10), digits),
        "p25": _round(s.quantile(0.25), digits),
        "p75": _round(s.quantile(0.75), digits),
        "p90": _round(s.quantile(0.90), digits),
        "min": _round(s.min(), digits),
        "max": _round(s.max(), digits),
    }


def _unit_word(label: str) -> str:
    return label.split("(", 1)[1].split(")", 1)[0].strip() if "(" in label and ")" in label else ""


def _plain(label: str) -> str:
    base = label.split("(")[0].strip()
    return base[:1].lower() + base[1:] if base and not base[:2].isupper() else base


def _number(v: float) -> str:
    if abs(v) >= 100:
        return f"{round(v):,}"
    text = f"{v:.1f}"
    return text[:-2] if text.endswith(".0") else text


def size_word(effect: float, sd: Optional[float]) -> Optional[str]:
    """How big the effect is next to this person's own day-to-day swing in the reading."""
    if not sd or sd <= 0:
        return None
    ratio = abs(effect) / sd
    if ratio < 0.2:
        return "small"
    if ratio < 0.5:
        return "modest"
    if ratio < 0.8:
        return "clear"
    return "large"


def checks_text(confidence: str, demoted: bool) -> str:
    """What the chance check concluded, in words. `demoted` is true if it was downgraded after the check across all patterns tested."""
    if confidence in ("strong", "moderate"):
        return (
            "The range stays on one side of zero, and the pattern also held up after a check for chance. We test dozens of "
            "possible patterns on every person, so some would look real by luck alone; this one passed that check."
        )
    if demoted:
        return (
            "This looked real on its own, but we test dozens of possible patterns, and with that many a few will look real by luck. "
            "It didn't clear that stricter check yet, so it's an early signal. More days will settle it."
        )
    return "The range is wide, or it touches zero, so this could still be chance. It's an early signal: keep logging and it will firm up or fade."


def _covariate_phrase(covs: list[str]) -> str:
    words = [COVARIATE_WORDS.get(c, c.replace("_", " ")) for c in covs]
    if not words:
        return ""
    if len(words) == 1:
        return words[0]
    return ", ".join(words[:-1]) + " and " + words[-1]


def build_evidence(*, sub: pd.DataFrame, hyp, result: dict, covs_used: list[str], higher_is_better: bool, confidence: str) -> dict:
    """The evidence for one finding. `result` is the estimator's answer already in the finding's units. Never raises."""
    try:
        return _build(sub, hyp, result, covs_used, higher_is_better, confidence)
    except Exception:
        return {}


def _build(sub: pd.DataFrame, hyp, result: dict, covs_used: list[str], higher_is_better: bool, confidence: str) -> dict:
    y = pd.to_numeric(sub[hyp.outcome_col], errors="coerce")
    t = pd.to_numeric(sub[hyp.treatment_col], errors="coerce")
    both = pd.DataFrame({"y": y, "t": t}).dropna()
    if len(both) < 5:
        return {}
    y, t = both["y"], both["t"]
    effect, ci_low, ci_high = float(result["effect"]), float(result["ci_low"]), float(result["ci_high"])
    unit = _unit_word(hyp.outcome_label)
    digits = 0 if abs(float(y.mean())) >= 200 else 1

    outcome = _stats(y, digits)
    outcome["best"] = outcome["max"] if higher_is_better else outcome["min"]
    outcome["worst"] = outcome["min"] if higher_is_better else outcome["max"]
    sd = _clean(y.std())
    swing = (outcome.get("p90") or 0) - (outcome.get("p10") or 0)
    evidence: dict = {
        "kind": "binary" if hyp.binary_treatment else "amount",
        "unit": unit,
        "outcome_name": _plain(hyp.outcome_label),
        "outcome": outcome,
        "effect": {"value": _round(effect, 2), "low": _round(ci_low, 2), "high": _round(ci_high, 2)},
        "size": {
            "word": size_word(effect, sd),
            "share_of_swing": _round(abs(effect) / sd, 2) if sd else None,
            "share_of_range": _round(abs(effect) / swing, 2) if swing > 0 else None,
        },
        "n": int(len(both)),
    }

    t_name = _plain(hyp.treatment_label)
    if hyp.binary_treatment:
        mask = t > 0
        with_y, without_y = y[mask], y[~mask]
        evidence["groups"] = {
            "with": _stats(with_y, digits),
            "without": _stats(without_y, digits),
            "with_label": f"Days with {t_name}",
            "without_label": "Days without it",
            "raw_difference": _round(with_y.mean() - without_y.mean(), 2) if len(with_y) and len(without_y) else None,
        }
    else:
        distinct = t.nunique()
        evidence["x_name"] = t_name
        evidence["treatment_range"] = {"min": _round(t.min(), 1), "max": _round(t.max(), 1)}
        if distinct >= 3:
            try:
                bands = pd.qcut(t.rank(method="first"), 3, labels=["lower", "middle", "higher"])
            except Exception:
                bands = None
            if bands is not None:
                evidence["bins"] = []
                for name in ("lower", "middle", "higher"):
                    part = both[bands == name]
                    if len(part):
                        evidence["bins"].append({"name": name, "t_low": _round(part["t"].min(), 1), "t_high": _round(part["t"].max(), 1), **_stats(part["y"], digits)})
        pts = both.sample(n=min(SCATTER_POINTS, len(both)), random_state=7).sort_values("t")
        evidence["points"] = [{"x": _round(r.t, 1), "y": _round(r.y, digits)} for r in pts.itertuples()]
        if t.std() and t.std() > 0:
            slope, intercept = np.polyfit(t.values, y.values, 1)
            x0, x1 = float(t.min()), float(t.max())
            evidence["trend"] = {"x0": _round(x0, 1), "y0": _round(slope * x0 + intercept, digits), "x1": _round(x1, 1), "y1": _round(slope * x1 + intercept, digits)}

    # The last six weeks of the reading, with the days that had the habit marked (or how high the amount was).
    recent = both.tail(TIMELINE_DAYS)
    low_t, high_t = float(t.quantile(0.33)), float(t.quantile(0.67))
    timeline = []
    for stamp, row in recent.iterrows():
        try:
            day = pd.Timestamp(stamp).date().isoformat()
        except Exception:
            day = str(stamp)
        if hyp.binary_treatment:
            level = 1 if row["t"] > 0 else 0
        else:
            level = 2 if row["t"] >= high_t else 0 if row["t"] <= low_t else 1
        timeline.append({"d": day, "y": _round(row["y"], digits), "l": level})
    evidence["timeline"] = timeline

    # How the engine got there, with the real numbers.
    lo, hi = _number(ci_low), _number(ci_high)
    signed = f"{'+' if effect >= 0 else '−'}{_number(abs(effect))}"
    steps = [f"We looked at {len(both)} days where we had both your {t_name} and your {_plain(hyp.outcome_label)}."]
    if hyp.binary_treatment:
        steps.append(f"On {int((t > 0).sum())} of those days you had it, and on {int((t <= 0).sum())} you didn't.")
    else:
        steps.append(f"Across those days your {t_name} ranged from {_number(float(t.min()))} to {_number(float(t.max()))}.")
    phrase = _covariate_phrase(covs_used)
    steps.append(
        f"We compared them while accounting for {phrase}, so those aren't mistaken for the effect."
        if phrase
        else "There weren't enough days to account for other factors, so this is a plain comparison."
    )
    per = hyp.treatment_label.split("(")[1].split(")")[0] if "(" in hyp.treatment_label and ")" in hyp.treatment_label else ""
    basis = "on days with it compared with days without" if hyp.binary_treatment else (per if per.startswith("per") else f"per {per}" if per else "per unit")
    steps.append(f"The adjusted difference came out at {signed} {unit} {basis}, most likely somewhere between {lo} and {hi} (a 90% range).".replace("  ", " "))
    evidence["how"] = steps
    evidence["checks"] = checks_text(confidence, demoted=False)
    evidence["limits"] = "This compares your own days. Things we can't see, like stress, illness or travel, can also play a part, so it's a strong clue and not proof."
    return evidence

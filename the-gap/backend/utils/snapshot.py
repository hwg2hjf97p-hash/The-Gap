"""
Builds a lightweight "today's snapshot" from a user's cleaned daily
DataFrame — works for Whoop, Oura, or any future source, since they all
funnel into the same column-name convention.

This is intentionally separate from the causal engine (causal/engine.py).
The causal engine looks for statistically validated cause-and-effect
relationships and needs real day-count to say anything with confidence.
This snapshot is the opposite: cheap, always-available, honestly-labeled
raw description of the data — latest values, simple trends, and raw
correlations — so there's something concrete to show even on day 1,
without ever claiming those raw correlations are causal.
"""

from __future__ import annotations

import pandas as pd

# Metrics worth surfacing as "latest reading" cards, with display metadata.
METRIC_DISPLAY = {
    "hrv": {"label": "HRV", "unit": "ms", "higher_is_better": True},
    "resting_hr": {"label": "Resting heart rate", "unit": "bpm", "higher_is_better": False},
    "sleep_total_min": {"label": "Sleep", "unit": "hrs", "higher_is_better": True, "divide_by": 60},
    "recovery_score": {"label": "Recovery score", "unit": "%", "higher_is_better": True},
    "sleep_score": {"label": "Sleep performance", "unit": "%", "higher_is_better": True},
    "steps": {"label": "Steps", "unit": "", "higher_is_better": True},
    "weight_kg": {"label": "Weight", "unit": "kg", "higher_is_better": None},
    "dietary_energy": {"label": "Calories", "unit": "kcal", "higher_is_better": None},
    "protein_g": {"label": "Protein", "unit": "g", "higher_is_better": None},
    "carbs_g": {"label": "Carbs", "unit": "g", "higher_is_better": None},
    "fat_g": {"label": "Fat", "unit": "g", "higher_is_better": None},
}

# Candidate raw-correlation pairs to check, in priority order.
# (column_a, column_b, human-readable description template)
CANDIDATE_PAIRS = [
    ("sleep_total_min", "hrv_next", "Sleep duration vs. next-day HRV"),
    ("sleep_total_min", "resting_hr_next", "Sleep duration vs. next-day resting heart rate"),
    ("hrv_lag1", "recovery_score", "Prior-day HRV vs. recovery score"),
    ("sleep_debt", "recovery_score", "Sleep debt vs. recovery score"),
    ("is_weekend", "sleep_total_min", "Weekends vs. sleep duration"),
    ("steps", "sleep_total_min", "Daily steps vs. same-night sleep duration"),
]


def _trend(series: pd.Series) -> str:
    """Compare the most recent value against the prior 7-day average."""
    clean = series.dropna()
    if len(clean) < 2:
        return "flat"
    latest = clean.iloc[-1]
    baseline = clean.iloc[:-1].tail(7).mean()
    if pd.isna(baseline) or baseline == 0:
        return "flat"
    pct_change = (latest - baseline) / abs(baseline)
    if pct_change > 0.03:
        return "up"
    if pct_change < -0.03:
        return "down"
    return "flat"


def build_snapshot(df: pd.DataFrame) -> dict:
    """
    Returns a JSON-serialisable dict:
    {
      "days_of_data": int,
      "latest": [ {metric, label, value, unit, trend, is_improving}, ... ],
      "raw_signals": [ {description, r, direction, n, strength_label}, ... ]
    }
    Empty/short data returns a valid, mostly-empty shape rather than erroring —
    callers should always be able to render *something* from this.
    """
    if df is None or df.empty:
        return {"days_of_data": 0, "latest": [], "raw_signals": []}

    latest_cards = []
    for col, meta in METRIC_DISPLAY.items():
        if col not in df.columns:
            continue
        series = df[col]
        clean = series.dropna()
        if clean.empty:
            continue
        value = clean.iloc[-1]
        divide_by = meta.get("divide_by", 1)
        display_value = round(value / divide_by, 1) if divide_by != 1 else round(float(value), 1)
        trend = _trend(series)
        is_improving = None
        if trend != "flat" and meta["higher_is_better"] is not None:
            went_up = trend == "up"
            is_improving = went_up if meta["higher_is_better"] else not went_up
        recent = [
            round(v / divide_by, 1) if divide_by != 1 else round(float(v), 1)
            for v in clean.tail(7).tolist()
        ]
        latest_cards.append(
            {
                "metric": col,
                "label": meta["label"],
                "value": display_value,
                "unit": meta["unit"],
                "trend": trend,
                "is_improving": is_improving,
                "recent": recent,
            }
        )

    raw_signals = []
    n_rows = len(df)
    if n_rows >= 5:
        for col_a, col_b, description in CANDIDATE_PAIRS:
            if col_a not in df.columns or col_b not in df.columns:
                continue
            paired = df[[col_a, col_b]].dropna()
            n = len(paired)
            if n < 5:
                continue
            r = paired[col_a].corr(paired[col_b])
            if r is None or pd.isna(r) or abs(r) < 0.2:
                continue  # too weak to be worth showing, even as a raw signal
            strength = "strong" if abs(r) >= 0.5 else "moderate"
            raw_signals.append(
                {
                    "description": description,
                    "r": round(float(r), 2),
                    "direction": "positive" if r > 0 else "negative",
                    "n": n,
                    "strength_label": strength,
                }
            )
        # Strongest first, cap at 4 so the panel stays scannable
        raw_signals.sort(key=lambda s: abs(s["r"]), reverse=True)
        raw_signals = raw_signals[:4]

    return {
        "days_of_data": n_rows,
        "latest": latest_cards,
        "raw_signals": raw_signals,
    }

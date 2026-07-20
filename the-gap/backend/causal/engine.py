"""
Causal Engine — orchestrates all hypothesis tests against a user's data.
Runs each hypothesis through LinearDML, returns a list of Insight objects.
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from causal.hypotheses import HYPOTHESES, Hypothesis
from causal.estimator import run_linear_dml
from causal.interpreter import interpret_result
from models.insight import Insight, ConfidenceLevel

logger = logging.getLogger(__name__)

# Minimum meaningful effect sizes — below these the result is noise, not signal.
# Values are in the natural unit of each outcome column.
MIN_EFFECT = {
    "hrv_next":           0.8,   # ms  — less than 0.8ms HRV change is not meaningful
    "sleep_deep_min":     1.5,   # min — less than 1.5 min deep sleep change is noise
    "sleep_total_min":    3.0,   # min — less than 3 min total sleep change is noise
    "resting_hr_next":    0.3,   # bpm — less than 0.3 bpm RHR change is noise
    "steps":            200.0,   # steps
}
DEFAULT_MIN_EFFECT = 0.5


def get_experiments_in_progress(df: pd.DataFrame) -> list[dict]:
    """
    For every hypothesis that doesn't yet have enough data to run, report
    how close it is — this is what powers the "Running on you" progress
    list (e.g. "Day 4 of 14"). Uses the exact same sufficiency check as
    _run_one, so this never claims something is "in progress" when it's
    actually already been tested (or never will be, for lack of a
    connected data source).
    """
    experiments = []
    for hyp in HYPOTHESES:
        required = [hyp.treatment_col, hyp.outcome_col] + (hyp.covariate_cols or [])
        if any(c not in df.columns for c in required):
            continue  # no relevant data source connected at all — nothing to show

        cols = list({hyp.treatment_col, hyp.outcome_col, *(hyp.covariate_cols or [])})
        sub = df[cols].dropna()

        if hyp.binary_treatment:
            current = int(sub[hyp.treatment_col].sum())
            required_n = hyp.min_treated_days
        else:
            current = len(sub)
            required_n = hyp.min_rows

        if current >= required_n:
            continue  # already sufficient — will surface as an insight instead

        experiments.append({
            "id": hyp.id,
            "treatment_label": hyp.treatment_label,
            "outcome_label": hyp.outcome_label,
            "category": hyp.category,
            "current": current,
            "required": required_n,
        })

    # Closest-to-done first — most encouraging order to show someone
    experiments.sort(key=lambda e: (e["required"] - e["current"]))
    return experiments


def run_all_hypotheses(df: pd.DataFrame) -> list[Insight]:
    """
    Iterate over every pre-defined hypothesis.
    Skip those with insufficient data or near-zero effects.
    Return a sorted list of Insight objects.
    """
    insights: list[Insight] = []

    for hyp in HYPOTHESES:
        try:
            insight = _run_one(df, hyp)
            if insight is not None:
                insights.append(insight)
        except Exception as exc:
            logger.warning("Hypothesis %s failed: %s", hyp.id, exc)
            continue

    # Sort: strong confidence first, then moderate, then weak
    order = {ConfidenceLevel.STRONG: 0, ConfidenceLevel.MODERATE: 1, ConfidenceLevel.WEAK: 2}
    insights.sort(key=lambda i: order.get(i.confidence, 3))

    return insights


def _run_one(df: pd.DataFrame, hyp: Hypothesis) -> Optional[Insight]:
    """
    Run a single hypothesis. Returns None if data is insufficient or effect is trivially small.
    """
    # ── 1. Check required columns exist ───────────────────────────────────
    required = [hyp.treatment_col, hyp.outcome_col] + (hyp.covariate_cols or [])
    missing = [c for c in required if c not in df.columns]
    if missing:
        logger.debug("Skipping %s — missing columns: %s", hyp.id, missing)
        return None

    # ── 2. Build working sub-frame ─────────────────────────────────────────
    cols = list({hyp.treatment_col, hyp.outcome_col, *(hyp.covariate_cols or [])})
    sub = df[cols].dropna()

    # ── 3. Check minimum row count ─────────────────────────────────────────
    if len(sub) < hyp.min_rows:
        logger.debug(
            "Skipping %s — only %d rows (need %d)", hyp.id, len(sub), hyp.min_rows
        )
        return None

    # ── 4. Extra cardinality check for binary treatment hypotheses ─────────
    if hyp.binary_treatment:
        n_treated = sub[hyp.treatment_col].sum()
        if n_treated < hyp.min_treated_days:
            logger.debug(
                "Skipping %s — only %d treated days (need %d)",
                hyp.id,
                int(n_treated),
                hyp.min_treated_days,
            )
            return None

    # ── 5. Run LinearDML ───────────────────────────────────────────────────
    result = run_linear_dml(
        df=sub,
        treatment_col=hyp.treatment_col,
        outcome_col=hyp.outcome_col,
        covariate_cols=hyp.covariate_cols or [],
        binary_treatment=hyp.binary_treatment,
    )

    if result is None:
        logger.info("ESTIMATION_RETURNED_NONE hyp=%s rows=%d — see estimator.py logs above for the actual cause", hyp.id, len(sub))
        return None

    # ── 6. Filter out near-zero / trivially small effects ─────────────────
    min_effect = MIN_EFFECT.get(hyp.outcome_col, DEFAULT_MIN_EFFECT)
    if abs(result["effect"]) < min_effect:
        logger.info(
            "FILTERED_SMALL_EFFECT hyp=%s effect=%.4f threshold=%.4f n_obs=%d p_value=%s",
            hyp.id, result["effect"], min_effect, result["n_obs"], result.get("p_value"),
        )
        return None

    # ── 7. Interpret → Insight ─────────────────────────────────────────────
    return interpret_result(
        hypothesis=hyp,
        effect=result["effect"],
        ci_low=result["ci_low"],
        ci_high=result["ci_high"],
        n_obs=result["n_obs"],
        p_value=result.get("p_value"),
    )

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


def run_all_hypotheses(df: pd.DataFrame) -> list[Insight]:
    """
    Iterate over every pre-defined hypothesis.
    Skip those with insufficient data.
    Return a list of Insight objects (max 7, typically 3–5 will pass).
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
    Run a single hypothesis.  Returns None if data is insufficient.
    """
    # ── 1. Check required columns exist ───────────────────────────────────
    required = [hyp.treatment_col, hyp.outcome_col] + (hyp.covariate_cols or [])
    missing = [c for c in required if c not in df.columns]
    if missing:
        logger.debug("Skipping %s — missing columns: %s", hyp.id, missing)
        return None

    # ── 2. Build working sub-frame ─────────────────────────────────────────
    cols = list({hyp.treatment_col, hyp.outcome_col, *( hyp.covariate_cols or [])})
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
        return None

    # ── 6. Interpret → Insight ─────────────────────────────────────────────
    return interpret_result(
        hypothesis=hyp,
        effect=result["effect"],
        ci_low=result["ci_low"],
        ci_high=result["ci_high"],
        n_obs=result["n_obs"],
        p_value=result.get("p_value"),
    )

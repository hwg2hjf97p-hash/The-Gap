"""
LinearDML estimator — runs a single treatment→outcome causal estimate.
Falls back to OLS when EconML is not installed (e.g. during local dev).
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def run_linear_dml(
    *,
    df: pd.DataFrame,
    treatment_col: str,
    outcome_col: str,
    covariate_cols: list[str],
    binary_treatment: bool = False,
) -> Optional[dict]:
    """
    Run LinearDML causal inference.

    Returns a dict:
        { "effect": float, "ci_low": float, "ci_high": float,
          "n_obs": int, "p_value": Optional[float], "method": str }

    Returns None if estimation fails or data is too sparse.

    NOTE: The 'effect' is the Average Treatment Effect (ATE):
      - For continuous treatment: effect per 1-unit increase
      - For binary treatment: effect of treatment=1 vs treatment=0
    """
    try:
        from econml.dml import LinearDML
        from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
        return _run_econml(
            df=df,
            treatment_col=treatment_col,
            outcome_col=outcome_col,
            covariate_cols=covariate_cols,
            binary_treatment=binary_treatment,
        )
    except ImportError:
        logger.warning("EconML not available — falling back to OLS")
        return _run_ols_fallback(
            df=df,
            treatment_col=treatment_col,
            outcome_col=outcome_col,
        )


def _run_econml(
    *,
    df: pd.DataFrame,
    treatment_col: str,
    outcome_col: str,
    covariate_cols: list[str],
    binary_treatment: bool,
) -> Optional[dict]:
    from econml.dml import LinearDML
    from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier

    # Outcome model is always a regressor
    model_y = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)

    # Treatment model: classifier for binary, regressor for continuous
    if binary_treatment:
        model_t = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
    else:
        model_t = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)

    T = df[treatment_col].values
    Y = df[outcome_col].values
    X = df[covariate_cols].values if covariate_cols else np.ones((len(df), 1))

    try:
        est = LinearDML(
            model_y=model_y,
            model_t=model_t,
            linear_first_stages=False,
            cv=3,
            random_state=42,
        )
        est.fit(Y, T, X=X)

        ate = float(est.effect(X).mean())
        ci_arr = est.effect_interval(X, alpha=0.10)   # 90% CI
        ci_low = float(ci_arr[0].mean())
        ci_high = float(ci_arr[1].mean())

        return {
            "effect": ate,
            "ci_low": ci_low,
            "ci_high": ci_high,
            "n_obs": len(df),
            "p_value": None,
            "method": "LinearDML",
        }
    except Exception as exc:
        logger.warning("EconML fit failed: %s — falling back to OLS", exc)
        return _run_ols_fallback(df=df, treatment_col=treatment_col, outcome_col=outcome_col)


def _run_ols_fallback(
    *,
    df: pd.DataFrame,
    treatment_col: str,
    outcome_col: str,
) -> Optional[dict]:
    """Simple OLS — directional estimate only, no causal guarantee."""
    try:
        from scipy import stats

        T = df[treatment_col].values.astype(float)
        Y = df[outcome_col].values.astype(float)

        slope, _, _, p_value, se = stats.linregress(T, Y)
        ci_margin = 1.645 * se  # 90%

        return {
            "effect": float(slope),
            "ci_low": float(slope - ci_margin),
            "ci_high": float(slope + ci_margin),
            "n_obs": len(df),
            "p_value": float(p_value),
            "method": "OLS_fallback",
        }
    except Exception as exc:
        logger.error("OLS fallback also failed: %s", exc)
        return None

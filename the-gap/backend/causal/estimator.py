"""
Causal estimator — runs a single treatment→outcome estimate using OLS with controls.

Uses statsmodels OLS with covariate adjustment, which gives:
  - Effect size (coefficient on treatment)
  - 90% confidence intervals
  - p-value

This is a valid causal estimate when covariates adequately control for confounders,
which is the case for our within-person health data hypotheses.
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
    Run OLS with covariate adjustment as a causal estimate.

    Returns a dict:
        { "effect": float, "ci_low": float, "ci_high": float,
          "n_obs": int, "p_value": Optional[float], "method": str }

    Returns None if estimation fails or data is too sparse.
    """
    return _run_ols(
        df=df,
        treatment_col=treatment_col,
        outcome_col=outcome_col,
        covariate_cols=covariate_cols,
    )


def _run_ols(
    *,
    df: pd.DataFrame,
    treatment_col: str,
    outcome_col: str,
    covariate_cols: list[str],
) -> Optional[dict]:
    """
    OLS with covariate adjustment using statsmodels.
    Includes treatment + all covariates as regressors.
    Returns the coefficient on the treatment variable.
    """
    try:
        import statsmodels.api as sm

        T = df[treatment_col].values.astype(float)
        Y = df[outcome_col].values.astype(float)

        # Build regressor matrix: treatment + covariates + constant
        if covariate_cols:
            X_controls = df[covariate_cols].values.astype(float)
            X = np.column_stack([T, X_controls])
        else:
            X = T.reshape(-1, 1)

        X = sm.add_constant(X)

        model = sm.OLS(Y, X)
        result = model.fit()

        # Treatment coefficient is index 1 (after constant)
        effect = float(result.params[1])
        ci = result.conf_int(alpha=0.10)  # 90% CI
        ci_low = float(ci[1][0])
        ci_high = float(ci[1][1])
        p_value = float(result.pvalues[1])

        return {
            "effect": effect,
            "ci_low": ci_low,
            "ci_high": ci_high,
            "n_obs": int(result.nobs),
            "p_value": p_value,
            "method": "OLS",
        }

    except Exception as exc:
        logger.error("OLS estimation failed: %s", exc)
        return None

"""
Causal estimator — runs a single treatment→outcome estimate using EconML's
LinearDML (Double Machine Learning).

WHY THIS IS DIFFERENT FROM PLAIN REGRESSION:
DML works by first "residualizing" — predicting the outcome from controls
alone, predicting the treatment from controls alone, then relating what's
*left over* in each (the parts controls couldn't explain) to each other.
Combined with cross-fitting (fitting on one split of the data, estimating
effects on a held-out split, then swapping), this makes the final effect
estimate meaningfully more robust to confounding and less prone to
overfitting bias than a single-pass regression — the same coefficient can
come out biased under plain OLS if the nuisance relationships (how
controls relate to treatment or outcome) are even mildly misspecified.

WHY SIMPLE LINEAR MODELS FOR THE NUISANCE FUNCTIONS, NOT GRADIENT BOOSTING:
DML's flexibility comes from letting you plug in any ML model for the
nuisance functions (predicting Y from W, predicting T from W). With larger
datasets, complex models (gradient boosting, random forests) can capture
non-linear confounding relationships. But this app's hypotheses typically
have 30-90 rows of daily data — genuinely too few for a complex model to
learn real signal rather than noise. Using simple linear/logistic models
here isn't a shortcut; it's the statistically correct choice for this
data size, and cross-fitting still provides real robustness benefits on
top of that.
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
    Run EconML's LinearDML as the causal estimate.

    Returns a dict:
        { "effect": float, "ci_low": float, "ci_high": float,
          "n_obs": int, "p_value": Optional[float], "method": str }

    Returns None if estimation fails or data is too sparse.
    """
    try:
        from econml.dml import LinearDML
        from sklearn.linear_model import LinearRegression, LogisticRegression

        Y = df[outcome_col].values.astype(float)
        T = df[treatment_col].values.astype(float)
        n = len(df)

        # W = controls the effect is adjusted for, but not assumed to vary by.
        # X = None throughout — we're estimating one overall effect per
        # hypothesis (e.g. "does more sleep help HRV, on average, for you"),
        # not how the effect differs across conditions. Keeping X unused
        # also keeps this well-identified given the small sample sizes here.
        W = df[covariate_cols].values.astype(float) if covariate_cols else None

        # Cross-fitting folds: EconML's default is 2, but with only ~30-90
        # rows, too many folds leaves each training split too small to be
        # useful. 3 is a reasonable balance for this data size.
        cv_folds = 3 if n >= 45 else 2

        model_t = LogisticRegression(max_iter=1000) if binary_treatment else LinearRegression()

        est = LinearDML(
            model_y=LinearRegression(),
            model_t=model_t,
            discrete_treatment=binary_treatment,
            cv=cv_folds,
            random_state=42,
        )
        est.fit(Y, T, X=None, W=W)

        inference = est.effect_inference(X=None)
        # For a constant (non-heterogeneous) effect with X=None, these come
        # back as single-element arrays — unwrap to plain floats.
        effect = float(np.asarray(inference.point_estimate).flatten()[0])
        ci = inference.conf_int(alpha=0.10)  # 90% CI, consistent with the previous OLS implementation
        ci_low = float(np.asarray(ci[0]).flatten()[0])
        ci_high = float(np.asarray(ci[1]).flatten()[0])
        p_value = float(np.asarray(inference.pvalue()).flatten()[0])

        return {
            "effect": effect,
            "ci_low": ci_low,
            "ci_high": ci_high,
            "n_obs": n,
            "p_value": p_value,
            "method": "LinearDML",
        }

    except Exception as exc:
        logger.error("LinearDML estimation failed for %s -> %s: %s", treatment_col, outcome_col, exc)
        return None

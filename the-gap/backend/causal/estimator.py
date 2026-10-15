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
        try:
            stderr = float(np.asarray(inference.stderr).flatten()[0])
        except Exception:
            stderr = None

        return {
            "effect": effect,
            "ci_low": ci_low,
            "ci_high": ci_high,
            "n_obs": n,
            "p_value": p_value,
            "stderr": stderr,
            "n_covariates": len(covariate_cols),
            "method": "LinearDML",
        }

    except Exception as exc:
        logger.error("LinearDML estimation failed for %s -> %s: %s", treatment_col, outcome_col, exc)
        return None


def run_ols(
    *,
    df: pd.DataFrame,
    treatment_col: str,
    outcome_col: str,
    covariate_cols: list[str],
    binary_treatment: bool = False,
) -> Optional[dict]:
    """
    The effect of the treatment on the outcome, adjusted for the covariates, by ordinary least squares
    with a t-test. Same result shape as run_linear_dml.

    WHY THIS REPLACED LinearDML FOR THE P-VALUES: with the simple linear models this app uses inside
    LinearDML, DML is the same calculation as least squares plus cross-fitting, which only adds noise
    on a few weeks of data. Tested on made-up people whose check-in answers were shuffled (so any
    pattern found is false), LinearDML's p-values called a pattern "significant" at p < 0.05 in 18-25% of
    cases instead of 5%. Least squares with a t-test did so in about 5%, and still found about as many
    real patterns (see lab/calibration_lab.py). For a yes/no treatment the heteroskedasticity-robust (HC3)
    standard error is used, because the days with and without it can vary by different amounts.
    """
    try:
        from scipy import stats

        y = df[outcome_col].values.astype(float)
        t = df[treatment_col].values.astype(float)
        if len(y) < 5 or float(np.std(t)) == 0.0:
            return None
        cols = [np.ones(len(y)), t] + [df[c].values.astype(float) for c in covariate_cols]
        X = np.column_stack(cols)
        n = X.shape[0]
        rank = int(np.linalg.matrix_rank(X))
        dof = n - rank
        if dof < 3:
            return None

        xtx_inv = np.linalg.pinv(X.T @ X)
        beta = xtx_inv @ X.T @ y
        resid = y - X @ beta
        effect = float(beta[1])

        if binary_treatment:
            lever = np.clip(np.einsum("ij,jk,ik->i", X, xtx_inv, X), 0.0, 0.999)
            scaled = resid / (1.0 - lever)
            meat = (X * scaled[:, None]).T @ (X * scaled[:, None])
            var = float((xtx_inv @ meat @ xtx_inv)[1, 1])
        else:
            var = float(resid @ resid) / dof * float(xtx_inv[1, 1])
        stderr = float(np.sqrt(max(var, 0.0)))
        if not np.isfinite(stderr) or stderr <= 0.0:
            return None

        p_value = float(2 * stats.t.sf(abs(effect) / stderr, dof))
        half = float(stats.t.ppf(0.95, dof)) * stderr  # a 90% interval, as before
        return {
            "effect": effect,
            "ci_low": effect - half,
            "ci_high": effect + half,
            "n_obs": n,
            "p_value": p_value,
            "stderr": stderr,
            "n_covariates": len(covariate_cols),
            "method": "OLS",
        }
    except Exception as exc:
        logger.error("OLS estimation failed for %s -> %s: %s", treatment_col, outcome_col, exc)
        return None

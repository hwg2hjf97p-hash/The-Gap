import numpy as np
import pandas as pd
import pytest

pytest.importorskip("scipy")

from causal import engine  # noqa: E402
from causal.estimator import run_ols  # noqa: E402


def frame(n, effect, seed, binary=False):
    rng = np.random.default_rng(seed)
    w = rng.normal(0, 1, n)
    t = (rng.random(n) < 0.35).astype(float) if binary else rng.normal(0, 1, n)
    y = effect * t + 0.6 * w + rng.normal(0, 1, n)
    return pd.DataFrame({"t": t, "y": y, "w": w})


def fit(df, binary=False):
    return run_ols(df=df, treatment_col="t", outcome_col="y", covariate_cols=["w"], binary_treatment=binary)


def test_it_recovers_a_real_effect_and_the_interval_covers_it():
    r = fit(frame(60, 1.5, 1))
    assert r is not None and r["method"] == "OLS"
    assert r["ci_low"] < 1.5 < r["ci_high"] and r["p_value"] < 0.01 and r["n_obs"] == 60


def test_it_recovers_a_yes_no_effect_with_few_treated_days():
    r = fit(frame(26, 2.0, 5, binary=True), binary=True)
    assert r is not None and r["effect"] > 0 and r["ci_low"] < r["effect"] < r["ci_high"]


def test_with_no_real_effect_it_cries_wolf_about_as_often_as_promised():
    for binary in (False, True):
        hits = 0
        runs = 300
        for seed in range(runs):
            r = fit(frame(24, 0.0, 1000 + seed, binary=binary), binary=binary)
            if r is not None and r["p_value"] < 0.05:
                hits += 1
        assert 0.01 <= hits / runs <= 0.10, f"binary={binary} false alarm rate {hits / runs:.3f}"


def test_a_treatment_that_never_varies_gives_nothing():
    df = frame(30, 0.0, 3)
    df["t"] = 1.0
    assert fit(df) is None


def test_too_few_days_for_the_number_of_things_adjusted_for_gives_nothing():
    df = frame(5, 1.0, 4)
    assert run_ols(df=df, treatment_col="t", outcome_col="y", covariate_cols=["w", "w", "w"], binary_treatment=False) is None


def test_the_engine_can_use_it_end_to_end(monkeypatch):
    monkeypatch.setattr(engine, "ESTIMATOR", "ols")
    df = frame(40, 2.0, 9)
    hyp = engine.Hypothesis(id="t_y", treatment_col="t", outcome_col="y", treatment_label="T", outcome_label="Y", covariate_cols=["w"], min_rows=30)
    out = engine.estimate(df, hyp, ["w"])
    assert out is not None and out["method"] == "OLS"

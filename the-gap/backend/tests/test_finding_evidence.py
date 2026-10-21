import numpy as np
import pandas as pd
import pytest

from causal import engine
from causal.evidence import build_evidence, checks_text, size_word
from causal.hypotheses import HYPOTHESES

BY_ID = {h.id: h for h in HYPOTHESES}


def frame(n=70, seed=3):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-08-01", periods=n)
    drinks = (rng.random(n) < 0.35).astype(float)
    hrv_lag = rng.normal(60, 5, n)
    hrv_next = 62 - 7 * drinks + rng.normal(0, 3, n)
    return pd.DataFrame(
        {"alcohol_flag": drinks, "hrv_next": hrv_next, "hrv_lag1": hrv_lag, "sleep_total_min": rng.normal(430, 30, n), "day_of_week": idx.dayofweek.astype(float), "is_weekend": (idx.dayofweek >= 5).astype(float)},
        index=idx,
    )


def result_for(df, hyp):
    """The days the engine would use and a made-up estimate of the effect (the statistics library isn't needed to test the evidence)."""
    sub, covs = engine.working_frame(df, hyp)
    t, y = sub[hyp.treatment_col], sub[hyp.outcome_col]
    if hyp.binary_treatment:
        effect = float(y[t > 0].mean() - y[t <= 0].mean())
    else:
        effect = float(np.polyfit(t.values, y.values, 1)[0])
    return sub, covs, {"effect": effect, "ci_low": effect - 2.0, "ci_high": effect + 2.0, "n_obs": len(sub), "p_value": 0.01}


def test_a_yes_no_finding_carries_days_with_and_without_and_the_steps_taken():
    hyp = BY_ID["alcohol_hrv"]
    df = frame()
    sub, covs, result = result_for(df, hyp)
    ev = build_evidence(sub=sub, hyp=hyp, result=result, covs_used=covs, higher_is_better=True, confidence="moderate")
    assert ev["kind"] == "binary" and ev["unit"] == "ms"
    with_, without = ev["groups"]["with"], ev["groups"]["without"]
    assert with_["n"] + without["n"] == ev["n"] and with_["mean"] < without["mean"]
    assert with_["min"] <= with_["p25"] <= with_["p75"] <= with_["max"]
    assert ev["outcome"]["best"] == ev["outcome"]["max"] and ev["outcome"]["worst"] == ev["outcome"]["min"]  # a higher HRV is better
    assert ev["effect"]["low"] < ev["effect"]["value"] < ev["effect"]["high"]
    assert len(ev["timeline"]) == 45 and {p["l"] for p in ev["timeline"]} <= {0, 1}
    how = " ".join(ev["how"])
    assert f"{ev['n']} days" in how and "accounting for" in how and "90% range" in how
    assert ev["groups"]["raw_difference"] < 0


def test_the_effect_is_put_next_to_the_persons_own_swing():
    hyp = BY_ID["alcohol_hrv"]
    sub, covs, result = result_for(frame(), hyp)
    ev = build_evidence(sub=sub, hyp=hyp, result=result, covs_used=covs, higher_is_better=True, confidence="strong")
    assert ev["size"]["word"] in {"small", "modest", "clear", "large"} and ev["size"]["share_of_swing"] > 0


def test_size_words_follow_the_share_of_the_persons_own_swing():
    assert size_word(1, 10) == "small" and size_word(3, 10) == "modest" and size_word(6, 10) == "clear" and size_word(9, 10) == "large"
    assert size_word(5, 0) is None and size_word(5, None) is None


def test_an_amount_finding_gets_lower_middle_and_higher_days_and_a_scatter():
    rng = np.random.default_rng(5)
    n = 80
    idx = pd.date_range("2026-08-01", periods=n)
    steps = rng.normal(9000, 3000, n).clip(1000)
    df = pd.DataFrame(
        {"steps": steps, "hrv_next": 50 + 0.004 * steps + rng.normal(0, 3, n), "hrv_lag1": rng.normal(60, 5, n), "sleep_total_min": rng.normal(430, 30, n),
         "resting_hr": rng.normal(55, 3, n), "day_of_week": idx.dayofweek.astype(float)},
        index=idx,
    )
    hyp = BY_ID["steps_hrv"]
    sub, covs, result = result_for(df, hyp)
    result = engine._scaled(result, hyp)
    assert result["effect"] > 0
    ev = build_evidence(sub=sub, hyp=hyp, result=result, covs_used=covs, higher_is_better=True, confidence="strong")
    assert ev["kind"] == "amount" and [b["name"] for b in ev["bins"]] == ["lower", "middle", "higher"]
    assert ev["bins"][0]["mean"] < ev["bins"][2]["mean"]  # more steps, higher HRV in this made-up person
    assert len(ev["points"]) == 60 and ev["trend"]["y1"] > ev["trend"]["y0"]
    assert "ranged from" in " ".join(ev["how"])


def test_the_engine_attaches_it_to_a_finding_and_it_survives_saving():
    pytest.importorskip("scipy")  # the real estimate needs it; the plain test run doesn't install it
    hyp = BY_ID["alcohol_hrv"]
    insight = engine._run_one(frame(90), hyp)
    assert insight is not None and insight.evidence["groups"]["with"]["n"] > 0
    assert insight.to_dict()["evidence"]["kind"] == "binary"


def test_a_downgraded_finding_says_why():
    assert "stricter check" in checks_text("weak", demoted=True)
    assert "passed that check" in checks_text("moderate", demoted=False)
    assert "could still be chance" in checks_text("weak", demoted=False)


def test_too_little_data_gives_no_evidence_rather_than_an_error():
    hyp = BY_ID["alcohol_hrv"]
    tiny = frame(4)
    assert build_evidence(sub=tiny, hyp=hyp, result={"effect": 1, "ci_low": 0, "ci_high": 2}, covs_used=[], higher_is_better=True, confidence="weak") == {}

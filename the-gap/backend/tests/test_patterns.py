from datetime import date

import numpy as np
import pandas as pd

from causal.engine import _contrast, contrast_sentence, min_effect_for
from causal.hypotheses import HYPOTHESES
from routers import checkin
from utils.data_cleaning import clean_dataframe
from utils.demo_data import generate_demo_data
from utils.patterns import CAVEAT, _fisher_p, best_vs_worst, build_patterns, tracking_suggestions

BY_ID = {h.id: h for h in HYPOTHESES}


# ── lighter days versus heavier days ─────────────────────────────────────────

def test_contrast_scales_the_per_unit_effect_across_the_persons_own_range():
    events = pd.Series([1, 1, 2, 2, 3, 3, 4, 5, 6, 6] * 3, dtype=float)
    contrast = _contrast(-4.0, events)  # 4 minutes less sleep per extra event
    assert contrast is not None
    assert contrast["low"] < contrast["high"]
    assert abs(contrast["effect"] - (-4.0 * (contrast["high"] - contrast["low"]))) < 1e-9
    assert abs(contrast["effect"]) >= 10  # "5 minutes per event" is really a 12+ minute swing between a light day and a busy one


def test_no_contrast_when_the_treatment_barely_varies():
    assert _contrast(3.0, pd.Series([2.0] * 30)) is None
    assert _contrast(3.0, pd.Series([1.0, 2.0, 3.0])) is None  # too few days


def test_the_contrast_reads_as_a_plain_sentence():
    hyp = BY_ID["event_density_sleep"]
    text = contrast_sentence(hyp, {"low": 1.0, "high": 6.0, "effect": -24.0})
    assert text == "Calendar events per day around 6 (vs 1 on your lighter days): your total sleep is about 24 minutes lower."
    steps = contrast_sentence(BY_ID["steps_hrv"], {"low": 5400.0, "high": 11200.0, "effect": 4.2})
    assert "around 11,200 (vs 5,400" in steps and "higher" in steps and "next-day HRV" in steps


def test_a_small_per_unit_effect_can_still_clear_the_bar_over_a_real_range():
    hyp = BY_ID["event_density_sleep"]
    sub = pd.DataFrame({"sleep_total_min": np.random.default_rng(2).normal(420, 40, 60)})
    bar = min_effect_for(hyp, sub)
    contrast = _contrast(-5.0, pd.Series(np.tile([0.0, 1.0, 2.0, 4.0, 6.0, 7.0], 10)))
    assert abs(-5.0) < bar < abs(contrast["effect"])  # 5 min per event fails; the 25+ min swing passes


# ── best days versus worst days ──────────────────────────────────────────────

def test_fisher_exact_p_is_sensible():
    assert _fisher_p(0, 8, 8, 0) < 0.001
    assert _fisher_p(4, 4, 4, 4) == 1.0


def _two_habits(days=60, seed=5):
    """Hand-built data: late phone use ruins sleep; steps do nothing."""
    rng = np.random.default_rng(seed)
    index = pd.date_range("2026-08-01", periods=days)
    late = (rng.random(days) < 0.4).astype(float)
    sleep = 450 - 70 * late + rng.normal(0, 15, days)
    steps = rng.normal(8000, 2500, days)
    return pd.DataFrame({"sleep_total_min": sleep, "late_screen_flag": late, "steps": steps}, index=index)


def test_the_habit_that_really_splits_best_from_worst_is_found():
    found = best_vs_worst(_two_habits())
    assert found, "expected the late-phone pattern"
    top = found[0]
    assert top["driver"] == "late_screen_flag" and top["outcome"] == "sleep_total_min"
    assert top["best_value"] < top["worst_value"]
    assert "Phone use after 11 pm" in top["headline"] and "longest-sleep nights" in top["headline"]
    assert not any(f["driver"] == "steps" for f in found)


def test_pure_noise_produces_no_patterns():
    rng = np.random.default_rng(11)
    index = pd.date_range("2026-08-01", periods=60)
    df = pd.DataFrame(
        {"sleep_total_min": rng.normal(430, 40, 60), "alcohol_flag": (rng.random(60) < 0.3).astype(float), "screen_hours": rng.normal(5, 2, 60)},
        index=index,
    )
    assert best_vs_worst(df) == []


def test_too_few_days_gives_nothing():
    assert best_vs_worst(_two_habits(days=20)) == []
    assert best_vs_worst(pd.DataFrame()) == []


def test_an_amount_habit_is_described_with_averages():
    rng = np.random.default_rng(8)
    index = pd.date_range("2026-08-01", periods=60)
    screen = rng.normal(5, 2, 60)
    df = pd.DataFrame({"sleep_total_min": 480 - 25 * screen + rng.normal(0, 10, 60), "screen_hours": screen}, index=index)
    top = best_vs_worst(df)[0]
    assert top["driver"] == "screen_hours" and top["kind"] == "amount"
    assert top["best_value"] < top["worst_value"]
    assert "Screen time that day: averaged" in top["headline"]


# ── what to log next ─────────────────────────────────────────────────────────

def test_habits_logged_on_few_recent_days_are_suggested():
    index = pd.date_range("2026-09-01", periods=40)
    df = pd.DataFrame({"hrv": 50.0, "alcohol_flag": [1.0, 0.0] * 20, "screen_hours": np.nan}, index=index)
    df.loc[index[-5:], "screen_hours"] = 4.0
    labels = [s["label"] for s in tracking_suggestions(df)]
    assert "Screen time" in labels and "Alcohol" not in labels  # alcohol is answered every day, screen time on 5 of 28
    first = next(s for s in tracking_suggestions(df) if s["label"] == "Screen time")
    assert first["answered"] == 5 and first["window"] == 28


def test_build_patterns_always_carries_the_caveat():
    result = build_patterns(_two_habits())
    assert result["caveat"] == CAVEAT and result["days"] == 60 and result["items"]
    assert build_patterns(pd.DataFrame())["items"] == []


# ── the sample data shows what the card looks like ───────────────────────────

class _FakeResponse:
    def __init__(self, rows):
        self._rows = rows

    def raise_for_status(self):
        pass

    def json(self):
        return self._rows


def test_the_sample_data_gives_clear_patterns(monkeypatch):
    health, checkins = generate_demo_data(date(2026, 10, 6))
    monkeypatch.setattr(checkin.httpx, "get", lambda *a, **k: _FakeResponse(checkins))
    health_df = pd.DataFrame.from_dict(health, orient="index")
    health_df.index = pd.to_datetime(health_df.index)
    df = clean_dataframe(health_df.join(checkin.get_checkin_dataframe("demo-user"), how="outer").sort_index())
    found = best_vs_worst(df)
    assert len(found) >= 2, [f["headline"] for f in found]
    drivers = {f["driver"] for f in found}
    assert drivers & {"late_screen_flag", "screen_hours", "alcohol_flag", "afternoon_caffeine"}

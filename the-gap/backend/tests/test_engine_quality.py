import numpy as np
import pandas as pd

from causal.engine import MIN_EFFECT, min_effect_for
from causal.hypotheses import HYPOTHESES
from utils.source_merge import merge_sources

BY_ID = {h.id: h for h in HYPOTHESES}


# ── trivial findings stay off the screen ─────────────────────────────────────

def _sub(outcome, values):
    return pd.DataFrame({outcome: values})


def test_five_minutes_of_sleep_is_not_worth_a_card():
    hyp = BY_ID["event_density_sleep"]
    sub = _sub("sleep_total_min", np.random.default_rng(1).normal(420, 50, 60))
    assert min_effect_for(hyp, sub) > 5.0


def test_the_bar_rises_with_how_much_the_person_normally_varies():
    hyp = BY_ID["steps_hrv"]
    calm = _sub("hrv_next", np.random.default_rng(1).normal(60, 2, 60))
    erratic = _sub("hrv_next", np.random.default_rng(1).normal(60, 14, 60))
    assert min_effect_for(hyp, calm) == MIN_EFFECT["hrv_next"]
    assert min_effect_for(hyp, erratic) > MIN_EFFECT["hrv_next"]


def test_a_single_row_does_not_break_the_threshold():
    hyp = BY_ID["alcohol_hrv"]
    assert min_effect_for(hyp, _sub("hrv_next", [55.0])) == MIN_EFFECT["hrv_next"]


# ── a short history on the main device must not throw away the long one ──────

def _two_devices(overlap_days=14, total_days=80):
    days = pd.date_range("2026-07-01", periods=total_days)
    rng = np.random.default_rng(3)
    apple = pd.DataFrame(
        {"hrv": 60 + rng.normal(0, 3, total_days), "sleep_total_min": 450 + rng.normal(0, 20, total_days), "resting_hr": 58 + rng.normal(0, 1, total_days)},
        index=days,
    )
    whoop_days = days[-overlap_days:]
    whoop = pd.DataFrame(
        {"hrv": 40 + rng.normal(0, 2, overlap_days), "sleep_total_min": 400 + rng.normal(0, 15, overlap_days), "resting_hr": 52 + rng.normal(0, 1, overlap_days)},
        index=whoop_days,
    )
    return {"whoop": whoop, "apple_health": apple}


def test_the_default_keeps_the_whole_history_for_sleep_and_hrv():
    merged = merge_sources(_two_devices(), None)
    assert merged["hrv"].notna().sum() == 80
    assert merged["sleep_total_min"].notna().sum() == 80
    assert merged["resting_hr"].notna().sum() == 80


def test_the_main_device_wins_on_the_days_it_has():
    frames = _two_devices()
    merged = merge_sources(frames, None)
    whoop = frames["whoop"]
    assert np.allclose(merged.loc[whoop.index, "hrv"].values, whoop["hrv"].values)


def test_the_older_device_is_lined_up_with_the_main_one():
    merged = merge_sources(_two_devices(), None)
    older = merged["hrv"].iloc[:60]
    recent = merged["hrv"].iloc[-14:]
    # Apple's raw level is ~60 and Whoop's ~40; after lining up the old days sit near the new ones.
    assert abs(older.mean() - recent.mean()) < 4
    sleep_older = merged["sleep_total_min"].iloc[:60].mean()
    sleep_recent = merged["sleep_total_min"].iloc[-14:].mean()
    assert abs(sleep_older - sleep_recent) < 15


def test_too_little_overlap_leaves_the_older_device_as_it_is():
    merged = merge_sources(_two_devices(overlap_days=4), None)
    assert merged["hrv"].notna().sum() == 80
    assert abs(merged["hrv"].iloc[0] - 60) < 10  # not shifted towards Whoop's 40


def test_filling_can_still_be_switched_off():
    merged = merge_sources(_two_devices(), {"fill_gaps": {"sleep": False, "recovery": False}})
    assert merged["hrv"].notna().sum() == 14
    assert merged["sleep_total_min"].notna().sum() == 14

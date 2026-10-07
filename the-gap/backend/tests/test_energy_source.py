import numpy as np
import pandas as pd

from routers.sources import CAN_SUPPLY, group_notes
from utils.source_merge import DEFAULT_FILL_GAPS, GROUPS, merge_sources


def _frames(days=60, whoop_days=20):
    index = pd.date_range("2026-08-01", periods=days)
    rng = np.random.default_rng(4)
    activity = rng.normal(0, 60, days)
    apple = pd.DataFrame({"steps": 8000 + rng.normal(0, 1500, days), "active_energy": 500 + activity}, index=index)
    # Whoop reports the whole day's energy: far higher, but it moves with activity.
    whoop = pd.DataFrame({"active_energy": 2500 + activity[-whoop_days:]}, index=index[-whoop_days:])
    return {"apple_health": apple, "whoop": whoop}


def test_calories_burned_is_its_own_choice_separate_from_steps():
    assert "active_energy" in GROUPS["energy"] and "active_energy" not in GROUPS["activity"]
    assert DEFAULT_FILL_GAPS["energy"] is True


def test_options_only_list_sources_that_really_report_the_reading():
    assert "whoop" not in CAN_SUPPLY["activity"]          # Whoop has no steps
    assert "strava" not in CAN_SUPPLY["activity"] and "strava" not in CAN_SUPPLY["energy"]
    assert "whoop" in CAN_SUPPLY["energy"]
    assert CAN_SUPPLY["body"] == ["withings"]             # Apple Health has no weight here


def test_the_default_for_calories_is_apple_health_and_steps_are_untouched():
    frames = _frames()
    merged = merge_sources(frames, None)
    assert np.allclose(merged["active_energy"].values, frames["apple_health"]["active_energy"].values)
    assert np.allclose(merged["steps"].values, frames["apple_health"]["steps"].values)


def test_choosing_whoop_uses_whoop_and_lines_the_rest_up_to_it():
    frames = _frames()
    merged = merge_sources(frames, {"primary": {"energy": "whoop"}})
    whoop = frames["whoop"]
    assert np.allclose(merged.loc[whoop.index, "active_energy"].values, whoop["active_energy"].values)
    older = merged["active_energy"].iloc[:30]
    assert older.notna().all()
    assert 2300 < older.mean() < 2700      # Apple's ~500 is shifted up to Whoop's level, not left 2,000 kcal lower
    assert (merged["steps"].values == frames["apple_health"]["steps"].values).all()  # steps still come from Apple


def test_whoop_never_replaces_steps():
    merged = merge_sources(_frames(), {"primary": {"activity": "whoop"}})
    assert (merged["steps"].values == _frames()["apple_health"]["steps"].values).all()


def test_notes_explain_why_a_source_is_missing_or_different():
    steps = group_notes("activity", ["whoop", "strava", "apple_health"])
    assert any("Whoop doesn't record" in n for n in steps) and any("Strava" in n for n in steps)
    assert group_notes("activity", ["apple_health"]) == []
    assert any("whole day" in n for n in group_notes("energy", ["whoop", "apple_health"]))
    assert group_notes("energy", ["apple_health"]) == []

import math

import pandas as pd
import pytest

from routers import checkin
from routers import workouts


class _FakeResponse:
    def __init__(self, rows):
        self._rows = rows

    def raise_for_status(self):
        pass

    def json(self):
        return self._rows


def _patch_get(monkeypatch, module, rows):
    monkeypatch.setattr(module.httpx, "get", lambda *a, **k: _FakeResponse(rows))


def _is_nan(value):
    return value is None or (isinstance(value, float) and math.isnan(value))


def test_checkin_dataframe_turns_answers_into_engine_columns(monkeypatch):
    rows = [
        {
            "date": "2026-10-01", "alcohol": False, "afternoon_caffeine": False, "stress_score": 3,
            "alcohol_drinks": 0, "energy_drinks": 0, "energy_drink_time": None, "cigarettes": 0,
            "gambling_minutes": 0, "substance_use": None, "work_hours": 8, "work_finish": "after_10pm",
            "argument_count": 0, "travel_hours": 0,
        },
        {
            "date": "2026-10-02", "alcohol": True, "afternoon_caffeine": True, "stress_score": 8,
            "alcohol_drinks": 6, "energy_drinks": 2, "energy_drink_time": "late", "cigarettes": 5,
            "gambling_minutes": 60, "substance_use": True, "work_hours": 0, "work_finish": None,
            "argument_count": 2, "travel_hours": 3,
        },
    ]
    _patch_get(monkeypatch, checkin, rows)
    df = checkin.get_checkin_dataframe("user-1")

    quiet, busy = df.iloc[0], df.iloc[1]
    assert quiet["alcohol_flag"] == 0 and busy["alcohol_flag"] == 1
    assert busy["alcohol_drinks"] == 6
    assert quiet["energy_drink_late_flag"] == 0 and busy["energy_drink_late_flag"] == 1
    assert quiet["high_stress_flag"] == 0 and busy["high_stress_flag"] == 1
    assert quiet["work_late_flag"] == 1 and busy["work_late_flag"] == 0
    assert busy["gambling_flag"] == 1 and quiet["gambling_flag"] == 0
    assert busy["argument_flag"] == 1 and busy["travel_flag"] == 1
    # "Not answered" must stay missing, never become a zero.
    assert _is_nan(quiet["substance_flag"])
    assert busy["substance_flag"] == 1


def test_checkin_dataframe_handles_old_check_ins_without_new_columns(monkeypatch):
    rows = [{"date": "2026-09-01", "alcohol": True, "afternoon_caffeine": False, "stress_score": None}]
    _patch_get(monkeypatch, checkin, rows)
    df = checkin.get_checkin_dataframe("user-1")
    assert df.iloc[0]["alcohol_flag"] == 1
    assert df.iloc[0]["afternoon_caffeine"] == 0
    # An old "yes" has no drink count, so there is no count to analyse.
    assert "alcohol_drinks" not in df.columns or _is_nan(df.iloc[0]["alcohol_drinks"])


def test_checkin_dataframe_is_empty_when_nothing_logged(monkeypatch):
    _patch_get(monkeypatch, checkin, [])
    assert checkin.get_checkin_dataframe("user-1").empty


def test_checkin_request_ignores_unknown_choices():
    body = checkin.CheckInRequest(
        date="2026-10-02", alcohol_drinks=3, alcohol_time="midnight-ish", energy_drink_time="late",
        work_finish="whenever", travel_mode="car",
    )
    assert body.alcohol_time is None
    assert body.energy_drink_time == "late"
    assert body.work_finish is None
    assert body.travel_mode == "car"


def test_checkin_request_rejects_bad_dates_and_impossible_amounts():
    with pytest.raises(Exception):
        checkin.CheckInRequest(date="02/10/2026")
    with pytest.raises(Exception):
        checkin.CheckInRequest(date="2026-10-02", alcohol_drinks=500)


def test_workout_volume_uses_what_was_actually_done():
    exercises = [
        {
            "sets": [
                {"done": True, "reps": 8, "weight_kg": 100, "actual_reps": 6, "actual_weight_kg": 100},  # 600
                {"done": True, "reps": 5, "weight_kg": 50},  # older set: planned numbers, 250
                {"done": False, "reps": 10, "weight_kg": 10},  # not done: not counted
            ]
        }
    ]
    assert workouts._volume_kg(exercises) == 850


def test_workout_leg_day_needs_a_done_lower_body_set():
    legs_done = [{"group": "Quads", "sets": [{"done": True}]}]
    legs_not_done = [{"group": "Quads", "sets": [{"done": False}]}]
    upper = [{"group": "Chest", "sets": [{"done": True}]}]
    assert workouts._trained_lower_body(legs_done)
    assert not workouts._trained_lower_body(legs_not_done)
    assert not workouts._trained_lower_body(upper)


def test_workout_dataframe_summarises_completed_days(monkeypatch):
    rows = [
        {
            "planned_date": "2026-10-01", "status": "completed", "include_in_engine": True,
            "exercises": [{"group": "Quads", "sets": [{"done": True, "reps": 5, "weight_kg": 100}]}],
        },
        {"planned_date": "2026-10-02", "status": "planned", "include_in_engine": True, "exercises": []},
        {"planned_date": "2026-10-03", "status": "completed", "include_in_engine": False, "exercises": []},
    ]
    _patch_get(monkeypatch, workouts, rows)
    df = workouts.get_workout_dataframe("user-1")
    assert pd.Timestamp("2026-10-03") not in df.index  # opted out of the engine
    done, planned = df.loc[pd.Timestamp("2026-10-01")], df.loc[pd.Timestamp("2026-10-02")]
    assert done["workout_completed_flag"] == 1
    assert done["workout_volume_kg"] == 500
    assert done["leg_day_flag"] == 1
    assert planned["workout_completed_flag"] == 0

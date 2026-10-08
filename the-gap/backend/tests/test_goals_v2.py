import asyncio
from datetime import date, timedelta

import pytest

from utils import goals
from utils.goal_catalog import GOAL_METRICS, public_catalog
from utils.goals import bmi, evaluate_goal, lowest_weight_for_bmi, validate_new_goal, window_average

TODAY = date(2026, 10, 8)


def _days(values, end=TODAY):
    """One reading per day ending on `end`, oldest first."""
    n = len(values)
    return [(end - timedelta(days=n - 1 - i), v) for i, v in enumerate(values)]


# ── what can be a goal ───────────────────────────────────────────────────────

def test_no_calorie_or_nutrient_goals_exist():
    assert not {"dietary_energy", "protein_g", "carbs_g", "fat_g"} & set(GOAL_METRICS)


def test_every_category_has_goals_and_every_goal_has_sane_limits():
    categories = {c["key"]: c["metrics"] for c in public_catalog(has_height=True)}
    assert set(categories) == {"sleep", "body", "fitness", "recovery", "stress_mood", "habits"}
    assert all(categories[k] for k in categories)
    for m in GOAL_METRICS.values():
        assert m.minimum < m.maximum and m.step > 0 and m.min_points >= 2
        assert m.default_direction in m.directions or m.default_direction == "maintain"


def test_alcohol_goals_can_only_go_down_or_hold():
    assert GOAL_METRICS["alcohol_drinks"].directions == ("decrease", "maintain")


def test_weight_needs_a_height_and_never_a_date():
    weight = GOAL_METRICS["weight_kg"]
    assert weight.needs_height and not weight.allow_target_date
    lookup = {m["metric_key"]: m for c in public_catalog(has_height=False) for m in c["metrics"]}
    assert lookup["weight_kg"]["available"] is False and lookup["steps"]["available"] is True


# ── the 7-day average ────────────────────────────────────────────────────────

def test_the_average_uses_only_the_last_seven_days():
    steps = GOAL_METRICS["steps"]
    points = _days([1000] * 10 + [9000] * 7)
    value, n = window_average(points, TODAY, steps)
    assert value == 9000 and n == 7


def test_too_few_days_gives_no_average():
    steps = GOAL_METRICS["steps"]
    value, n = window_average(_days([9000] * 4), TODAY, steps)
    assert value is None and n == 4


def test_sleep_is_shown_in_hours_and_weekly_habits_per_week():
    sleep, workouts = GOAL_METRICS["sleep_total_min"], GOAL_METRICS["workout_completed_flag"]
    assert window_average(_days([420] * 7), TODAY, sleep)[0] == 7.0
    assert window_average(_days([1, 0, 1, 0, 1, 0]), TODAY, workouts)[0] == pytest.approx(3.5)  # 6 days logged, half with a workout


def test_a_single_great_day_does_not_reach_a_goal():
    goal = {"metric_col": "steps", "direction": "increase", "baseline_value": 6000, "target_value": 10000, "status": "active"}
    spike = _days([6000] * 6 + [25000])
    assert evaluate_goal(goal, spike, TODAY)["state"] == "building"  # average is ~8,700


# ── progress and reaching a goal ─────────────────────────────────────────────

def test_progress_runs_from_baseline_to_target():
    goal = {"metric_col": "steps", "direction": "increase", "baseline_value": 6000, "target_value": 10000, "status": "active"}
    p = evaluate_goal(goal, _days([8000] * 7), TODAY)
    assert p["state"] == "building" and p["fraction"] == pytest.approx(0.5)


def test_reaching_the_target_with_the_average_counts():
    goal = {"metric_col": "steps", "direction": "increase", "baseline_value": 6000, "target_value": 10000, "status": "active"}
    p = evaluate_goal(goal, _days([10100] * 7), TODAY)
    assert p["state"] == "achieved" and p["fraction"] == 1.0


def test_decrease_goals_work_downwards():
    goal = {"metric_col": "resting_hr", "direction": "decrease", "baseline_value": 62, "target_value": 55, "status": "active"}
    assert evaluate_goal(goal, _days([58] * 7), TODAY)["fraction"] == pytest.approx(4 / 7)
    assert evaluate_goal(goal, _days([54] * 7), TODAY)["state"] == "achieved"


def test_progress_never_goes_below_zero_or_above_one():
    goal = {"metric_col": "steps", "direction": "increase", "baseline_value": 6000, "target_value": 10000, "status": "active"}
    assert evaluate_goal(goal, _days([2000] * 7), TODAY)["fraction"] == 0.0


def test_maintain_goals_hold_or_drift_and_are_never_achieved():
    goal = {"metric_col": "weight_kg", "direction": "maintain", "baseline_value": 72, "target_value": 72, "status": "active"}
    assert evaluate_goal(goal, _days([72.4] * 7), TODAY)["state"] == "holding"
    assert evaluate_goal(goal, _days([76] * 7), TODAY)["state"] == "drifting"


def test_not_enough_data_is_reported_plainly():
    goal = {"metric_col": "steps", "direction": "increase", "baseline_value": 6000, "target_value": 10000, "status": "active"}
    p = evaluate_goal(goal, _days([9000] * 3), TODAY)
    assert p["state"] == "not_enough_data" and p["current"] is None and p["points"] == 3 and p["needed"] == 5


# ── safety rules for new goals ───────────────────────────────────────────────

def _check(metric, direction, target, baseline=None, target_date=None, height=None):
    return validate_new_goal(GOAL_METRICS[metric], direction, target, baseline, target_date, height, TODAY)


def test_a_sensible_goal_is_accepted():
    assert _check("steps", "increase", 9000, baseline=7000) is None


def test_targets_outside_the_limits_are_refused():
    assert _check("steps", "increase", 80000, baseline=7000)["code"] == "target_range"
    assert _check("sleep_total_min", "increase", 14, baseline=7)["code"] == "target_range"


def test_the_target_must_be_on_the_right_side_of_where_you_are():
    assert _check("steps", "increase", 6000, baseline=7000)["code"] == "target_side"
    assert _check("resting_hr", "decrease", 60, baseline=55)["code"] == "target_side"


def test_a_goal_needs_enough_recent_data_to_start_from():
    assert _check("steps", "increase", 9000, baseline=None)["code"] == "no_baseline"
    assert _check("steps", "maintain", 8000, baseline=None) is None


def test_directions_a_metric_does_not_allow_are_refused():
    assert _check("alcohol_drinks", "increase", 10, baseline=5)["code"] == "direction"


def test_weight_goals_need_a_height():
    assert _check("weight_kg", "decrease", 68, baseline=72)["code"] == "height_needed"


def test_a_weight_target_that_would_be_underweight_is_refused():
    floor = lowest_weight_for_bmi(170)
    assert 53 < floor < 54.5                               # BMI 18.5 at 170 cm is about 53.5 kg
    refused = _check("weight_kg", "decrease", 52, baseline=70, height=170)
    assert refused["code"] == "bmi_floor" and "healthy range" in refused["message"]
    assert _check("weight_kg", "decrease", 60, baseline=70, height=170) is None
    assert bmi(floor, 170) == pytest.approx(18.5)


def test_someone_already_under_the_floor_cannot_set_a_loss_goal_or_a_maintain_target_below_it():
    assert _check("weight_kg", "decrease", 50, baseline=52, height=170)["code"] == "bmi_floor"
    assert _check("weight_kg", "maintain", 50, baseline=50, height=170)["code"] == "bmi_floor"


def test_weight_goals_have_no_dates_but_other_goals_can():
    assert _check("weight_kg", "decrease", 65, baseline=70, target_date=TODAY + timedelta(days=60), height=170)["code"] == "no_date"
    assert _check("steps", "increase", 9000, baseline=7000, target_date=TODAY + timedelta(days=60)) is None
    assert _check("steps", "increase", 9000, baseline=7000, target_date=TODAY)["code"] == "date_past"


# ── marking a goal achieved ──────────────────────────────────────────────────

class _Resp:
    def __init__(self, rows):
        self._rows = rows

    def raise_for_status(self):
        pass

    def json(self):
        return self._rows


def _fake_db(monkeypatch, patch_rows):
    calls = {"patch": [], "feed": []}

    class _Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def patch(self, url, headers=None, params=None, json=None):
            calls["patch"].append((params, json))
            return _Resp(patch_rows)

    async def feed(user_id, **kwargs):
        calls["feed"].append(kwargs)

    monkeypatch.setattr(goals.httpx, "AsyncClient", lambda **kw: _Client())
    import utils.feed as feed_module

    monkeypatch.setattr(feed_module, "create_feed_item", feed)
    return calls


def _wire_goals(monkeypatch, goal_list, progress):
    async def list_goals(user_id, status=None):
        return goal_list

    async def user_today(user_id):
        return TODAY

    async def goal_progress(user_id, goal, today=None):
        return progress

    monkeypatch.setattr(goals, "list_goals", list_goals)
    monkeypatch.setattr(goals, "user_today", user_today)
    monkeypatch.setattr(goals, "goal_progress", goal_progress)


GOAL = {"id": "g1", "metric_col": "steps", "metric_label": "Daily steps", "direction": "increase", "baseline_value": 6000, "target_value": 10000, "status": "active"}


def test_a_reached_goal_is_marked_and_celebrated_once(monkeypatch):
    _wire_goals(monkeypatch, [GOAL], {"state": "achieved", "current": 10150.0})
    calls = _fake_db(monkeypatch, patch_rows=[{"id": "g1"}])
    done = asyncio.run(goals.check_goal_achievements("u1"))
    assert [g["id"] for g in done] == ["g1"]
    assert calls["patch"][0][0]["status"] == "eq.active" and calls["patch"][0][1]["status"] == "achieved"
    assert len(calls["feed"]) == 1 and calls["feed"][0]["kind"] == "goal_achieved" and calls["feed"][0]["goal_id"] == "g1"
    assert "10,150" in calls["feed"][0]["body"] and "6,000" in calls["feed"][0]["body"]


def test_a_goal_already_marked_by_another_check_is_not_celebrated_twice(monkeypatch):
    _wire_goals(monkeypatch, [GOAL], {"state": "achieved", "current": 10150.0})
    calls = _fake_db(monkeypatch, patch_rows=[])  # the database found no still-active goal to move
    assert asyncio.run(goals.check_goal_achievements("u1")) == []
    assert calls["feed"] == []


def test_goals_still_building_are_left_alone(monkeypatch):
    _wire_goals(monkeypatch, [GOAL], {"state": "building", "current": 8000.0})
    calls = _fake_db(monkeypatch, patch_rows=[{"id": "g1"}])
    assert asyncio.run(goals.check_goal_achievements("u1")) == []
    assert calls["patch"] == [] and calls["feed"] == []


def test_maintain_goals_are_never_checked_for_achievement(monkeypatch):
    _wire_goals(monkeypatch, [{**GOAL, "direction": "maintain"}], {"state": "achieved", "current": 10150.0})
    calls = _fake_db(monkeypatch, patch_rows=[{"id": "g1"}])
    assert asyncio.run(goals.check_goal_achievements("u1")) == []
    assert calls["patch"] == []

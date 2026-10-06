from routers.health_plan import (
    HEADLINES,
    WORKOUT_BUTTON_ACTIONS,
    _decide_training,
    _fallback_text,
    _nutrition_flags,
    _round_steps,
)


def test_already_trained_today_is_done():
    assert _decide_training("train", "high", {}, True, False) == "done"


def test_rest_day_with_strong_recovery_offers_a_session():
    signals = {"hrv_pct": 8, "sleep_pct": 5}
    assert _decide_training("rest", "high", signals, False, False) == "rest_but_ready"


def test_rest_day_stays_rest_if_you_trained_yesterday():
    signals = {"hrv_pct": 8, "sleep_pct": 5}
    assert _decide_training("rest", "high", signals, False, True) == "rest"


def test_rest_day_stays_rest_if_hrv_or_sleep_is_below_average():
    assert _decide_training("rest", "high", {"hrv_pct": -5, "sleep_pct": 3}, False, False) == "rest"
    assert _decide_training("rest", "high", {"hrv_pct": 5, "sleep_pct": -3}, False, False) == "rest"


def test_rest_day_with_only_ok_recovery_stays_rest():
    assert _decide_training("rest", "moderate", {"hrv_pct": 5, "sleep_pct": 5}, False, False) == "rest"


def test_training_day_follows_recovery():
    assert _decide_training("train", "low", {}, False, False) == "train_easy"
    assert _decide_training("train", "moderate", {}, False, False) == "train_controlled"
    assert _decide_training("train", "high", {}, False, False) == "train"
    assert _decide_training("train", "unknown", {}, False, False) == "train_unknown"


def test_no_schedule_uses_recovery_alone():
    assert _decide_training(None, "high", {}, False, False) == "train_suggested"
    assert _decide_training(None, "low", {}, False, False) == "rest_suggested"
    assert _decide_training(None, "moderate", {}, False, False) == "no_plan"


def test_every_decision_has_a_headline_and_fallback_text():
    for action in HEADLINES:
        assert HEADLINES[action]
        assert _fallback_text(action, None, [])


def test_workout_button_only_on_training_style_actions():
    assert "rest" not in WORKOUT_BUTTON_ACTIONS
    assert "done" not in WORKOUT_BUTTON_ACTIONS
    assert "rest_but_ready" in WORKOUT_BUTTON_ACTIONS


def test_rest_day_text_mentions_step_range():
    assert "4,500" in _fallback_text("rest", [4500, 6000], [])


def test_steps_round_to_nearest_500():
    assert _round_steps(4620) == 4500
    assert _round_steps(4800) == 5000


def _nutrition(calories=800.0, protein=20.0, water=200.0, goals=None):
    return {"calories": calories, "protein_g": protein, "water_ml": water, "goals": goals or {"protein_goal_g": 150, "water_goal_ml": 3000, "calorie_goal": 2400}}


def test_protein_and_water_nudges_appear_when_behind_later_in_the_day():
    flags = _nutrition_flags(_nutrition(), hour=15)
    assert "protein_behind" in flags
    assert "water_behind" in flags


def test_no_nudges_early_in_the_morning():
    assert _nutrition_flags(_nutrition(calories=300), hour=9) == []


def test_nothing_logged_after_lunch_says_so():
    assert _nutrition_flags(_nutrition(calories=0, protein=0, water=0), hour=14) == ["nothing_logged"]


def test_on_track_gets_no_nudge():
    on_track = _nutrition(calories=1500, protein=110, water=2200)
    assert _nutrition_flags(on_track, hour=15) == []

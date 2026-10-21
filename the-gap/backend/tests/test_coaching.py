import asyncio
import json

from routers import coach, suggestions
from utils import coaching as c


def test_protein_for_someone_training_for_muscle_is_a_range_with_a_reason():
    out = c.protein(80, 180, "gain", "muscle")
    assert (out["low"], out["high"]) == (130, 175) and out["suggested"] == 150
    assert "1.6 and 2.2 g" in out["why"] and "130 to 175 g" in out["why"]


def test_protein_is_lower_for_general_health_and_for_endurance():
    general = c.protein(70, 175, "maintain", "general")
    assert (general["low"], general["high"]) == (55, 85)
    endurance = c.protein(70, 175, "maintain", "endurance")
    assert endurance["low"] < c.protein(70, 175, "gain", "muscle")["low"] and endurance["low"] > general["low"]


def test_the_goal_to_gain_muscle_wins_even_if_the_training_goal_is_general():
    assert c.protein(80, 180, "gain", "general")["low"] == c.protein(80, 180, "gain", "muscle")["low"]


def test_a_high_bmi_is_worked_from_a_healthy_weight_for_the_height():
    out = c.protein(130, 170, "gain", "muscle")  # BMI 45
    assert out["high"] <= 195 and "healthy-weight figure for your height" in out["why"]


def test_a_low_bmi_gets_no_number_and_is_pointed_to_a_dietitian():
    out = c.protein(50, 175, "gain", "muscle")  # BMI 16
    assert "low" not in out and "dietitian" in out["unavailable"]


def test_without_a_weight_it_asks_for_one_instead_of_guessing():
    assert c.protein(None, None, "gain", "muscle")["needs"] == "weight"
    assert c.water(None)["needs"] == "weight"


def test_water_is_a_range_by_bodyweight_and_stays_within_sensible_bounds():
    out = c.water(80)
    assert out["low"] == 2500 and out["high"] == 3250 and "30 to 40 ml" in out["why"] and "fluid limit" in out["why"]
    tiny = c.water(40)
    assert tiny["low"] >= 1500 and tiny["high"] <= 4500


def test_steps_sleep_and_workouts_suggest_a_next_step_from_where_the_person_is():
    assert c.steps(4200)["next_step"]["value"] == 5000
    assert "next_step" not in c.steps(8200)
    assert c.sleep(6.2)["next_step"]["value"] == 6.75
    assert "next_step" not in c.sleep(7.6)
    assert c.workout_days("muscle", 1.4)["next_step"]["value"] == 2
    assert (c.workout_days("endurance", None)["low"], c.workout_days("endurance", None)["high"]) == (4, 6)


def test_nothing_is_suggested_when_switched_off_or_under_18():
    base = dict(weight_kg=80, height_cm=180, diet_goal="gain", training_goal="muscle")
    assert c.build(age=30, coach_off=True, **base) == {"off": True, "suggestions": [], "disclaimer": c.DISCLAIMER}
    assert c.build(age=17, coach_off=False, **base)["suggestions"] == []
    assert len(c.build(age=30, coach_off=False, **base)["suggestions"]) == 5


def test_it_never_talks_about_calories_or_losing_weight():
    out = c.build(weight_kg=80, height_cm=180, age=30, diet_goal="lose", training_goal="fat_loss", coach_off=False, current_steps=3000, current_sleep_hours=6.0, current_workouts=1.0)
    text = json.dumps(out).lower()
    for word in ("calorie", "kcal", "lose weight", "weight loss", "weight-loss", "slim"):
        assert word not in text, word
    assert "isn't medical or dietitian advice" in out["disclaimer"]


def test_the_route_puts_it_together_from_the_persons_own_data(monkeypatch):
    async def profile(client, user_id):
        return {"diet_goal": "gain", "training_goal": "muscle", "coach_off": False}

    async def about(user_id):
        return {"weight_kg": 90, "height_cm": 182, "age": 31}

    async def latest(user_id):
        return 80.0  # a logged weight beats the one typed into the profile

    async def today(user_id):
        from datetime import date

        return date(2026, 10, 21)

    async def average(user_id, key, today=None):
        return {"steps": 5200.0, "sleep_total_min": 6.4, "workout_completed_flag": 1.5}[key], 7

    monkeypatch.setattr(coach, "_load_profile", profile)
    monkeypatch.setattr(coach, "get_user_profile", about)
    monkeypatch.setattr(coach, "_latest_weight", latest)
    monkeypatch.setattr(coach, "user_today", today)
    monkeypatch.setattr(coach, "current_average", average)
    out = json.loads(asyncio.run(coach.suggestions(user_id="u1")).body)
    by_key = {s["key"]: s for s in out["suggestions"]}
    assert by_key["protein_g"]["low"] == 130 and by_key["steps"]["next_step"]["value"] == 6000 and by_key["sleep_total_min"]["next_step"]["value"] == 7.0


def test_saving_the_profile_survives_the_new_columns_not_existing_yet(monkeypatch):
    posted = []

    class _Resp:
        def __init__(self, status, text=""):
            self.status_code, self.text = status, text

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError("bad")

    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, params=None, json=None):
            posted.append(dict(json))
            if "coach_off" in json or "plans_for" in json:
                return _Resp(400, 'column "coach_off" of relation does not exist')
            return _Resp(201)

    monkeypatch.setattr(suggestions.httpx, "AsyncClient", lambda **kw: _Client())
    body = suggestions.ProfileBody(diet_goal="gain", coach_off=True, plans_for="women")
    out = json.loads(asyncio.run(suggestions.put_profile(body, user_id="u1")).body)
    assert out["profile"]["diet_goal"] == "gain"
    assert "coach_off" in posted[0] and "coach_off" not in posted[-1]  # retried without the missing columns

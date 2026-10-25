import math

import pytest

from causal.hypotheses import HYPOTHESES
from routers import nutrition
from utils import saved_logging, sugar


@pytest.fixture
def tracking(monkeypatch):
    monkeypatch.setenv("SUGAR_TRACKING", "true")


@pytest.fixture
def not_tracking(monkeypatch):
    monkeypatch.delenv("SUGAR_TRACKING", raising=False)


# ── unknown is not zero ──────────────────────────────────────────────────────

def test_a_missing_or_empty_figure_is_unknown_not_zero():
    assert sugar.known(None) is None
    assert sugar.known(float("nan")) is None
    assert sugar.known("abc") is None
    assert sugar.known(0) == 0.0
    assert sugar.known("12.5") == 12.5


def test_a_day_has_a_sugar_total_only_when_every_food_has_a_figure():
    assert sugar.day_total([10, 5.5, 20]) == 35.5
    assert sugar.day_total([10, None, 20]) is None
    assert sugar.day_total([10, float("nan")]) is None
    assert sugar.day_total([]) is None


# ── writing is switched on separately ───────────────────────────────────────

def test_nothing_is_added_to_a_saved_row_until_tracking_is_switched_on(not_tracking):
    assert "sugar_g" not in sugar.add_scaled({}, {"sugar_g": 10}, 2)


def test_sugar_is_scaled_by_the_servings_once_tracking_is_on(tracking):
    assert sugar.add_scaled({}, {"sugar_g": 10.5}, 2) == {"sugar_g": 21.0}
    assert sugar.add_scaled({}, {}, 2) == {}  # a food with no figure adds nothing


def test_a_saved_food_logs_with_its_sugar_when_tracking_is_on(tracking):
    food = {"name": "Yoghurt", "calories": 100, "protein_g": 5, "carbs_g": 12, "fat_g": 3, "sugar_g": 9}
    row = saved_logging.food_log_row("u1", "2026-10-26", "snack", food, 2, 10.0, "saved")
    assert row["sugar_g"] == 18.0 and row["calories"] == 200.0


def test_a_saved_food_logs_as_before_when_tracking_is_off(not_tracking):
    food = {"name": "Yoghurt", "calories": 100, "protein_g": 5, "carbs_g": 12, "fat_g": 3, "sugar_g": 9}
    row = saved_logging.food_log_row("u1", "2026-10-26", "snack", food, 2, 10.0, "saved")
    assert "sugar_g" not in row


def test_a_saved_food_shows_its_sugar_only_when_it_has_one():
    with_sugar = saved_logging.public_food({"id": "a", "name": "A", "calories": 1, "sugar_g": 4})
    without = saved_logging.public_food({"id": "b", "name": "B", "calories": 1})
    assert with_sugar["per_serving"]["sugar_g"] == 4.0
    assert "sugar_g" not in without["per_serving"]


# ── reading sugar from the food databases ────────────────────────────────────

def test_usda_sugar_comes_through_per_serving():
    food = {
        "description": "Test cereal",
        "fdcId": 1,
        "servingSize": 50,
        "servingSizeUnit": "g",
        "foodNutrients": [
            {"nutrientNumber": "208", "unitName": "KCAL", "value": 400},
            {"nutrientNumber": "203", "value": 8},
            {"nutrientNumber": "205", "value": 80},
            {"nutrientNumber": "204", "value": 5},
            {"nutrientNumber": "269", "value": 30},
        ],
    }
    item = nutrition._usda_to_item(food)
    assert item["per_serving"]["sugar_g"] == 15.0
    assert item["per_serving"]["calories"] == 200.0


def test_a_food_without_a_sugar_figure_has_none_rather_than_zero():
    food = {
        "description": "Plain rice",
        "fdcId": 2,
        "servingSize": 100,
        "servingSizeUnit": "g",
        "foodNutrients": [{"nutrientNumber": "208", "unitName": "KCAL", "value": 130}, {"nutrientNumber": "203", "value": 2.7}, {"nutrientNumber": "205", "value": 28}, {"nutrientNumber": "204", "value": 0.3}],
    }
    assert "sugar_g" not in nutrition._usda_to_item(food)["per_serving"]


def test_open_food_facts_sugar_is_read_when_present():
    per100 = nutrition._off_per100({"energy-kcal_100g": 400, "proteins_100g": 5, "carbohydrates_100g": 70, "fat_100g": 10, "sugars_100g": 22})
    assert per100["sugar_g"] == 22.0
    assert "sugar_g" not in nutrition._off_per100({"energy-kcal_100g": 400, "proteins_100g": 5, "carbohydrates_100g": 70, "fat_100g": 10})


# ── editing an entry keeps sugar in step ─────────────────────────────────────

def test_changing_the_servings_rescales_sugar_too():
    row = {"servings": 1, "calories": 100, "protein_g": 1, "carbs_g": 20, "fat_g": 1, "sugar_g": 12}
    assert nutrition.rescaled_totals(row, 2)["sugar_g"] == 24.0


def test_an_entry_without_sugar_is_rescaled_as_before():
    row = {"servings": 1, "calories": 100, "protein_g": 1, "carbs_g": 20, "fat_g": 1}
    assert "sugar_g" not in nutrition.rescaled_totals(row, 2)


# ── the engine ───────────────────────────────────────────────────────────────

def test_sugar_patterns_exist_and_scale_to_25_grams():
    found = {h.id: h for h in HYPOTHESES if h.treatment_col == "sugar_g"}
    assert set(found) == {"sugar_hrv", "sugar_sleep"}
    assert all(h.treatment_scale == 25.0 and h.min_rows >= 30 for h in found.values())
    assert not any(math.isnan(h.treatment_scale) for h in found.values())

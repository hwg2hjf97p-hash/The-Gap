import asyncio

import httpx
import pytest
from fastapi import HTTPException

from routers import saved_foods
from routers.nutrition import PerServing
from utils import saved_logging


class _Resp:
    def __init__(self, rows=None, status=200):
        self._rows, self.status_code = rows if rows is not None else [], status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=httpx.Request("POST", "http://x"), response=httpx.Response(self.status_code))

    def json(self):
        return self._rows


def install(monkeypatch, *, foods=(), meals=(), log_rows=(), duplicate=False):
    calls = {"posts": [], "patches": [], "deletes": []}

    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None, params=None):
            table = url.rsplit("/", 1)[-1]
            return _Resp({"saved_foods": list(foods), "saved_meals": list(meals), "food_log": list(log_rows)}.get(table, []))

        async def post(self, url, headers=None, params=None, json=None):
            table = url.rsplit("/", 1)[-1]
            if duplicate and table.startswith("saved_"):
                return _Resp(status=409)
            calls["posts"].append((table, json))
            rows = json if isinstance(json, list) else [{**json, "id": "new-id"}]
            return _Resp(rows, status=201)

        async def patch(self, url, headers=None, params=None, json=None):
            calls["patches"].append((url.rsplit("/", 1)[-1], params, json))
            return _Resp()

        async def delete(self, url, headers=None, params=None):
            calls["deletes"].append((url.rsplit("/", 1)[-1], params))
            return _Resp()

    monkeypatch.setattr(saved_foods.httpx, "AsyncClient", lambda **kw: _Client())
    return calls


FOOD_ROW = {"id": "f1", "name": "Protein drink", "aliases": [], "brand": "Brand", "serving_label": "1 bottle", "serving_grams": 330, "calories": 150, "protein_g": 25, "carbs_g": 5, "fat_g": 2, "default_servings": 1, "use_count": 2}
MEAL_ROW = {"id": "m1", "name": "Brekky", "aliases": [], "meal": "breakfast", "use_count": 0, "items": [
    {"food_name": "Egg", "servings": 2, "serving_label": "1 egg", "per_serving": {"calories": 70, "protein_g": 6, "carbs_g": 0.5, "fat_g": 5}},
    {"food_name": "Toast", "servings": 1, "serving_label": "1 slice", "per_serving": {"calories": 80, "protein_g": 3, "carbs_g": 15, "fat_g": 1}},
]}


# ── what a saved item looks like to the app ──────────────────────────────────

def test_a_saved_food_looks_like_any_other_food_to_the_app():
    food = saved_logging.public_food(FOOD_ROW)
    assert food["source"] == "saved" and food["source_id"] == "f1" and food["name"] == "Protein drink"
    assert food["per_serving"] == {"calories": 150.0, "protein_g": 25.0, "carbs_g": 5.0, "fat_g": 2.0}
    assert food["serving_label"] == "1 bottle" and food["default_servings"] == 1.0


def test_a_saved_meal_shows_its_totals():
    meal = saved_logging.public_meal(MEAL_ROW)
    assert meal["totals"]["calories"] == 220.0 and meal["totals"]["protein_g"] == 15.0
    assert [i["food_name"] for i in meal["items"]] == ["Egg", "Toast"]


def test_logging_a_saved_food_works_out_the_totals_from_what_was_saved():
    [row] = saved_logging.saved_food_rows("u1", FOOD_ROW, 2.0, "2026-10-09", 8.0, None)
    assert row["calories"] == 300 and row["protein_g"] == 50 and row["servings"] == 2 and row["meal"] == "breakfast"
    assert row["source"] == "saved" and row["brand"] == "Brand"


def test_an_item_that_would_be_absurdly_large_is_caught():
    rows = saved_logging.saved_food_rows("u1", {**FOOD_ROW, "calories": 4000}, 5.0, "2026-10-09", 8.0, None)
    assert saved_logging.too_big(rows)


# ── saving ───────────────────────────────────────────────────────────────────

def test_saving_a_food_stores_exactly_what_was_logged(monkeypatch):
    calls = install(monkeypatch)
    body = saved_foods.SavedFoodBody(name=" Protein drink ", aliases=["shake", "Shake", ""], per_serving=PerServing(calories=150, protein_g=25, carbs_g=5, fat_g=2), serving_label="1 bottle", default_servings=1)
    response = asyncio.run(saved_foods.save_food(body, user_id="u1"))
    assert response.status_code == 200
    table, row = calls["posts"][0]
    assert table == "saved_foods" and row["name"] == "Protein drink" and row["aliases"] == ["shake"] and row["calories"] == 150 and row["user_id"] == "u1"


def test_a_second_saved_food_with_the_same_name_is_refused_politely(monkeypatch):
    install(monkeypatch, duplicate=True)
    body = saved_foods.SavedFoodBody(name="Protein drink", per_serving=PerServing(calories=150))
    with pytest.raises(HTTPException) as err:
        asyncio.run(saved_foods.save_food(body, user_id="u1"))
    assert err.value.status_code == 409 and "already have a saved food" in err.value.detail


def test_a_meal_is_saved_from_what_was_logged_with_per_serving_numbers(monkeypatch):
    log_rows = [
        {"id": "e1", "meal": "breakfast", "food_name": "Egg", "brand": None, "servings": 2, "serving_label": "1 egg", "serving_grams": None, "calories": 140, "protein_g": 12, "carbs_g": 1, "fat_g": 10},
        {"id": "e2", "meal": "breakfast", "food_name": "Toast", "brand": None, "servings": 1, "serving_label": "1 slice", "serving_grams": None, "calories": 80, "protein_g": 3, "carbs_g": 15, "fat_g": 1},
    ]
    calls = install(monkeypatch, log_rows=log_rows)
    asyncio.run(saved_foods.save_meal_from_log(saved_foods.MealFromLogBody(name="Brekky", entry_ids=["e1", "e2"]), user_id="u1"))
    table, row = calls["posts"][0]
    assert table == "saved_meals" and row["meal"] == "breakfast"
    egg = row["items"][0]
    assert egg["servings"] == 2 and egg["per_serving"]["calories"] == 70      # the log keeps totals; the saved meal keeps one serving


def test_saving_a_meal_from_entries_that_are_not_yours_finds_nothing(monkeypatch):
    install(monkeypatch, log_rows=[])
    with pytest.raises(HTTPException) as err:
        asyncio.run(saved_foods.save_meal_from_log(saved_foods.MealFromLogBody(name="Brekky", entry_ids=["nope"]), user_id="u1"))
    assert err.value.status_code == 404


# ── logging a saved item from the app ────────────────────────────────────────

def test_one_tap_logs_a_saved_food_and_counts_the_use(monkeypatch):
    calls = install(monkeypatch, foods=[FOOD_ROW])
    body = saved_foods.LogSavedBody(kind="food", id="f1", local_date="2026-10-09", local_hour=8.5, meal="breakfast", servings=1)
    response = asyncio.run(saved_foods.log_saved(body, user_id="u1"))
    assert response.status_code == 200
    [(table, rows)] = calls["posts"]
    assert table == "food_log" and rows[0]["local_hour"] == 8.5 and rows[0]["meal"] == "breakfast"
    assert calls["patches"][0][0] == "saved_foods" and calls["patches"][0][2]["use_count"] == 3


def test_one_tap_logs_every_item_of_a_saved_meal(monkeypatch):
    calls = install(monkeypatch, meals=[MEAL_ROW])
    asyncio.run(saved_foods.log_saved(saved_foods.LogSavedBody(kind="meal", id="m1", local_date="2026-10-09", local_hour=7.5), user_id="u1"))
    [(_, rows)] = calls["posts"]
    assert [r["food_name"] for r in rows] == ["Egg", "Toast"] and rows[0]["calories"] == 140


def test_logging_something_that_is_not_saved_is_a_clear_error(monkeypatch):
    install(monkeypatch)
    with pytest.raises(HTTPException) as err:
        asyncio.run(saved_foods.log_saved(saved_foods.LogSavedBody(kind="food", id="gone", local_date="2026-10-09"), user_id="u1"))
    assert err.value.status_code == 404


def test_a_bad_date_is_refused(monkeypatch):
    install(monkeypatch, foods=[FOOD_ROW])
    with pytest.raises(HTTPException) as err:
        asyncio.run(saved_foods.log_saved(saved_foods.LogSavedBody(kind="food", id="f1", local_date="yesterday"), user_id="u1"))
    assert err.value.status_code == 400


def test_the_list_is_in_the_shape_the_app_reads(monkeypatch):
    install(monkeypatch, foods=[FOOD_ROW], meals=[MEAL_ROW])
    response = asyncio.run(saved_foods.list_saved(user_id="u1"))
    body = response.body.decode()
    assert '"foods"' in body and '"meals"' in body and "Protein drink" in body and "Brekky" in body


def test_renaming_and_deleting_only_touch_the_persons_own_items(monkeypatch):
    calls = install(monkeypatch)
    asyncio.run(saved_foods.rename_food("f1", saved_foods.RenameBody(name="Shake", aliases=["protein"]), user_id="u1"))
    asyncio.run(saved_foods.delete_meal("m1", user_id="u1"))
    assert calls["patches"][0][1] == {"id": "eq.f1", "user_id": "eq.u1"} and calls["patches"][0][2] == {"name": "Shake", "aliases": ["protein"]}
    assert calls["deletes"][0] == ("saved_meals", {"id": "eq.m1", "user_id": "eq.u1"})

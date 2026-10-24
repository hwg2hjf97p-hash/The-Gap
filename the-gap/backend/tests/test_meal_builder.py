import asyncio

import httpx
import pytest
from fastapi import HTTPException

from routers import saved_foods
from routers.nutrition import PerServing
from utils import meal_builder as mb
from utils import saved_logging


def pasta(amount=200, unit="g"):
    return {"name": "Pasta, dry", "brand": None, "serving_label": "100 g", "serving_grams": 100, "per_serving": {"calories": 350, "protein_g": 12, "carbs_g": 72, "fat_g": 1.5}, "amount": amount, "unit": unit}


def oil(amount=18):
    return {"name": "Olive oil", "brand": None, "serving_label": "100 g", "serving_grams": 100, "per_serving": {"calories": 884, "protein_g": 0, "carbs_g": 0, "fat_g": 100}, "amount": amount, "unit": "g"}


# ── serves ──────────────────────────────────────────────────────────────────
def test_each_ingredient_is_stored_as_its_share_of_one_serve():
    items = mb.build_items([pasta(200)], serves=4)
    assert items[0]["servings"] == 0.5          # 200 g is 2 x 100 g, shared across 4 serves
    assert items[0]["per_serving"]["calories"] == 350  # what 100 g is, unchanged


def test_one_serve_adds_up_to_the_whole_recipe_divided_by_the_serves():
    items = mb.build_items([pasta(400), oil(36)], serves=4)
    whole = 4 * 350 + 0.36 * 884 * 1  # 400 g pasta and 36 g oil, in kcal
    one = mb.per_serve_totals(items)["calories"]
    assert abs(one - whole / 4) < 0.5


def test_a_built_meal_logs_one_serve_once_and_two_serves_twice():
    items = mb.build_items([pasta(400), oil(36)], serves=4)
    meal = {"items": items, "meal": "dinner"}
    one = saved_logging.saved_meal_rows("u1", meal, 1.0, "2026-10-24", 18.5, None)
    two = saved_logging.saved_meal_rows("u1", meal, 2.0, "2026-10-24", 18.5, None)
    assert round(sum(r["calories"] for r in one)) == round(mb.per_serve_totals(items)["calories"])
    assert round(sum(r["calories"] for r in two)) == round(2 * mb.per_serve_totals(items)["calories"])


def test_servings_can_be_entered_in_the_foods_own_serving_size():
    banana = {"name": "Banana", "serving_label": "1 medium banana, 118 g", "serving_grams": 118, "per_serving": {"calories": 105}, "amount": 2, "unit": "serving"}
    assert mb.build_items([banana], serves=2)[0]["servings"] == 1.0


# ── things that can't be saved ──────────────────────────────────────────────
def test_grams_need_a_known_serving_weight():
    food = {**pasta(), "serving_grams": None}
    with pytest.raises(mb.BuildProblem):
        mb.build_items([food], serves=1)


def test_an_ingredient_needs_an_amount():
    with pytest.raises(mb.BuildProblem):
        mb.build_items([pasta(0)], serves=1)


def test_an_empty_meal_or_too_many_serves_is_refused():
    with pytest.raises(mb.BuildProblem):
        mb.build_items([], serves=1)
    with pytest.raises(mb.BuildProblem):
        mb.build_items([pasta()], serves=0.5)
    with pytest.raises(mb.BuildProblem):
        mb.build_items([pasta()], serves=41)


def test_a_mistyped_amount_is_caught_before_saving():
    items = mb.build_items([oil(5000)], serves=1)  # five kilos of oil in one serve
    with pytest.raises(mb.BuildProblem):
        mb.check_serve_size(items)


def test_the_recipe_keeps_the_ingredients_as_entered():
    recipe = mb.recipe_json("Spag bol", 4, 1200, [pasta(200), oil(18)])
    assert recipe["serves"] == 4 and recipe["cooked_weight_g"] == 1200
    assert [(i["name"], i["amount"], i["unit"]) for i in recipe["ingredients"]] == [("Pasta, dry", 200.0, "g"), ("Olive oil", 18.0, "g")]


# ── the endpoints ───────────────────────────────────────────────────────────
class _Resp:
    def __init__(self, rows=None, status=200, text=""):
        self._rows, self.status_code, self.text = rows if rows is not None else [], status, text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=httpx.Request("POST", "http://x"), response=httpx.Response(self.status_code))

    def json(self):
        return self._rows


def install(monkeypatch, *, no_recipe_column=False, duplicate=False, patch_rows=None):
    calls = {"posts": [], "patches": []}

    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, params=None, json=None):
            if duplicate:
                return _Resp(status=409)
            if no_recipe_column and "recipe" in json:
                return _Resp(status=400, text="PGRST204 Could not find the 'recipe' column of 'saved_meals'")
            calls["posts"].append(json)
            return _Resp([{**json, "id": "new-id"}], status=201)

        async def patch(self, url, headers=None, params=None, json=None):
            calls["patches"].append((params, json))
            return _Resp(patch_rows if patch_rows is not None else [{**json, "id": "m1"}])

    monkeypatch.setattr(saved_foods.httpx, "AsyncClient", lambda **kw: _Client())
    return calls


def body(**changes):
    base = dict(
        name=" Spag bol ",
        serves=4,
        ingredients=[
            saved_foods.IngredientBody(name="Pasta, dry", serving_label="100 g", serving_grams=100, per_serving=PerServing(calories=350, protein_g=12, carbs_g=72, fat_g=1.5), amount=400, unit="g"),
            saved_foods.IngredientBody(name="Olive oil", serving_label="100 g", serving_grams=100, per_serving=PerServing(calories=884, fat_g=100), amount=36, unit="g"),
        ],
    )
    base.update(changes)
    return saved_foods.BuildMealBody(**base)


def test_saving_a_built_meal_stores_its_serve_shares_and_its_recipe(monkeypatch):
    calls = install(monkeypatch)
    response = asyncio.run(saved_foods.build_meal(body(), user_id="u1"))
    assert response.status_code == 200
    [posted] = calls["posts"]
    assert posted["user_id"] == "u1" and posted["name"] == "Spag bol"
    assert [round(i["servings"], 3) for i in posted["items"]] == [1.0, 0.09]
    assert posted["recipe"]["serves"] == 4


def test_it_still_saves_when_the_editable_copy_has_nowhere_to_go_yet(monkeypatch):
    calls = install(monkeypatch, no_recipe_column=True)
    response = asyncio.run(saved_foods.build_meal(body(), user_id="u1"))
    assert response.status_code == 200
    assert "recipe" not in calls["posts"][0] and calls["posts"][0]["items"]


def test_a_name_already_used_says_so(monkeypatch):
    install(monkeypatch, duplicate=True)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(saved_foods.build_meal(body(), user_id="u1"))
    assert caught.value.status_code == 409 and "Spag bol" in caught.value.detail


def test_editing_only_touches_the_persons_own_meal(monkeypatch):
    calls = install(monkeypatch)
    asyncio.run(saved_foods.update_built_meal("m1", body(), user_id="u1"))
    params, sent = calls["patches"][0]
    assert params == {"id": "eq.m1", "user_id": "eq.u1"} and sent["items"]


def test_editing_a_meal_that_isnt_theirs_is_not_found(monkeypatch):
    install(monkeypatch, patch_rows=[])
    with pytest.raises(HTTPException) as caught:
        asyncio.run(saved_foods.update_built_meal("someone-elses", body(), user_id="u1"))
    assert caught.value.status_code == 404


def test_an_absurd_serve_is_a_400(monkeypatch):
    install(monkeypatch)
    huge = saved_foods.IngredientBody(name="Oil", serving_grams=100, per_serving=PerServing(calories=884, fat_g=100), amount=5000, unit="g")
    with pytest.raises(HTTPException) as caught:
        asyncio.run(saved_foods.build_meal(body(serves=1, ingredients=[huge]), user_id="u1"))
    assert caught.value.status_code == 400

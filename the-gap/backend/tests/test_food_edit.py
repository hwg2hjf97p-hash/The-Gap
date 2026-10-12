import asyncio

import pytest
from fastapi import HTTPException

from routers import nutrition

ROW = {"id": "e1", "user_id": "u1", "local_date": "2026-10-09", "meal": "breakfast", "food_name": "Oats", "servings": 2.0,
       "calories": 300.0, "protein_g": 10.0, "carbs_g": 54.0, "fat_g": 6.0, "local_hour": 8.0}


class _Resp:
    def __init__(self, rows=None):
        self._rows, self.status_code = rows if rows is not None else [], 200

    def raise_for_status(self):
        pass

    def json(self):
        return self._rows


def install(monkeypatch, stored=(ROW,)):
    seen = {"patch": None, "params": None}

    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None, params=None):
            return _Resp([dict(r) for r in stored if r["user_id"] == params["user_id"].removeprefix("eq.")])

        async def patch(self, url, headers=None, params=None, json=None):
            seen["patch"], seen["params"] = json, params
            if not stored:
                return _Resp([])
            return _Resp([{**ROW, **json}])

    monkeypatch.setattr(nutrition.httpx, "AsyncClient", lambda **kw: _Client())
    return seen


def edit(**fields):
    return asyncio.run(nutrition.edit_food_entry("e1", nutrition.EditFoodRequest(**fields), "u1"))


def test_changing_the_servings_rescales_every_total(monkeypatch):
    seen = install(monkeypatch)
    edit(servings=3)
    assert seen["patch"] == {"servings": 3, "calories": 450.0, "protein_g": 15.0, "carbs_g": 81.0, "fat_g": 9.0}


def test_changing_only_the_time_leaves_the_totals_alone(monkeypatch):
    seen = install(monkeypatch)
    edit(local_hour=7.5)
    assert seen["patch"] == {"local_hour": 7.5}


def test_meal_time_and_date_can_all_change_at_once(monkeypatch):
    seen = install(monkeypatch)
    edit(meal="dinner", local_hour=18.5, local_date="2026-10-08")
    assert seen["patch"] == {"meal": "dinner", "local_hour": 18.5, "local_date": "2026-10-08"}


def test_the_edit_is_scoped_to_the_signed_in_person(monkeypatch):
    seen = install(monkeypatch)
    edit(local_hour=9)
    assert seen["params"] == {"id": "eq.e1", "user_id": "eq.u1"}


def test_someone_elses_entry_cannot_be_rescaled(monkeypatch):
    install(monkeypatch)
    with pytest.raises(HTTPException) as err:
        asyncio.run(nutrition.edit_food_entry("e1", nutrition.EditFoodRequest(servings=2), "someone-else"))
    assert err.value.status_code == 404


def test_an_entry_that_is_not_there_is_a_404_when_only_the_time_changes(monkeypatch):
    install(monkeypatch, stored=())
    with pytest.raises(HTTPException) as err:
        edit(local_hour=9)
    assert err.value.status_code == 404


def test_an_edit_that_changes_nothing_is_refused(monkeypatch):
    install(monkeypatch)
    with pytest.raises(HTTPException) as err:
        edit()
    assert err.value.status_code == 400


def test_a_silly_amount_is_caught(monkeypatch):
    install(monkeypatch, stored=({**ROW, "calories": 4000.0, "servings": 1.0},))
    with pytest.raises(HTTPException) as err:
        edit(servings=3)
    assert err.value.status_code == 400 and "10,000" in err.value.detail


def test_a_bad_date_is_refused(monkeypatch):
    install(monkeypatch)
    with pytest.raises(HTTPException) as err:
        edit(local_date="not-a-date")
    assert err.value.status_code == 400


def test_zero_or_negative_servings_are_rejected_by_the_request_model():
    for bad in (0, -1, 51):
        with pytest.raises(Exception):
            nutrition.EditFoodRequest(servings=bad)


def test_rescaling_works_from_fractional_servings():
    out = nutrition.rescaled_totals({**ROW, "servings": 0.5, "calories": 100.0}, 1.5)
    assert out["calories"] == 300.0

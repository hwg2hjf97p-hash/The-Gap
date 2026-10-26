import asyncio

from utils import saved_logging

MEAL = {
    "name": "Spag  bol",
    "meal": "dinner",
    "items": [
        {"food_name": "Beef mince", "servings": 2, "per_serving": {"calories": 200, "protein_g": 20, "carbs_g": 0, "fat_g": 12}},
        {"food_name": "Pasta", "servings": 1, "per_serving": {"calories": 300, "protein_g": 10, "carbs_g": 60, "fat_g": 2}},
    ],
}


def test_every_ingredient_of_a_meal_carries_the_same_group_and_the_meals_name():
    rows = saved_logging.saved_meal_rows("u1", MEAL, 1, "2026-10-26", 18.5, None)
    assert len(rows) == 2
    assert len({r["log_group"] for r in rows}) == 1
    assert {r["log_group_name"] for r in rows} == {"Spag bol"}


def test_logging_the_same_meal_twice_makes_two_groups():
    a = saved_logging.saved_meal_rows("u1", MEAL, 1, "2026-10-26", 18.5, None)
    b = saved_logging.saved_meal_rows("u1", MEAL, 1, "2026-10-26", 18.5, None)
    assert a[0]["log_group"] != b[0]["log_group"]


class FakeResponse:
    def __init__(self, status_code, text="", body=None):
        self.status_code, self.text, self._body = status_code, text, body or []

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeClient:
    """A database that doesn't have some columns yet: it refuses a row that carries one, naming it, the way PostgREST does."""

    def __init__(self, missing):
        self.missing = list(missing)
        self.sent = []

    async def post(self, url, headers=None, json=None):
        self.sent.append(json)
        for column in self.missing:
            if any(column in row for row in json):
                return FakeResponse(400, f"{{\"code\":\"PGRST204\",\"message\":\"Could not find the '{column}' column of 'food_log' in the schema cache\"}}")
        return FakeResponse(201, body=[{"id": "x"}])


def test_a_meal_still_saves_when_the_database_has_no_group_columns_yet():
    rows = saved_logging.saved_meal_rows("u1", MEAL, 1, "2026-10-26", 18.5, None)
    client = FakeClient(["log_group", "log_group_name"])
    saved = asyncio.run(saved_logging.insert_food_rows(client, rows))
    assert saved == [{"id": "x"}]
    assert all("log_group" not in r and "log_group_name" not in r for r in client.sent[-1])
    assert client.sent[-1][0]["food_name"] == "Beef mince"


def test_a_meal_saves_with_the_group_when_the_columns_exist():
    rows = saved_logging.saved_meal_rows("u1", MEAL, 1, "2026-10-26", 18.5, None)
    client = FakeClient([])
    asyncio.run(saved_logging.insert_food_rows(client, rows))
    assert len(client.sent) == 1 and client.sent[0][0]["log_group"]


def test_a_real_error_is_still_raised():
    class Down:
        async def post(self, *a, **k):
            return FakeResponse(500, "boom")

    rows = saved_logging.saved_meal_rows("u1", MEAL, 1, "2026-10-26", 18.5, None)
    try:
        asyncio.run(saved_logging.insert_food_rows(Down(), rows))
    except RuntimeError:
        return
    raise AssertionError("a server error was swallowed")

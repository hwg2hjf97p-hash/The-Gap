import asyncio
import json

from routers import profile


def test_the_checklist_reports_each_item_by_name(monkeypatch):
    async def fake_has_row(client, user_id, table, extra):
        return table in ("daily_checkins", "user_goals")

    monkeypatch.setattr(profile, "_has_row", fake_has_row)
    response = asyncio.run(profile.read_checklist(user_id="12345678-aaaa"))
    done = json.loads(response.body)
    assert set(done) == set(profile._CHECKLIST_TABLES)
    assert done["checkin"] is True and done["goal"] is True
    assert done["food"] is False and done["body"] is False


def test_an_empty_row_does_not_count_as_set_up():
    # A body profile or home address row can exist with nothing filled in, so those are matched on the value being present.
    assert profile._CHECKLIST_TABLES["body"][1] == {"weight_kg": "not.is.null"}
    assert profile._CHECKLIST_TABLES["location"][1] == {"home_address": "not.is.null"}
    assert "or" in profile._CHECKLIST_TABLES["nutrition_goals"][1]


def test_a_failed_lookup_counts_as_not_done_rather_than_breaking_the_page(monkeypatch):
    class Boom:
        async def get(self, *a, **k):
            raise RuntimeError("down")

    assert asyncio.run(profile._has_row(Boom(), "u1", "food_log", {})) is False

import asyncio
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from routers import log as log_module
from utils.log_undo import Undo, restorable_fields, safe_ids, snapshot_checkin

ID_A = "11111111-2222-3333-4444-555555555555"
ID_B = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
BRISBANE = "Australia/Brisbane"


# ── the safety rules ────────────────────────────────────────────────────────
def test_only_things_that_look_like_row_ids_are_used():
    assert safe_ids([ID_A, "abc", "x" * 100, "1;drop table", "a,b", None, 5, ID_B]) == [ID_A, ID_B]


def test_a_filter_cannot_be_slipped_into_an_id():
    assert safe_ids(["11111111-2222)or(id.neq.1"]) == []


def test_the_snapshot_keeps_only_the_fields_a_quick_log_changes():
    row = {"user_id": "u1", "date": "2026-10-23", "alcohol_drinks": 2, "stress_score": 9, "notes": "private", "partial": False}
    assert snapshot_checkin(row) == {"alcohol_drinks": 2, "partial": False}
    assert snapshot_checkin(None) is None


def test_only_known_fields_are_ever_restored_and_as_the_right_kind_of_value():
    cleaned = restorable_fields({"alcohol_drinks": "3", "cigarettes": -4, "alcohol": True, "alcohol_time": "evening", "stress_score": 10, "user_id": "someone-else", "afternoon_caffeine": "yes"})
    assert cleaned == {"alcohol_drinks": 3, "cigarettes": 0, "alcohol": True, "alcohol_time": "evening"}


def test_a_null_snapshot_value_is_restored_as_null():
    assert restorable_fields({"alcohol": None, "partial": None}) == {"alcohol": None, "partial": None}


# ── a fake database for the undo ────────────────────────────────────────────
class _Resp:
    def __init__(self, status=200, rows=None, text=""):
        self.status_code, self._rows, self.text = status, rows if rows is not None else [], text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self._rows


class FakeDB:
    def __init__(self, checkin_rows=None, fail_patch_columns=()):
        self.deletes, self.patches, self.gets = [], [], []
        self.checkin_rows = checkin_rows or []
        self.fail_patch_columns = list(fail_patch_columns)


def install(monkeypatch, db: FakeDB):
    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None, params=None):
            db.gets.append((url.rsplit("/", 1)[-1], params))
            return _Resp(200, db.checkin_rows)

        async def delete(self, url, headers=None, params=None):
            db.deletes.append((url.rsplit("/", 1)[-1], params))
            return _Resp(204)

        async def patch(self, url, headers=None, params=None, json=None):
            for col in db.fail_patch_columns:
                if col in json:
                    return _Resp(400, text=f"PGRST204 Could not find the '{col}' column of 'daily_checkins'")
            db.patches.append((url.rsplit("/", 1)[-1], params, json))
            return _Resp(204)

    monkeypatch.setattr(log_module.httpx, "AsyncClient", lambda **kw: _Client())


def run(undo: Undo, user="u1"):
    return asyncio.run(log_module.undo_quick_entry(user, undo))


# ── undoing ─────────────────────────────────────────────────────────────────
def test_the_note_the_water_and_the_food_are_removed_for_this_person_only(monkeypatch):
    db = FakeDB()
    install(monkeypatch, db)
    failed = run(Undo(note_id=ID_A, water_ids=[ID_B], food_ids=[ID_A, ID_B]))
    assert failed == []
    tables = {t: p for t, p in db.deletes}
    assert tables["quick_entries"] == {"id": f"eq.{ID_A}", "user_id": "eq.u1"}
    assert tables["water_log"] == {"id": f"in.({ID_B})", "user_id": "eq.u1"}
    assert tables["food_log"] == {"id": f"in.({ID_A},{ID_B})", "user_id": "eq.u1"}


def test_junk_ids_are_dropped_not_sent(monkeypatch):
    db = FakeDB()
    install(monkeypatch, db)
    run(Undo(note_id="bad id!", water_ids=["1)or(user_id.neq.x"], food_ids=[]))
    assert db.deletes == []


def test_a_check_in_that_existed_is_put_back_as_it_was(monkeypatch):
    db = FakeDB()
    install(monkeypatch, db)
    run(Undo(checkin_touched=True, checkin_day="2026-10-23", checkin_before={"alcohol_drinks": 1, "alcohol": True, "stress_score": 9}))
    assert len(db.patches) == 1
    _, params, body = db.patches[0]
    assert params == {"user_id": "eq.u1", "date": "eq.2026-10-23"}
    assert body == {"alcohol_drinks": 1, "alcohol": True}  # nothing outside the allowed fields


def test_a_missing_column_does_not_stop_the_rest_being_restored(monkeypatch):
    db = FakeDB(fail_patch_columns=["alcohol_time"])
    install(monkeypatch, db)
    assert run(Undo(checkin_touched=True, checkin_day="2026-10-23", checkin_before={"alcohol_drinks": 1, "alcohol_time": "evening"})) == []
    assert db.patches[0][2] == {"alcohol_drinks": 1}


def test_a_check_in_the_log_started_is_removed_while_it_is_still_the_bare_one(monkeypatch):
    db = FakeDB(checkin_rows=[{"partial": True}])
    install(monkeypatch, db)
    run(Undo(checkin_touched=True, checkin_day="2026-10-23", checkin_before=None))
    assert db.deletes == [("daily_checkins", {"date": "eq.2026-10-23", "partial": "eq.true", "user_id": "eq.u1"})]


def test_a_check_in_filled_in_since_is_left_alone(monkeypatch):
    db = FakeDB(checkin_rows=[{"partial": False}])
    install(monkeypatch, db)
    run(Undo(checkin_touched=True, checkin_day="2026-10-23", checkin_before=None))
    assert db.deletes == []


def test_a_bad_date_does_nothing(monkeypatch):
    db = FakeDB()
    install(monkeypatch, db)
    assert run(Undo(checkin_touched=True, checkin_day="not-a-date", checkin_before={"alcohol_drinks": 1})) == []
    assert db.patches == [] and db.deletes == []


def test_weight_goes_back_to_what_it_was(monkeypatch):
    db = FakeDB()
    install(monkeypatch, db)
    saved = []

    async def save_weight(user_id, day, kg):
        saved.append((user_id, day, kg))

    monkeypatch.setattr(log_module, "save_weight", save_weight)
    assert run(Undo(weight_touched=True, weight_day="2026-10-23", weight_previous_kg=81.4)) == []
    assert saved == [("u1", "2026-10-23", 81.4)]


def test_weight_that_had_no_earlier_value_is_removed(monkeypatch):
    db = FakeDB()
    install(monkeypatch, db)
    removed = []

    async def delete_weight(day, user_id):
        removed.append((day.isoformat(), user_id))

    monkeypatch.setattr(log_module, "delete_weight", delete_weight)
    assert run(Undo(weight_touched=True, weight_day="2026-10-23", weight_previous_kg=None)) == []
    assert removed == [("2026-10-23", "u1")]


def test_the_route_says_what_could_not_be_undone(monkeypatch):
    async def failing(user_id, undo):
        return ["the water"]

    monkeypatch.setattr(log_module, "undo_quick_entry", failing)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(log_module.undo_log(Undo(), "u1"))
    assert caught.value.status_code == 500
    assert "the water" in caught.value.detail


# ── a log reports what it created ───────────────────────────────────────────
def _at(hour):
    return datetime(2026, 10, 9, hour - 10, 0, tzinfo=timezone.utc)


def test_a_logged_water_reports_its_row_so_it_can_be_undone(monkeypatch):
    posts = []

    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None, params=None):
            table = url.rsplit("/", 1)[-1]
            return _Resp(200, [{"amount_ml": 500}] if table == "water_log" else [])

        async def post(self, url, headers=None, params=None, json=None):
            table = url.rsplit("/", 1)[-1]
            posts.append(table)
            if table == "water_log":
                return _Resp(201, [{"id": ID_B, **json}])
            if table == "quick_entries":
                return _Resp(201, [{"id": ID_A}])
            return _Resp(201, json if isinstance(json, list) else [json])

    async def zero(user_id, day):
        return 1

    monkeypatch.setattr(log_module.httpx, "AsyncClient", lambda **kw: _Client())
    monkeypatch.setattr(log_module, "_count_today", zero)
    monkeypatch.setattr(log_module, "_get_streak", zero)
    result = asyncio.run(log_module.process_log_text("u1", "just drank 300ml of water", None, _at(12), BRISBANE, "app"))
    assert result["undo"]["water_ids"] == [ID_B]
    assert result["undo"]["note_id"] == ID_A

import asyncio
import json
from datetime import date, timedelta

import pytest
from fastapi import HTTPException

from routers import life_events as router
from routers import account, assistant
from utils import life_events as le

TODAY = date(2026, 10, 21)


def series(start: date, values):
    return [(start + timedelta(days=i), v) for i, v in enumerate(values)]


# ── what can be added ────────────────────────────────────────────────────────

def test_a_good_event_is_accepted_and_the_note_is_trimmed():
    fields, problem = le.validate("job_lost", "2026-09-02", "  tough week  ", TODAY)
    assert problem is None and fields == {"kind": "job_lost", "event_date": "2026-09-02", "note": "tough week"}
    fields, _ = le.validate("moved", "2026-10-21", "x" * 500, TODAY)
    assert fields is not None and len(fields["note"]) == le.MAX_NOTE


def test_bad_events_are_refused_with_a_plain_reason():
    assert le.validate("nonsense", "2026-09-02", None, TODAY)[1] == "Pick what changed from the list."
    assert "date" in le.validate("moved", "yesterday", None, TODAY)[1]
    assert "future" in le.validate("moved", "2026-10-22", None, TODAY)[1]
    assert "year ago" in le.validate("moved", "2025-01-01", None, TODAY)[1]
    assert le.validate("moved", "2026-09-02", "", TODAY)[0]["note"] is None


# ── what changed around it ───────────────────────────────────────────────────

def test_a_clear_drop_after_the_event_is_described():
    event = date(2026, 9, 2)
    before = series(event - timedelta(days=14), [60, 62, 61, 63, 60, 62, 61, 59, 62, 60, 61, 63, 62, 60])
    after = series(event + timedelta(days=1), [48, 50, 47, 49, 51, 48, 46, 50, 49, 47, 48, 50, 49, 47])
    found = le.compare(before + after, event, TODAY)
    assert found is not None
    mean_before, mean_after, n_before, n_after = found
    assert mean_before > 60 and mean_after < 50 and (n_before, n_after) == (14, 14)
    text = le.sentence("hrv", "HRV", mean_before, mean_after, n_before, n_after)
    assert "HRV averaged 48" in text and "against 61" in text and "14 days after" in text and "14 days before" in text


def test_sleep_is_shown_in_hours_not_minutes():
    text = le.sentence("sleep_total_min", "sleep", 450.0, 390.0, 14, 12)
    assert "6.5 hrs" in text and "7.5 hrs" in text


def test_it_says_nothing_without_enough_days_or_a_real_change():
    event = date(2026, 9, 2)
    steady = series(event - timedelta(days=14), [60, 62, 61, 63, 60, 62, 61, 59, 62, 60, 61, 63, 62, 60] + [None] * 1 + [61, 62, 60, 63, 61, 62, 60, 61, 62, 60, 61, 62, 60])
    steady = [(d, v) for d, v in steady if v is not None]
    assert le.compare(steady, event, TODAY) is None  # a wobble, not a change
    too_few = series(event - timedelta(days=3), [60, 61, 60]) + series(event + timedelta(days=1), [40, 41, 40, 41, 40, 41, 40, 41])
    assert le.compare(too_few, event, TODAY) is None
    assert le.compare(steady, date(2026, 10, 18), TODAY) is None  # only three days have passed


def test_a_flat_run_of_days_is_not_divided_by_zero():
    event = date(2026, 9, 2)
    flat = series(event - timedelta(days=14), [60.0] * 14) + series(event + timedelta(days=1), [50.0] * 14)
    assert le.compare(flat, event, TODAY) is None


def test_effects_are_worked_out_for_each_event(monkeypatch):
    event = date(2026, 9, 2)
    before = series(event - timedelta(days=14), [60, 62, 61, 63, 60, 62, 61, 59, 62, 60, 61, 63, 62, 60])
    after = series(event + timedelta(days=1), [48, 50, 47, 49, 51, 48, 46, 50, 49, 47, 48, 50, 49, 47])

    async def points(user_id, key, since):
        return before + after if key == "hrv" else []

    monkeypatch.setattr(le, "fetch_points", points)
    out = asyncio.run(le.effects_for("u1", [{"id": "e1", "event_date": "2026-09-02"}, {"id": "e2", "event_date": "2026-10-20"}], TODAY))
    assert len(out["e1"]) == 1 and "HRV" in out["e1"][0]
    assert out["e2"] == []  # too recent to say anything


# ── the routes ───────────────────────────────────────────────────────────────

def test_adding_checks_the_event_and_refuses_a_repeat(monkeypatch):
    async def today(user_id):
        return TODAY

    async def existing(user_id):
        return [{"id": "e1", "kind": "moved", "event_date": "2026-09-02"}]

    monkeypatch.setattr(router, "user_today", today)
    monkeypatch.setattr(le, "list_events", existing)
    with pytest.raises(HTTPException) as err:
        asyncio.run(router.add_event(router.EventBody(kind="nonsense", event_date="2026-09-02"), user_id="u1"))
    assert err.value.status_code == 400
    with pytest.raises(HTTPException) as err:
        asyncio.run(router.add_event(router.EventBody(kind="moved", event_date="2026-09-02"), user_id="u1"))
    assert err.value.status_code == 409


def test_the_list_reports_when_the_table_is_not_there_yet(monkeypatch):
    async def broken(user_id):
        raise RuntimeError("no such table")

    monkeypatch.setattr(le, "list_events", broken)
    out = json.loads(asyncio.run(router.list_my_events(user_id="u1")).body)
    assert out["events"] == [] and out["available"] is False and len(out["kinds"]) == len(le.KINDS)


def test_the_list_carries_labels_and_what_changed(monkeypatch):
    async def events(user_id):
        return [{"id": "e1", "kind": "job_lost", "event_date": "2026-09-02", "note": "private", "created_at": "x"}]

    async def effects(user_id, evs, today):
        return {"e1": ["Your HRV averaged 48 ms."]}

    async def today(user_id):
        return TODAY

    monkeypatch.setattr(le, "list_events", events)
    monkeypatch.setattr(le, "effects_for", effects)
    monkeypatch.setattr(router, "user_today", today)
    out = json.loads(asyncio.run(router.list_my_events(user_id="u1")).body)
    assert out["events"][0]["label"] == "Lost or left a job" and out["events"][0]["changes"] == ["Your HRV averaged 48 ms."]
    assert "isn't what caused" not in out["caveat"] and "not what caused" in out["caveat"]


# ── privacy ──────────────────────────────────────────────────────────────────

def test_gappy_gets_the_type_and_date_but_never_the_note(monkeypatch):
    async def events(user_id):
        return [{"id": "e1", "kind": "loss", "event_date": "2026-09-02", "note": "my private words"}]

    monkeypatch.setattr(le, "list_events", events)
    text = asyncio.run(le.for_assistant("u1"))
    assert "Loss of someone close" in text and "2026-09-02" in text and "private" not in text


def test_gappy_is_told_how_to_treat_big_changes_and_the_data_can_be_deleted():
    assert "never as its cause" in assistant.SYSTEM_PROMPT and "grief, mood or mental health" in assistant.SYSTEM_PROMPT
    assert "life_events" in account.USER_DATA_TABLES

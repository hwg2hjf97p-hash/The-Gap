import asyncio
import sys
import types
from datetime import date

import numpy as np
import pytest
from fastapi import HTTPException

from routers import app_config, demo
from utils.demo_data import DAYS, SCREEN_LAST_USE, generate_demo_data

LAST_DAY = date(2026, 10, 6)


# ── the sample data itself ───────────────────────────────────────────────────

def test_twelve_weeks_ending_on_the_given_day():
    health, checkins = generate_demo_data(LAST_DAY)
    assert len(health) == DAYS == len(checkins)
    assert max(health) == LAST_DAY.isoformat()
    assert [c["date"] for c in checkins] == sorted(health)


def test_the_same_twelve_weeks_every_time():
    assert generate_demo_data(LAST_DAY) == generate_demo_data(LAST_DAY)


def test_values_look_like_a_real_person():
    health, checkins = generate_demo_data(LAST_DAY)
    for row in health.values():
        assert 25 <= row["hrv"] <= 110 and 40 <= row["resting_hr"] <= 90
        assert 240 <= row["sleep_total_min"] <= 600 and 20 <= row["sleep_deep_min"] <= 140
        assert 1800 <= row["steps"] <= 18000
    for c in checkins:
        assert 1 <= c["stress_score"] <= 10
        assert 0 <= c["screen_hours"] <= 24 and c["screen_last_use"] in SCREEN_LAST_USE
        assert isinstance(c["alcohol"], bool) and isinstance(c["afternoon_caffeine"], bool)
        assert 0 <= c["work_hours"] <= 24


def _arrays():
    health, checkins = generate_demo_data(LAST_DAY)
    days = sorted(health)
    hrv = np.array([health[d]["hrv"] for d in days])
    rhr = np.array([health[d]["resting_hr"] for d in days])
    sleep = np.array([health[d]["sleep_total_min"] for d in days])
    deep = np.array([health[d]["sleep_deep_min"] for d in days])
    steps = np.array([health[d]["steps"] for d in days])
    alcohol = np.array([c["alcohol"] for c in checkins], dtype=bool)
    caffeine = np.array([c["afternoon_caffeine"] for c in checkins], dtype=bool)
    late = np.array([c["screen_last_use"] in ("11pm_1am", "after_1am") for c in checkins], dtype=bool)
    return hrv, rhr, sleep, deep, steps, alcohol, caffeine, late


def test_there_are_enough_drinking_and_caffeine_days_for_the_engine():
    *_, alcohol, caffeine, late = _arrays()
    assert alcohol.sum() >= 12 and caffeine.sum() >= 12 and late.sum() >= 12


def test_a_drink_is_followed_by_lower_hrv_and_higher_resting_heart_rate():
    hrv, rhr, _, _, _, alcohol, _, _ = _arrays()
    after = alcohol[:-1]
    assert hrv[1:][after].mean() < hrv[1:][~after].mean() - 4
    assert rhr[1:][after].mean() > rhr[1:][~after].mean() + 1.5


def test_more_steps_are_followed_by_higher_hrv():
    hrv, _, _, _, steps, *_ = _arrays()
    assert np.corrcoef(steps[:-1], hrv[1:])[0, 1] > 0.1


def test_afternoon_caffeine_cuts_deep_sleep():
    _, _, _, deep, _, _, caffeine, _ = _arrays()
    assert deep[caffeine].mean() < deep[~caffeine].mean() - 5


def test_late_phone_use_shortens_sleep():
    _, _, sleep, _, _, _, _, late = _arrays()
    assert sleep[late].mean() < sleep[~late].mean() - 20


# ── free access switch ───────────────────────────────────────────────────────

def test_free_access_is_off_unless_switched_on(monkeypatch):
    monkeypatch.delenv("FREE_ACCESS", raising=False)
    assert app_config.free_access_enabled() is False
    monkeypatch.setenv("FREE_ACCESS", "maybe")
    assert app_config.free_access_enabled() is False
    monkeypatch.setenv("FREE_ACCESS", "True")
    assert app_config.free_access_enabled() is True


# ── loading and removing sample data ─────────────────────────────────────────

def _fake_sync(result):
    module = types.ModuleType("sync.daily_sync")
    calls = []

    async def _sync_user(user_id, connections):
        calls.append((user_id, connections))
        return result

    module._sync_user = _sync_user  # type: ignore[attr-defined]
    return module, calls


def _wire(monkeypatch, *, empty=True, sync_result=None, save_fails=False):
    events = []

    async def account_is_empty(user_id):
        return empty

    async def upsert(user_id, rows):
        events.append(("health", len(rows)))

    async def save_checkins(user_id, rows):
        if save_fails:
            raise RuntimeError("db down")
        events.append(("checkins", len(rows)))

    async def set_flag(user_id, active):
        events.append(("flag", active))

    async def remove_rows(user_id):
        events.append(("removed",))

    for name, fn in (
        ("_account_is_empty", account_is_empty),
        ("upsert_apple_health_rows", upsert),
        ("_save_checkins", save_checkins),
        ("_set_demo_flag", set_flag),
        ("_remove_demo_rows", remove_rows),
    ):
        monkeypatch.setattr(demo, name, fn)
    module, calls = _fake_sync(sync_result or {"status": "success", "insights": 7, "days": 84})
    monkeypatch.setitem(sys.modules, "sync.daily_sync", module)
    return events, calls


def test_loading_demo_data_runs_the_normal_analysis(monkeypatch):
    events, calls = _wire(monkeypatch)
    response = asyncio.run(demo.load_demo(user_id="u1"))
    assert response.status_code == 200
    assert events == [("health", 84), ("checkins", 84), ("flag", True)]
    assert calls == [("u1", [])]


def test_demo_data_is_refused_on_an_account_that_has_data(monkeypatch):
    events, calls = _wire(monkeypatch, empty=False)
    with pytest.raises(HTTPException) as err:
        asyncio.run(demo.load_demo(user_id="u1"))
    assert err.value.status_code == 409
    assert events == [] and calls == []


def test_a_failed_save_leaves_nothing_behind(monkeypatch):
    events, calls = _wire(monkeypatch, save_fails=True)
    with pytest.raises(HTTPException) as err:
        asyncio.run(demo.load_demo(user_id="u1"))
    assert err.value.status_code == 500
    assert ("removed",) in events and ("flag", True) not in events
    assert calls == []


def test_a_failed_analysis_removes_the_sample_data(monkeypatch):
    events, _ = _wire(monkeypatch, sync_result={"status": "engine_error"})
    with pytest.raises(HTTPException):
        asyncio.run(demo.load_demo(user_id="u1"))
    assert events[-2:] == [("removed",), ("flag", False)]


def test_removing_needs_the_demo_flag(monkeypatch):
    events, _ = _wire(monkeypatch)

    async def no_flag(user_id):
        return {"primary": {"sleep": "whoop"}}

    monkeypatch.setattr(demo, "load_source_prefs", no_flag)
    with pytest.raises(HTTPException) as err:
        asyncio.run(demo.remove_demo(user_id="u1"))
    assert err.value.status_code == 409 and events == []

    async def with_flag(user_id):
        return {"demo": True}

    monkeypatch.setattr(demo, "load_source_prefs", with_flag)
    response = asyncio.run(demo.remove_demo(user_id="u1"))
    assert response.status_code == 200
    assert events == [("removed",), ("flag", False)]

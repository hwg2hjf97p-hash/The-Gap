import asyncio
from datetime import date

import pandas as pd
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from routers import weight
from sync import weight_store
from utils.source_merge import DEFAULT_PRIORITY, SOURCE_LABELS, merge_sources

TODAY = date(2026, 10, 8)


def test_only_sensible_weights_are_accepted():
    assert weight.WeightBody(weight_kg=72.4).weight_kg == 72.4
    for bad in (7.2, 19.9, 401, -5):
        with pytest.raises(ValidationError):
            weight.WeightBody(weight_kg=bad)


def test_a_day_that_has_not_happened_or_is_too_far_back_is_refused():
    assert weight.valid_log_date(None, TODAY) is None
    assert weight.valid_log_date(TODAY, TODAY) is None
    assert weight.valid_log_date(date(2026, 8, 20), TODAY) is None
    assert "hasn't happened" in weight.valid_log_date(date(2026, 10, 9), TODAY)
    assert "60 days" in weight.valid_log_date(date(2026, 7, 1), TODAY)


class _Resp:
    def __init__(self, rows=None):
        self._rows = rows or []

    def raise_for_status(self):
        pass

    def json(self):
        return self._rows


def _fake_db(monkeypatch, rows=None, fail=False):
    calls = []

    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, params=None, json=None):
            if fail:
                raise RuntimeError("db down")
            calls.append((url.rsplit("/", 1)[-1], json))
            return _Resp()

        async def get(self, url, headers=None, params=None):
            return _Resp(rows if rows is not None else [{"local_date": "2026-10-08", "weight_kg": 72.4}])

        async def delete(self, url, headers=None, params=None):
            calls.append(("delete:" + url.rsplit("/", 1)[-1], params))
            return _Resp()

    async def user_today(user_id):
        return TODAY

    async def current_average(user_id, metric, today=None):
        return 72.1, 5

    async def check(user_id):
        calls.append(("goals_checked", None))
        return []

    monkeypatch.setattr(weight.httpx, "AsyncClient", lambda **kw: _Client())
    monkeypatch.setattr(weight, "user_today", user_today)
    monkeypatch.setattr(weight, "current_average", current_average)
    monkeypatch.setattr(weight, "check_goal_achievements", check)
    return calls


def test_logging_a_weight_saves_it_and_updates_history_and_goals(monkeypatch):
    calls = _fake_db(monkeypatch)
    response = asyncio.run(weight.log_weight(weight.WeightBody(weight_kg=72.4), user_id="u1"))
    assert response.status_code == 200
    assert [t for t, _ in calls] == ["weight_log", "metric_history", "goals_checked"]
    assert calls[0][1] == {"user_id": "u1", "local_date": "2026-10-08", "weight_kg": 72.4}
    assert calls[1][1][0]["metric"] == "weight_kg" and calls[1][1][0]["value"] == 72.4
    assert b'"average_7d":72.1' in response.body.replace(b" ", b"")


def test_a_failed_save_says_so(monkeypatch):
    _fake_db(monkeypatch, fail=True)
    with pytest.raises(HTTPException) as err:
        asyncio.run(weight.log_weight(weight.WeightBody(weight_kg=72.4), user_id="u1"))
    assert err.value.status_code == 500


def test_a_future_date_is_refused_before_anything_is_saved(monkeypatch):
    calls = _fake_db(monkeypatch)
    with pytest.raises(HTTPException) as err:
        asyncio.run(weight.log_weight(weight.WeightBody(weight_kg=72.4, local_date=date(2026, 10, 20)), user_id="u1"))
    assert err.value.status_code == 400 and calls == []


def test_deleting_an_entry_removes_it_from_the_log_and_the_history(monkeypatch):
    calls = _fake_db(monkeypatch)
    asyncio.run(weight.delete_weight(date(2026, 10, 7), user_id="u1"))
    assert [t for t, _ in calls] == ["delete:weight_log", "delete:metric_history"]


def test_logged_weights_become_a_daily_table(monkeypatch):
    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None, params=None):
            return _Resp([{"local_date": "2026-10-06", "weight_kg": "72.8"}, {"local_date": "2026-10-07", "weight_kg": "72.4"}])

    monkeypatch.setattr(weight_store.httpx, "AsyncClient", lambda **kw: _Client())
    df = asyncio.run(weight_store.get_weight_dataframe("u1"))
    assert list(df.columns) == ["weight_kg"] and df["weight_kg"].tolist() == [72.8, 72.4]
    assert df.index[0] == pd.Timestamp("2026-10-06")


def test_logged_weight_is_a_named_source_that_leads_for_weight():
    assert SOURCE_LABELS["manual"] == "Logged in the app"
    assert DEFAULT_PRIORITY["body"][0] == "manual"


def test_a_logged_weight_beats_a_scale_on_the_same_day_and_fills_the_rest():
    days = pd.date_range("2026-10-01", periods=4)
    scale = pd.DataFrame({"weight_kg": [80.0, 80.2, 80.4, 80.6]}, index=days)
    logged = pd.DataFrame({"weight_kg": [79.5]}, index=days[1:2])
    merged = merge_sources({"withings": scale, "manual": logged}, None)
    assert merged["weight_kg"].tolist() == [80.0, 79.5, 80.4, 80.6]

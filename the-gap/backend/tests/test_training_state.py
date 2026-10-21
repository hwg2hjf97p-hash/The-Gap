import asyncio
import json

import pytest
from fastapi import HTTPException

from routers import training_state as ts


def test_good_values_are_accepted_and_only_what_was_sent_is_saved():
    out, problem = ts.clean({"weekly_target": 4})
    assert problem is None and out == {"weekly_target": 4}
    out, _ = ts.clean({"rest_pref": "90", "active_program": {"id": "full-body-3", "startDate": "2026-10-19"}})
    assert out == {"rest_pref": "90", "active_program": {"id": "full-body-3", "startDate": "2026-10-19"}}


def test_a_value_can_be_cleared_with_null():
    out, problem = ts.clean({"active_program": None, "rest_pref": None, "weekly_target": None})
    assert problem is None and out == {"active_program": None, "rest_pref": None, "weekly_target": None}


def test_bad_values_are_refused_with_a_reason():
    assert ts.clean({"weekly_target": 9})[1] and ts.clean({"weekly_target": 0})[1]
    assert ts.clean({"rest_pref": "forever"})[1]
    assert ts.clean({"active_program": {"id": "../../x", "startDate": "2026-10-19"}})[1]
    assert ts.clean({"active_program": {"id": "full-body-3", "startDate": "next monday"}})[1]


def test_the_body_model_rejects_a_target_out_of_range():
    with pytest.raises(Exception):
        ts.StateBody(weekly_target=12)


def test_saving_sends_only_the_fields_that_were_given(monkeypatch):
    posted = []

    class _Resp:
        def raise_for_status(self):
            pass

    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, params=None, json=None):
            posted.append(dict(json))
            return _Resp()

    monkeypatch.setattr(ts.httpx, "AsyncClient", lambda **kw: _Client())
    out = json.loads(asyncio.run(ts.put_state(ts.StateBody(rest_pref="auto"), user_id="u1")).body)
    assert out["saved"] == ["rest_pref"]
    assert posted[0]["rest_pref"] == "auto" and "weekly_target" not in posted[0] and "active_program" not in posted[0]
    asyncio.run(ts.put_state(ts.StateBody(active_program=None, weekly_target=3), user_id="u1"))
    assert posted[1]["active_program"] is None and posted[1]["weekly_target"] == 3  # an explicit null clears it


def test_reading_before_the_table_exists_says_nothing_is_saved_yet(monkeypatch):
    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, *a, **k):
            raise RuntimeError("no such table")

    monkeypatch.setattr(ts.httpx, "AsyncClient", lambda **kw: _Client())
    out = json.loads(asyncio.run(ts.get_state(user_id="u1")).body)
    assert out["exists"] is False and out["available"] is False and out["weekly_target"] is None


def test_a_failed_save_tells_the_phone_to_keep_it_locally(monkeypatch):
    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *a, **k):
            raise RuntimeError("down")

    monkeypatch.setattr(ts.httpx, "AsyncClient", lambda **kw: _Client())
    with pytest.raises(HTTPException) as err:
        asyncio.run(ts.put_state(ts.StateBody(weekly_target=3), user_id="u1"))
    assert err.value.status_code == 503 and "kept on this phone" in err.value.detail

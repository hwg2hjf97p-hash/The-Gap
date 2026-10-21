import asyncio

import pytest
from fastapi import HTTPException

from routers import push as push_router
from utils import push as push


def test_what_expo_said_about_each_message_is_read_properly():
    tokens = ["a", "b", "c"]
    tickets = [
        {"status": "ok", "id": "t1"},
        {"status": "error", "message": "gone", "details": {"error": "DeviceNotRegistered"}},
        {"status": "error", "message": "bad key", "details": {"error": "InvalidCredentials"}},
    ]
    out = push.read_tickets(tokens, tickets)
    assert out["accepted"] == 1 and out["ticket_ids"] == ["t1"]
    assert out["dead_tokens"] == ["b"]
    assert len(out["errors"]) == 2 and "InvalidCredentials" in out["errors"][1]


def test_a_person_with_no_registered_phone_is_told_so_plainly():
    assert "No phone is registered" in push_router.plain_verdict(0, 0, [], [])
    assert "did not go through" in push_router.plain_verdict(1, 1, [], ["InvalidCredentials: x"])
    assert "wasn't accepted" in push_router.plain_verdict(1, 0, [], [])
    assert push_router.plain_verdict(2, 2, [], []).startswith("Test sent")


def test_tests_are_limited_per_hour():
    push_router._test_calls.clear()
    for i in range(push_router.MAX_TESTS_PER_HOUR):
        assert push_router._too_many_tests("u1", now=1000 + i) is False
    assert push_router._too_many_tests("u1", now=2000) is True
    assert push_router._too_many_tests("u1", now=1000 + 3601) is False
    assert push_router._too_many_tests("u2", now=2000) is False
    push_router._test_calls.clear()


def test_a_send_with_no_registered_phone_says_so_and_sends_nothing(monkeypatch):
    async def prefs(user_id):
        return None

    async def tokens(user_id):
        return []

    monkeypatch.setattr(push, "get_prefs", prefs)
    monkeypatch.setattr(push, "_get_tokens_for_user", tokens)
    out = asyncio.run(push.send_push_detailed("u1", "t", "b"))
    assert out["tokens"] == 0 and out["accepted"] == 0 and out["held"] is False


def test_a_phone_expo_says_is_gone_is_forgotten(monkeypatch):
    forgotten = []

    async def prefs(user_id):
        return None

    async def tokens(user_id):
        return ["good", "gone"]

    async def forget(user_id, dead):
        forgotten.extend(dead)

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [{"status": "ok", "id": "t1"}, {"status": "error", "message": "x", "details": {"error": "DeviceNotRegistered"}}]}

    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *a, **k):
            return _Resp()

    monkeypatch.setattr(push, "get_prefs", prefs)
    monkeypatch.setattr(push, "_get_tokens_for_user", tokens)
    monkeypatch.setattr(push, "_forget_tokens", forget)
    monkeypatch.setattr(push.httpx, "AsyncClient", lambda **kw: _Client())
    out = asyncio.run(push.send_push_detailed("u1", "t", "b"))
    assert out["accepted"] == 1 and out["tokens"] == 2 and forgotten == ["gone"]

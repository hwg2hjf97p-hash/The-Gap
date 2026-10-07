import asyncio

import pytest

from utils import consent


class _FakeResponse:
    def __init__(self, rows):
        self._rows = rows

    def raise_for_status(self):
        pass

    def json(self):
        return self._rows


class _FakeClient:
    def __init__(self, rows=None, fail=False):
        self.rows, self.fail = rows, fail

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError("database down")
        return _FakeResponse(self.rows)


def _ask(monkeypatch, rows=None, fail=False, strict=False):
    consent._cache.clear()
    if strict:
        monkeypatch.setenv("REQUIRE_AI_CONSENT", "true")
    else:
        monkeypatch.delenv("REQUIRE_AI_CONSENT", raising=False)
    monkeypatch.setattr(consent.httpx, "AsyncClient", lambda **kw: _FakeClient(rows, fail))
    return asyncio.run(consent.ai_allowed("user-1"))


def test_a_recorded_yes_allows_ai(monkeypatch):
    assert _ask(monkeypatch, rows=[{"ai_processing": True}]) is True


def test_a_recorded_no_blocks_ai_even_when_not_strict(monkeypatch):
    assert _ask(monkeypatch, rows=[{"ai_processing": False}]) is False


def test_no_record_is_allowed_by_default_but_blocked_when_strict(monkeypatch):
    assert _ask(monkeypatch, rows=[]) is True
    assert _ask(monkeypatch, rows=[], strict=True) is False


def test_database_trouble_follows_the_strict_setting(monkeypatch):
    assert _ask(monkeypatch, fail=True) is True
    assert _ask(monkeypatch, fail=True, strict=True) is False


def test_the_answer_is_remembered_briefly_and_can_be_forgotten(monkeypatch):
    assert _ask(monkeypatch, rows=[{"ai_processing": True}]) is True
    # Now the database says no, but the remembered answer is still used...
    monkeypatch.setattr(consent.httpx, "AsyncClient", lambda **kw: _FakeClient([{"ai_processing": False}]))
    assert asyncio.run(consent.ai_allowed("user-1")) is True
    # ...until a change in Settings makes the server forget it.
    consent.forget("user-1")
    assert asyncio.run(consent.ai_allowed("user-1")) is False


def test_oauth_state_round_trips_and_rejects_tampering():
    from routers import connect

    token = connect._store_state("", "user-123", "whoop", "mobile")
    data = connect._consume_state(token)
    assert data is not None and data["user_id"] == "user-123" and data["provider"] == "whoop" and data["platform"] == "mobile"

    body, sig = token.rsplit(".", 1)
    assert connect._consume_state(body + "." + ("0" * len(sig))) is None
    assert connect._consume_state("garbage") is None


def test_oauth_signing_key_is_not_a_fixed_string_in_the_source():
    from routers import connect

    assert connect._STATE_SECRET != b"thegap-sync-2026"


def test_entitlement_check_is_off_until_switched_on(monkeypatch):
    from fastapi import HTTPException
    from utils import entitlement

    async def not_subscribed(user_id):
        return False

    monkeypatch.setattr(entitlement, "is_subscribed", not_subscribed)

    monkeypatch.delenv("REQUIRE_SUBSCRIPTION", raising=False)
    asyncio.run(entitlement.require_subscription("user-1"))  # allowed: not required yet

    monkeypatch.setenv("REQUIRE_SUBSCRIPTION", "true")
    monkeypatch.delenv("FREE_ACCESS", raising=False)
    with pytest.raises(HTTPException) as err:
        asyncio.run(entitlement.require_subscription("user-1"))
    assert err.value.status_code == 402

    monkeypatch.setenv("FREE_ACCESS", "true")  # the testing switch lets everyone in
    asyncio.run(entitlement.require_subscription("user-1"))


def test_debug_pages_are_hidden_without_the_secret(monkeypatch):
    from fastapi import HTTPException

    from utils import debug_guard

    monkeypatch.delenv("DEBUG_SECRET", raising=False)
    with pytest.raises(HTTPException) as err:
        debug_guard.require_debug_secret("anything")
    assert err.value.status_code == 404

    monkeypatch.setenv("DEBUG_SECRET", "s3cret")
    with pytest.raises(HTTPException):
        debug_guard.require_debug_secret("wrong")
    assert debug_guard.require_debug_secret("s3cret") is None


def test_webhook_refuses_everyone_when_no_secret_is_configured(monkeypatch):
    from fastapi import HTTPException

    from routers import subscriptions

    monkeypatch.setattr(subscriptions, "REVENUECAT_WEBHOOK_SECRET", "")
    with pytest.raises(HTTPException) as err:
        asyncio.run(subscriptions.revenuecat_webhook({"event": {}}, authorization="Bearer "))
    assert err.value.status_code == 401


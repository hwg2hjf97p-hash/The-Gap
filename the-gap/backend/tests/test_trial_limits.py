import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from routers import assistant, subscriptions


class _Resp:
    def __init__(self, rows=None, status=200, text=""):
        self._rows, self.status_code, self.text = rows if rows is not None else [], status, text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self._rows


def install(monkeypatch, rows=(), fail=False, reject_period_type=False):
    posts = []

    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None, params=None):
            if fail:
                raise RuntimeError("down")
            return _Resp(list(rows))

        async def post(self, url, headers=None, params=None, json=None):
            posts.append(json[0])
            if reject_period_type and "period_type" in json[0]:
                return _Resp(status=400, text="PGRST204 Could not find the 'period_type' column")
            return _Resp()

    monkeypatch.setattr(subscriptions.httpx, "AsyncClient", lambda **kw: _Client())
    return posts


def soon(days):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def check(user="u1"):
    return asyncio.run(subscriptions.is_on_trial(user))


def test_someone_in_their_free_month_is_on_trial(monkeypatch):
    install(monkeypatch, rows=[{"is_active": True, "expires_at": soon(10), "period_type": "TRIAL"}])
    assert check() is True


def test_someone_paying_is_not_on_trial(monkeypatch):
    install(monkeypatch, rows=[{"is_active": True, "expires_at": soon(10), "period_type": "NORMAL"}])
    assert check() is False


def test_a_lapsed_trial_is_not_on_trial(monkeypatch):
    install(monkeypatch, rows=[{"is_active": True, "expires_at": soon(-1), "period_type": "TRIAL"}])
    assert check() is False
    install(monkeypatch, rows=[{"is_active": False, "expires_at": soon(10), "period_type": "TRIAL"}])
    assert check() is False


def test_no_record_or_an_old_record_without_the_column_counts_as_paying(monkeypatch):
    install(monkeypatch, rows=[])
    assert check() is False
    install(monkeypatch, rows=[{"is_active": True, "expires_at": soon(10)}])
    assert check() is False


def test_a_database_problem_never_locks_anyone_into_the_trial_limit(monkeypatch):
    install(monkeypatch, fail=True)
    assert check() is False


def event(period_type="TRIAL"):
    return {"event": {"type": "INITIAL_PURCHASE", "app_user_id": "u1", "product_id": "gap_plus_monthly", "expiration_at_ms": 1900000000000, "period_type": period_type}}


def hook(body):
    return asyncio.run(subscriptions.revenuecat_webhook(body, "Bearer s3cret"))


def test_the_webhook_records_the_period_type(monkeypatch):
    monkeypatch.setattr(subscriptions, "REVENUECAT_WEBHOOK_SECRET", "s3cret")
    posts = install(monkeypatch)
    hook(event("trial"))
    assert posts[0]["period_type"] == "TRIAL" and posts[0]["is_active"] is True


def test_the_webhook_still_records_the_rest_if_the_column_is_not_there_yet(monkeypatch):
    monkeypatch.setattr(subscriptions, "REVENUECAT_WEBHOOK_SECRET", "s3cret")
    posts = install(monkeypatch, reject_period_type=True)
    hook(event("TRIAL"))
    assert len(posts) == 2 and "period_type" not in posts[1] and posts[1]["is_active"] is True


# ── the assistant's daily limit ──────────────────────────────────────────────

def ask(monkeypatch, *, asked, on_trial):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")

    async def allowed(user_id):
        return True

    async def entitled(user_id):
        return None

    async def count(user_id):
        return asked

    async def trial(user_id):
        return on_trial

    def stop_here(user_id):
        raise RuntimeError("past-the-limit")

    monkeypatch.setattr(assistant, "ai_allowed", allowed)
    monkeypatch.setattr(assistant, "require_subscription", entitled)
    monkeypatch.setattr(assistant, "_questions_in_last_day", count)
    monkeypatch.setattr(assistant, "is_on_trial", trial)
    monkeypatch.setattr(assistant, "get_latest_results", stop_here)
    return asyncio.run(assistant.ask(assistant.AskRequest(question="hi"), "u1"))


def test_the_trial_gets_ten_questions_a_day(monkeypatch):
    with pytest.raises(HTTPException) as err:
        ask(monkeypatch, asked=10, on_trial=True)
    assert err.value.status_code == 429 and "10" in err.value.detail and "free week" in err.value.detail


def test_the_ninth_trial_question_still_goes_through(monkeypatch):
    with pytest.raises(RuntimeError, match="past-the-limit"):
        ask(monkeypatch, asked=9, on_trial=True)


def test_a_paying_person_keeps_the_normal_limit(monkeypatch):
    with pytest.raises(RuntimeError, match="past-the-limit"):
        ask(monkeypatch, asked=10, on_trial=False)
    with pytest.raises(HTTPException) as err:
        ask(monkeypatch, asked=assistant.MAX_QUESTIONS_PER_DAY, on_trial=False)
    assert err.value.status_code == 429 and "free week" not in err.value.detail

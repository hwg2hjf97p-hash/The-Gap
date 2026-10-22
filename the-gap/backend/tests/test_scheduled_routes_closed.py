import asyncio

import pytest
from fastapi import HTTPException

from routers import digest, feed


def test_digest_run_refuses_everyone_when_no_secret_is_set(monkeypatch):
    monkeypatch.setattr(digest, "SYNC_SECRET", "")
    with pytest.raises(HTTPException) as caught:
        asyncio.run(digest.run_weekly_digest(x_sync_secret=""))
    assert caught.value.status_code == 403


def test_digest_run_refuses_a_wrong_secret(monkeypatch):
    monkeypatch.setattr(digest, "SYNC_SECRET", "right")
    with pytest.raises(HTTPException) as caught:
        asyncio.run(digest.run_weekly_digest(x_sync_secret="wrong"))
    assert caught.value.status_code == 403


def test_feed_run_refuses_everyone_when_no_secret_is_set(monkeypatch):
    monkeypatch.delenv("SYNC_SECRET", raising=False)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(feed.run_round(x_sync_secret=""))
    assert caught.value.status_code == 403


def test_feed_run_refuses_a_wrong_secret(monkeypatch):
    monkeypatch.setenv("SYNC_SECRET", "right")
    with pytest.raises(HTTPException) as caught:
        asyncio.run(feed.run_round(x_sync_secret="wrong"))
    assert caught.value.status_code == 403

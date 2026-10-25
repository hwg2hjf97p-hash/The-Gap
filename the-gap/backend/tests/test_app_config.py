import asyncio
import json

from routers import app_config


def test_ratings_and_invites_are_off_until_the_server_switches_them_on(monkeypatch):
    monkeypatch.delenv("ASK_FOR_RATINGS", raising=False)
    assert app_config.ask_for_ratings_enabled() is False
    monkeypatch.setenv("ASK_FOR_RATINGS", "true")
    assert app_config.ask_for_ratings_enabled() is True
    monkeypatch.setenv("ASK_FOR_RATINGS", "nope")
    assert app_config.ask_for_ratings_enabled() is False


def test_config_reports_both_switches_and_free_access_stays_off_by_default(monkeypatch):
    monkeypatch.delenv("FREE_ACCESS", raising=False)
    monkeypatch.delenv("ASK_FOR_RATINGS", raising=False)
    payload = json.loads(asyncio.run(app_config.get_config()).body)
    assert payload == {"free_access": False, "ask_for_ratings": False}

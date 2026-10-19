import pytest

from utils import provider_caps as pc


def test_whoop_and_oura_default_to_ten_and_other_services_have_no_limit(monkeypatch):
    for name in ("WHOOP_USER_CAP", "OURA_USER_CAP", "STRAVA_USER_CAP"):
        monkeypatch.delenv(name, raising=False)
    assert pc.cap_for("whoop") == 10 and pc.cap_for("oura") == 10
    assert pc.cap_for("strava") is None and pc.cap_for("withings") is None


def test_a_limit_can_be_raised_or_removed_from_the_environment(monkeypatch):
    monkeypatch.setenv("WHOOP_USER_CAP", "100")
    assert pc.cap_for("whoop") == 100
    monkeypatch.setenv("WHOOP_USER_CAP", "none")
    assert pc.cap_for("whoop") is None
    monkeypatch.setenv("WHOOP_USER_CAP", "0")
    assert pc.cap_for("whoop") is None
    monkeypatch.setenv("STRAVA_USER_CAP", "25")
    assert pc.cap_for("strava") == 25


def test_a_free_place_is_needed_unless_you_are_already_connected():
    connected = {f"u{i}" for i in range(10)}
    assert pc.has_room(10, connected, "new") is False
    assert pc.has_room(10, connected, "u3") is True      # reconnecting never needs a new place
    assert pc.has_room(11, connected, "new") is True
    assert pc.has_room(None, connected, "new") is True   # no limit


def test_full_means_full_only_for_people_not_already_in(monkeypatch):
    monkeypatch.setenv("WHOOP_USER_CAP", "2")

    async def fake(_provider):
        return {"a", "b"}

    monkeypatch.setattr(pc, "connected_users", fake)
    import asyncio

    assert asyncio.run(pc.is_full_for("c", "whoop")) is True
    assert asyncio.run(pc.is_full_for("a", "whoop")) is False
    assert asyncio.run(pc.is_full_for("c", "strava")) is False  # no limit set


def test_a_database_error_never_blocks_a_connection(monkeypatch):
    monkeypatch.setenv("WHOOP_USER_CAP", "2")

    async def broken(_provider):
        raise RuntimeError("database down")

    monkeypatch.setattr(pc, "connected_users", broken)
    import asyncio

    assert asyncio.run(pc.is_full_for("c", "whoop")) is False

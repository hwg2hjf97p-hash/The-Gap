import asyncio

import pytest
from fastapi import HTTPException

from routers import notifications
from utils import push


def test_every_gated_kind_sits_behind_a_known_switch():
    assert set(push.PUSH_KIND_SWITCH.values()) <= set(push.PUSH_SWITCHES)


def test_a_gated_notification_is_off_until_the_person_turns_it_on():
    # Nothing saved, or the table without the new column: everything is off.
    assert push.kind_allowed(None, "discovery") is False
    assert push.kind_allowed({"tz": "UTC"}, "discovery") is False
    assert push.kind_allowed({"push_kinds": None}, "digest") is False
    assert push.kind_allowed({"push_kinds": {"findings": False}}, "discovery") is False
    assert push.kind_allowed({"push_kinds": {"findings": True}}, "discovery") is True


def test_one_switch_covers_the_kinds_that_belong_to_it_and_no_others():
    on = {"push_kinds": {"findings": True}}
    assert push.kind_allowed(on, "proactive_nudge") is True
    assert push.kind_allowed(on, "digest") is False
    assert push.kind_allowed(on, "intervention_followup") is False
    assert push.kind_allowed({"push_kinds": {"connections": True}}, "connection_expired") is True


def test_a_test_notification_and_a_heads_up_are_not_held_back_by_these_switches():
    assert push.kind_allowed(None, "test") is True
    assert push.kind_allowed(None, "headsup") is True
    assert push.kind_allowed(None, None) is True


def test_a_switched_off_notification_is_not_sent_and_says_so(monkeypatch):
    async def prefs(user_id):
        return {"tz": "UTC", "quiet_start": 22, "quiet_end": 7, "push_kinds": {"findings": False}}

    async def tokens(user_id):
        raise AssertionError("must not even look for a phone")

    monkeypatch.setattr(push, "get_prefs", prefs)
    monkeypatch.setattr(push, "_get_tokens_for_user", tokens)
    out = asyncio.run(push.send_push_detailed("u1", "t", "b", {"kind": "discovery"}))
    assert out["off"] is True and out["accepted"] == 0 and out["held"] is False


def test_a_switched_on_notification_goes_on_to_find_the_phone(monkeypatch):
    looked = []

    async def prefs(user_id):
        return {"tz": "UTC", "quiet_start": 0, "quiet_end": 0, "push_kinds": {"recap": True}}

    async def tokens(user_id):
        looked.append(user_id)
        return []

    monkeypatch.setattr(push, "get_prefs", prefs)
    monkeypatch.setattr(push, "_get_tokens_for_user", tokens)
    out = asyncio.run(push.send_push_detailed("u1", "t", "b", {"kind": "digest"}))
    assert looked == ["u1"] and "off" not in out


def test_saving_one_switch_keeps_the_others_as_they_were():
    saved = {"findings": True, "recap": True}
    assert notifications.merged_kinds(saved, {"recap": False}) == {"findings": True, "recap": False, "followups": False, "connections": False}
    assert notifications.merged_kinds(None, {}) == {name: False for name in push.PUSH_SWITCHES}


def test_a_switch_that_does_not_exist_is_refused():
    with pytest.raises(HTTPException) as err:
        notifications.merged_kinds({}, {"findngs": True})
    assert err.value.status_code == 400 and "findngs" in err.value.detail

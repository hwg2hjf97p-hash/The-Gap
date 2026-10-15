from datetime import datetime, timedelta, timezone

from utils.insight_memory import GRACE_DAYS, stabilise

NOW = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)


def ins(hid, confidence="moderate", **extra):
    return {"hypothesis_id": hid, "confidence": confidence, "headline": f"about {hid}", **extra}


def ids(items, confirmed=None):
    return [i["hypothesis_id"] for i in items if confirmed is None or (i["confidence"] != "weak") == confirmed]


def test_a_new_confirmed_insight_is_stamped_with_when_it_arrived():
    out = stabilise([], None, [ins("a")], NOW)
    assert out[0]["first_confirmed_at"] == NOW.isoformat() and out[0]["last_confirmed_at"] == NOW.isoformat() and out[0]["carried"] is False


def test_an_insight_that_keeps_being_confirmed_keeps_its_first_date():
    first = (NOW - timedelta(days=3)).isoformat()
    previous = [ins("a", first_confirmed_at=first, last_confirmed_at=first)]
    out = stabilise(previous, first, [ins("a")], NOW)
    assert out[0]["first_confirmed_at"] == first and out[0]["last_confirmed_at"] == NOW.isoformat()


def test_a_confirmed_insight_that_drops_out_for_a_run_is_held_on_to():
    saved = (NOW - timedelta(hours=8)).isoformat()
    previous = [ins("a", last_confirmed_at=saved)]
    out = stabilise(previous, saved, [], NOW)
    assert ids(out) == ["a"] and out[0]["carried"] is True and out[0]["confidence"] == "moderate"


def test_it_is_held_on_to_when_the_engine_now_calls_it_an_early_signal():
    saved = (NOW - timedelta(hours=8)).isoformat()
    out = stabilise([ins("a", last_confirmed_at=saved)], saved, [ins("a", "weak")], NOW)
    assert len(out) == 1 and out[0]["confidence"] == "moderate" and out[0]["carried"] is True


def test_it_gives_way_once_it_has_not_been_confirmed_for_the_grace_period():
    old = (NOW - timedelta(days=GRACE_DAYS, minutes=1)).isoformat()
    out = stabilise([ins("a", last_confirmed_at=old)], old, [ins("a", "weak")], NOW)
    assert len(out) == 1 and out[0]["confidence"] == "weak"
    assert ids(stabilise([ins("a", last_confirmed_at=old)], old, [], NOW)) == []


def test_holding_on_does_not_extend_itself_forever():
    day0 = NOW - timedelta(days=GRACE_DAYS + 1)
    stamp = day0.isoformat()
    held = stabilise([ins("a", last_confirmed_at=stamp)], stamp, [], day0 + timedelta(days=3))
    again = stabilise(held, (day0 + timedelta(days=3)).isoformat(), [], NOW)
    assert ids(again) == []


def test_early_signals_are_not_remembered():
    out = stabilise([ins("w", "weak")], NOW.isoformat(), [], NOW)
    assert out == []


def test_an_old_result_without_dates_uses_when_it_was_saved():
    recent = (NOW - timedelta(days=1)).isoformat()
    assert ids(stabilise([ins("a")], recent, [], NOW)) == ["a"]
    stale = (NOW - timedelta(days=30)).isoformat()
    assert ids(stabilise([ins("a")], stale, [], NOW)) == []


def test_the_order_is_strongest_first():
    out = stabilise([], None, [ins("w", "weak"), ins("m", "moderate"), ins("s", "strong")], NOW)
    assert ids(out) == ["s", "m", "w"]


def test_the_discovery_check_sees_a_held_insight_as_already_known():
    saved = (NOW - timedelta(hours=8)).isoformat()
    first = stabilise([ins("a", last_confirmed_at=saved)], saved, [], NOW)
    # next run it is confirmed again: it was already in the confirmed list, so no new "discovery"
    previous_ids = {i["hypothesis_id"] for i in first if i["confidence"] != "weak"}
    assert "a" in previous_ids

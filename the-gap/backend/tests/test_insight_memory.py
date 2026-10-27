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


# ── the record of findings that were once confirmed ─────────────────────────────

from utils.insight_memory import MAX_PAST_FINDINGS, past_findings  # noqa: E402


def test_a_finding_is_held_for_two_weeks_before_it_gives_way():
    assert GRACE_DAYS == 14


def test_a_finding_whose_hold_ran_out_goes_into_the_record_with_its_dates():
    first, last = (NOW - timedelta(days=40)).isoformat(), (NOW - timedelta(days=15)).isoformat()
    previous = [ins("a", first_confirmed_at=first, last_confirmed_at=last, title="Steps & Recovery", carried=True)]
    shown = stabilise(previous, last, [ins("a", "weak")], NOW)  # past the hold: gives way to the early signal
    record = past_findings([], previous, shown, NOW)
    assert [p["hypothesis_id"] for p in record] == ["a"]
    assert record[0]["first_confirmed_at"] == first and record[0]["last_confirmed_at"] == last
    assert record[0]["lapsed_at"] == NOW.isoformat() and record[0]["title"] == "Steps & Recovery"


def test_a_finding_that_is_only_being_held_is_not_in_the_record():
    saved = (NOW - timedelta(days=3)).isoformat()
    previous = [ins("a", last_confirmed_at=saved)]
    shown = stabilise(previous, saved, [], NOW)  # held, still shown as confirmed
    assert past_findings([], previous, shown, NOW) == []


def test_a_finding_that_is_confirmed_again_comes_off_the_record():
    lapsed = {"hypothesis_id": "a", "lapsed_at": (NOW - timedelta(days=5)).isoformat()}
    assert past_findings([lapsed], [], [ins("a")], NOW) == []
    still_gone = past_findings([lapsed], [], [ins("a", "weak")], NOW)
    assert [p["hypothesis_id"] for p in still_gone] == ["a"] and still_gone[0]["lapsed_at"] == lapsed["lapsed_at"]


def test_early_signals_never_enter_the_record_and_it_has_a_limit():
    assert past_findings([], [ins("w", "weak")], [], NOW) == []
    many = [{"hypothesis_id": f"h{i}", "lapsed_at": (NOW - timedelta(days=i)).isoformat()} for i in range(MAX_PAST_FINDINGS + 5)]
    out = past_findings(many, [], [], NOW)
    assert len(out) == MAX_PAST_FINDINGS and out[0]["hypothesis_id"] == "h0"

from datetime import datetime, timedelta, timezone

from routers.sync_admin import summarise
from utils.movement import add_movement, score

NOW = datetime(2026, 10, 16, 9, 0, tzinfo=timezone.utc)


def ins(hid, conf="moderate", ate=5.0, p=0.02):
    return {"hypothesis_id": hid, "confidence": conf, "ate": ate, "p_value": p}


def test_a_finding_that_was_not_there_yesterday_is_new():
    assert score(ins("a"), None) == (100.0, "new")


def test_an_early_signal_that_became_confirmed_counts_as_new_and_a_tier_up_as_stronger():
    value, label = score(ins("a", "moderate"), ins("a", "weak"))
    assert label == "new" and value >= 80
    value, label = score(ins("a", "strong"), ins("a", "moderate"))
    assert label == "stronger" and value >= 80


def test_a_finding_that_got_weaker_has_moved_too():
    assert score(ins("a", "weak"), ins("a", "moderate"))[1] == "weaker"


def test_a_steady_finding_barely_moves_and_a_resized_one_moves_more():
    steady, label = score(ins("a", ate=5.0, p=0.02), ins("a", ate=5.05, p=0.021))
    assert label == "steady" and steady < 5
    moved, label = score(ins("a", ate=8.0, p=0.01), ins("a", ate=5.0, p=0.04))
    assert label == "shifted" and moved > steady


def test_the_biggest_change_ranks_highest():
    today = [ins("steady", ate=5.0), ins("brand_new"), ins("resized", ate=9.0)]
    yesterday = [ins("steady", ate=5.0), ins("resized", ate=5.0)]
    add_movement(today, yesterday)
    ranked = sorted(today, key=lambda i: -i["movement"])
    assert [i["hypothesis_id"] for i in ranked] == ["brand_new", "resized", "steady"]


def test_with_nothing_earlier_to_compare_nothing_has_moved():
    today = [ins("a"), ins("b")]
    add_movement(today, None)
    assert all(i["movement"] == 0.0 and i["movement_label"] == "" for i in today)


def test_an_early_signal_that_stays_early_is_not_news():
    today = [ins("a", "weak", ate=9.0)]
    add_movement(today, [ins("a", "weak", ate=2.0)])
    assert today[0]["movement"] == 0.0


# ── the sync status page ─────────────────────────────────────────────────────

def row(uid, next_in_minutes, fails=0, claimed_for=None, error=None, last_ok_ago=30):
    return {
        "user_id": uid,
        "next_sync_at": (NOW + timedelta(minutes=next_in_minutes)).isoformat(),
        "claimed_until": (NOW + timedelta(minutes=claimed_for)).isoformat() if claimed_for else None,
        "fail_count": fails,
        "last_error": error,
        "last_ok_at": (NOW - timedelta(minutes=last_ok_ago)).isoformat(),
    }


def test_the_status_counts_due_running_failing_and_overdue_people():
    rows = [row("aaaaaaaa1", 30), row("bbbbbbbb2", -5), row("cccccccc3", -3, claimed_for=8), row("dddddddd4", 20, fails=2, error="timed out"), row("eeeeeeee5", -200)]
    out = summarise(rows, set(), NOW)
    assert out["tracked"] == 5 and out["due_now"] == 2 and out["running"] == 1 and out["failing"] == 1 and out["overdue"] == 1
    who = {p["who"]: p for p in out["needs_a_look"]}
    assert set(who) == {"dddddddd", "eeeeeeee"} and who["dddddddd"]["last_error"] == "timed out" and who["eeeeeeee"]["state"] == "overdue"


def test_people_who_are_no_longer_connected_are_left_out():
    rows = [row("aaaaaaaa1", -200), row("bbbbbbbb2", -5)]
    out = summarise(rows, {"bbbbbbbb2"}, NOW)
    assert out["tracked"] == 1 and out["overdue"] == 0 and out["due_now"] == 1


def test_only_a_short_id_is_ever_shown():
    out = summarise([row("0123456789abcdef", -300)], set(), NOW)
    assert out["needs_a_look"][0]["who"] == "01234567"

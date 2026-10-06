from datetime import datetime, timezone

from utils import push
from utils import weekly_review as wr
from utils.quiet_hours import in_quiet_hours


def _utc(hour, minute=0, day=6):
    return datetime(2026, 10, day, hour, minute, tzinfo=timezone.utc)


def test_quiet_hours_that_run_past_midnight():
    # Brisbane is UTC+10: 15:00 UTC is 1 am there.
    assert in_quiet_hours(_utc(15), "Australia/Brisbane", 22, 7) is True
    # 06:00 UTC is 4 pm in Brisbane.
    assert in_quiet_hours(_utc(6), "Australia/Brisbane", 22, 7) is False
    # 21:30 UTC is 7:30 am in Brisbane: just after quiet hours end.
    assert in_quiet_hours(_utc(21, 30, day=5), "Australia/Brisbane", 22, 7) is False


def test_quiet_hours_within_a_single_day():
    assert in_quiet_hours(_utc(3), "Australia/Brisbane", 12, 14) is True  # 1 pm local
    assert in_quiet_hours(_utc(5), "Australia/Brisbane", 12, 14) is False  # 3 pm local


def test_quiet_hours_do_nothing_without_a_usable_time_zone():
    assert in_quiet_hours(_utc(15), None, 22, 7) is False
    assert in_quiet_hours(_utc(15), "Not/AZone", 22, 7) is False
    assert in_quiet_hours(_utc(15), "Australia/Brisbane", 8, 8) is False


def test_push_helper_follows_the_saved_preferences():
    now_quiet = {"tz": "UTC", "quiet_start": 0, "quiet_end": 24 - 0.01}
    # An empty or missing preference never holds anything back.
    assert push._quiet_now(None) is False
    assert push._quiet_now({}) is False
    assert isinstance(push._quiet_now(now_quiet), bool)


def _metrics(sleep_this, sleep_last, hrv_this=None, hrv_last=None, rhr_this=None, rhr_last=None):
    this_week = {"sleep_total_min": sleep_this}
    last_week = {"sleep_total_min": sleep_last}
    if hrv_this is not None:
        this_week["hrv"], last_week["hrv"] = hrv_this, hrv_last
    if rhr_this is not None:
        this_week["resting_hr"], last_week["resting_hr"] = rhr_this, rhr_last
    return this_week, last_week


def test_more_sleep_is_good_and_described_in_minutes():
    this_week, last_week = _metrics([450] * 5, [420] * 5)
    stats = wr.summarise_metrics(this_week, last_week)
    sleep = stats[0]
    assert sleep["good"] is True
    assert sleep["value"] == 7.5
    assert sleep["delta_text"] == "+30 min a night"


def test_a_higher_resting_heart_rate_is_a_slip():
    this_week, last_week = _metrics([420] * 4, [420] * 4, rhr_this=[60, 61, 62, 61], rhr_last=[56, 57, 56, 57])
    rhr = next(s for s in wr.summarise_metrics(this_week, last_week) if s["key"] == "resting_hr")
    assert rhr["good"] is False


def test_tiny_changes_are_called_the_same_and_few_days_are_skipped():
    this_week, last_week = _metrics([420, 424, 421], [421, 420, 422])
    assert wr.summarise_metrics(this_week, last_week)[0]["delta_text"] == "About the same"
    assert wr.summarise_metrics(this_week, last_week)[0]["good"] is None
    assert wr.summarise_metrics({"sleep_total_min": [420, 430]}, last_week) == []


def test_headline_reflects_what_moved():
    good = [{"good": True, "label": "Sleep"}, {"good": True, "label": "HRV"}]
    bad = [{"good": False, "label": "Steps"}]
    assert wr.headline(good) == "A good week: your sleep and hrv improved."
    assert wr.headline(bad) == "A tougher week: your steps slipped."
    assert "Mixed week" in wr.headline(good[:1] + bad)
    assert wr.headline([{"good": None, "label": "Sleep"}]) == "A steady week, with no big changes."


def test_focus_goes_to_the_first_rule_that_applies():
    stats_with_slip = [{"good": False, "label": "Sleep", "key": "sleep_total_min"}]
    assert "5 check-ins" in wr.choose_focus(stats_with_slip, {"checkins": 2})
    assert "meals" in wr.choose_focus([], {"checkins": 6, "food_days": 2})
    assert "planned 3 workouts and finished 1" in wr.choose_focus([], {"checkins": 6, "food_days": 7, "workouts_planned": 3, "workouts_done": 1})
    assert "sleep" in wr.choose_focus(stats_with_slip, {"checkins": 6, "food_days": 7}).lower()
    assert "Consistency" in wr.choose_focus([], {"checkins": 6, "food_days": 7})


def test_review_is_not_ready_without_data():
    payload = wr.build_review_payload({}, {}, {"checkins": 0}, 0, 0, 0, "2026-09-29", "2026-10-05")
    assert payload["ready"] is False
    assert "message" in payload


def test_review_with_data_has_everything_the_screen_needs():
    this_week, last_week = _metrics([450] * 6, [420] * 6, hrv_this=[60] * 5, hrv_last=[55] * 5)
    habits = {"checkins": 5, "workouts_done": 3, "workouts_planned": 3, "food_days": 6}
    payload = wr.build_review_payload(this_week, last_week, habits, 4, 2, 1, "2026-09-29", "2026-10-05")
    assert payload["ready"] is True
    assert payload["headline"].startswith("A good week")
    assert len(payload["highlights"]) <= 3
    assert payload["focus"]
    assert payload["streak"] == 4 and payload["confirmed_count"] == 2 and payload["early_count"] == 1


def test_metric_rows_split_into_this_week_and_the_one_before():
    rows = [
        {"date": "2026-10-03", "metric": "hrv", "value": 60},
        {"date": "2026-09-30", "metric": "hrv", "value": 62},
        {"date": "2026-09-25", "metric": "hrv", "value": 55},
        {"date": "2026-10-04", "metric": "hrv", "value": "not a number"},
    ]
    this_week, last_week = wr.split_by_week(rows, "2026-09-29", "2026-10-05")
    assert this_week == {"hrv": [60.0, 62.0]}
    assert last_week == {"hrv": [55.0]}

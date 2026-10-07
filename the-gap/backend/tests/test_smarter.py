import math
from datetime import date

import numpy as np
import pandas as pd

from routers import checkin
from routers.readiness import _latest_vs_baseline
from utils.snapshot import build_snapshot
from utils.source_merge import merge_sources
from utils.weekday_baseline import weekday_baseline


# ── same-weekday baseline ────────────────────────────────────────────────────

MONDAYS = [(date(2026, 9, 7), 6.5), (date(2026, 9, 14), 6.7), (date(2026, 9, 21), 6.4), (date(2026, 9, 28), 6.6)]


def test_a_monday_is_compared_with_other_mondays_only():
    sunday_lie_in = (date(2026, 10, 4), 8.7)
    base = weekday_baseline(MONDAYS + [sunday_lie_in], date(2026, 10, 5))
    assert base is not None
    assert base["weekday"] == "Monday"
    assert base["n"] == 4
    assert abs(base["mean"] - 6.55) < 1e-9


def test_too_few_same_weekday_readings_gives_no_baseline():
    assert weekday_baseline(MONDAYS[:3], date(2026, 10, 5)) is None


def test_old_and_future_readings_are_ignored():
    old = [(date(2026, 6, 1), 9.0), (date(2026, 6, 8), 9.0)]  # more than 8 weeks back
    future = [(date(2026, 10, 12), 1.0)]
    base = weekday_baseline(MONDAYS + old + future, date(2026, 10, 5))
    assert base["n"] == 4 and abs(base["mean"] - 6.55) < 1e-9


def _daily(values_by_weekday, start, periods):
    days = pd.date_range(start, periods=periods)
    return days, [values_by_weekday[d.weekday()] for d in days]


def test_readiness_baseline_uses_your_usual_for_that_day():
    # Sleep: Sundays long (520 min), Mondays short (390), other days 420.
    per_day = {0: 390.0, 6: 520.0, **{i: 420.0 for i in range(1, 6)}}
    days, values = _daily(per_day, "2026-08-10", 57)  # ends Monday 2026-10-05
    series = [(d.date(), v) for d, v in zip(days, values)]
    info = _latest_vs_baseline(series, date(2026, 10, 5))
    assert info is not None
    assert info["weekday"] == "Monday"
    assert abs(info["mean"] - 390.0) < 1.0  # a 6.5 hour Monday is normal for this person


def test_snapshot_calls_a_normal_monday_flat_not_a_drop():
    per_day = {0: 390.0, 6: 520.0, **{i: 420.0 for i in range(1, 6)}}
    days, values = _daily(per_day, "2026-07-27", 71)  # ends Monday 2026-10-05
    df = pd.DataFrame({"sleep_total_min": values}, index=days)
    card = next(c for c in build_snapshot(df)["latest"] if c["metric"] == "sleep_total_min")
    assert card["value"] == 6.5
    assert card["typical"]["weekday"] == "Monday"
    assert card["typical"]["delta"] == 0.0
    assert card["trend"] == "flat"
    assert card["date"] == "2026-10-05"


def test_snapshot_still_works_without_enough_history():
    days = pd.date_range("2026-10-01", periods=5)
    df = pd.DataFrame({"hrv": [50.0, 52.0, 51.0, 53.0, 49.0]}, index=days)
    card = next(c for c in build_snapshot(df)["latest"] if c["metric"] == "hrv")
    assert card["typical"] is None
    assert card["trend"] in ("up", "down", "flat")


# ── one main source per reading ──────────────────────────────────────────────

DAYS = pd.date_range("2026-10-01", periods=3)


def _frames():
    whoop = pd.DataFrame({"sleep_total_min": [400.0, 420.0, np.nan], "hrv": [50.0, 52.0, 54.0], "strain": [10.0, 12.0, 9.0]}, index=DAYS)
    apple = pd.DataFrame({"sleep_total_min": [480.0, 500.0, 510.0], "hrv": [40.0, 41.0, 42.0], "steps": [8000.0, 9000.0, 7000.0]}, index=DAYS)
    return {"whoop": whoop, "apple_health": apple}


def test_default_takes_sleep_from_whoop_and_steps_from_apple():
    merged = merge_sources(_frames(), None)
    assert merged["sleep_total_min"].iloc[0] == 400.0 and merged["sleep_total_min"].iloc[1] == 420.0
    assert merged["hrv"].tolist() == [50.0, 52.0, 54.0]
    assert merged["steps"].tolist() == [8000.0, 9000.0, 7000.0]
    assert merged["strain"].tolist() == [10.0, 12.0, 9.0]  # not a group reading: merged in order


def test_sleep_does_not_hop_between_sources_by_default():
    merged = merge_sources(_frames(), None)
    assert math.isnan(merged["sleep_total_min"].iloc[2])  # whoop has no third night; apple's is NOT mixed in


def test_gap_filling_can_be_switched_on():
    merged = merge_sources(_frames(), {"fill_gaps": {"sleep": True}})
    assert merged["sleep_total_min"].iloc[2] == 510.0


def test_the_persons_choice_wins():
    merged = merge_sources(_frames(), {"primary": {"sleep": "apple_health", "recovery": "apple_health"}})
    assert merged["sleep_total_min"].tolist() == [480.0, 500.0, 510.0]
    assert merged["hrv"].tolist() == [40.0, 41.0, 42.0]


def test_a_choice_that_is_not_connected_falls_back_to_the_default():
    merged = merge_sources(_frames(), {"primary": {"sleep": "oura"}})
    assert merged["sleep_total_min"].iloc[0] == 400.0


def test_a_source_with_no_data_for_a_reading_is_skipped():
    only_apple_steps = {"whoop": _frames()["whoop"], "apple_health": _frames()["apple_health"][["steps"]]}
    merged = merge_sources(only_apple_steps, None)
    assert merged["steps"].tolist() == [8000.0, 9000.0, 7000.0]
    assert merged["sleep_total_min"].iloc[0] == 400.0


def test_nothing_to_merge_gives_none():
    assert merge_sources({}, None) is None
    assert merge_sources({"whoop": pd.DataFrame()}, None) is None


# ── screen time in the check-in ──────────────────────────────────────────────

class _FakeResponse:
    def __init__(self, rows):
        self._rows = rows

    def raise_for_status(self):
        pass

    def json(self):
        return self._rows


def test_screen_time_becomes_engine_columns(monkeypatch):
    rows = [
        {"date": "2026-10-01", "alcohol": False, "afternoon_caffeine": False, "stress_score": 3, "screen_hours": 6, "screen_last_use": "after_1am"},
        {"date": "2026-10-02", "alcohol": False, "afternoon_caffeine": False, "stress_score": 3, "screen_hours": 2, "screen_last_use": "before_9pm"},
        {"date": "2026-10-03", "alcohol": False, "afternoon_caffeine": False, "stress_score": 3},
    ]
    monkeypatch.setattr(checkin.httpx, "get", lambda *a, **k: _FakeResponse(rows))
    df = checkin.get_checkin_dataframe("user-1")
    assert df.iloc[0]["screen_hours"] == 6 and df.iloc[0]["late_screen_flag"] == 1
    assert df.iloc[1]["screen_hours"] == 2 and df.iloc[1]["late_screen_flag"] == 0
    assert math.isnan(df.iloc[2]["late_screen_flag"])  # not answered: stays missing


def test_screen_last_use_ignores_unknown_choices():
    body = checkin.CheckInRequest(date="2026-10-02", screen_hours=4, screen_last_use="whenever")
    assert body.screen_last_use is None
    assert checkin.CheckInRequest(date="2026-10-02", screen_last_use="11pm_1am").screen_last_use == "11pm_1am"


# ── a column that isn't in the table yet must not lose the rest ─────────────

def test_a_missing_column_only_drops_that_field(monkeypatch):
    import asyncio
    import json as jsonlib

    posted = []

    class _Resp:
        def __init__(self, status=200, text="", rows=None):
            self.status_code, self.text, self._rows = status, text, rows or []

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError("http error")

        def json(self):
            return self._rows

    class _Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, params=None, json=None):
            posted.append(dict(json))
            if "screen_hours" in json:
                return _Resp(400, "PGRST204 Could not find the 'screen_hours' column of 'daily_checkins' in the schema cache")
            return _Resp(201)

        async def get(self, *args, **kwargs):
            return _Resp(200, rows=[])

    monkeypatch.setattr(checkin.httpx, "AsyncClient", lambda **kw: _Client())
    body = checkin.CheckInRequest(date="2026-10-02", alcohol_drinks=6, screen_hours=4)
    response = asyncio.run(checkin.submit_checkin(body, user_id="user-1"))
    data = jsonlib.loads(response.body)

    assert data["success"] is True and data["extended_saved"] is False
    assert "screen_hours" in posted[0]
    assert "screen_hours" not in posted[1]
    assert posted[1]["alcohol_drinks"] == 6  # the other new fields were still saved

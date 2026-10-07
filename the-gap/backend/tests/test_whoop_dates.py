import asyncio

from sync import whoop_sync

AU = "+10:00"


def _records(sleep_start, sleep_end, cycle_start, cycle_end, steps=10800, tz=AU):
    sleep = {
        "id": "sleep-1", "start": sleep_start, "end": sleep_end, "timezone_offset": tz, "nap": False, "score_state": "SCORED",
        "score": {"stage_summary": {"total_light_sleep_time_milli": 3 * 3600000, "total_slow_wave_sleep_time_milli": 1 * 3600000, "total_rem_sleep_time_milli": 2 * 3600000}, "sleep_performance_percentage": 90},
    }
    recovery = {
        "cycle_id": 7, "sleep_id": "sleep-1", "created_at": sleep_end, "score_state": "SCORED",
        "score": {"recovery_score": 70, "resting_heart_rate": 52, "hrv_rmssd_milli": 61},
    }
    cycle = {
        "id": 7, "start": cycle_start, "end": cycle_end, "timezone_offset": tz, "score_state": "SCORED", "step_count": steps,
        "score": {"strain": 12.5, "kilojoule": 10000},
    }
    return {"recovery": [recovery], "activity/sleep": [sleep], "cycle": [cycle]}


def _fetch(monkeypatch, records):
    class _Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    async def paginated(client, endpoint, headers, start, max_pages=20):
        return records.get(endpoint, [])

    monkeypatch.setattr(whoop_sync.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(whoop_sync, "_get_whoop_paginated", paginated)
    return asyncio.run(whoop_sync.fetch_whoop_data("token"))


def test_a_queensland_night_lands_on_the_right_local_days(monkeypatch):
    # Slept 10:30 pm Wed 7 Oct to 6:30 am Thu 8 Oct local (UTC+10); cycle ran to 11 pm Thu.
    df = _fetch(monkeypatch, _records("2026-10-07T12:30:00.000Z", "2026-10-07T20:30:00.000Z", "2026-10-07T12:30:00.000Z", "2026-10-08T13:00:00.000Z"))
    assert "2026-10-07" in df.index.strftime("%Y-%m-%d")
    by_day = {d.strftime("%Y-%m-%d"): row for d, row in df.iterrows()}
    assert by_day["2026-10-07"]["sleep_total_min"] == 360          # the night is filed under the evening it began
    assert by_day["2026-10-08"]["hrv"] == 61                        # the morning's recovery is filed under the morning
    assert by_day["2026-10-08"]["resting_hr"] == 52
    assert by_day["2026-10-08"]["steps"] == 10800                   # the day's steps and strain on the day they happened
    assert by_day["2026-10-08"]["strain"] == 12.5
    assert abs(by_day["2026-10-08"]["active_energy"] - 10000 * 0.239) < 1e-6
    assert "hrv" not in by_day["2026-10-07"] or by_day["2026-10-07"]["hrv"] != by_day["2026-10-07"]["hrv"]


def test_an_after_midnight_sleeper_keeps_their_own_date(monkeypatch):
    # Asleep 1:30 am Thu 8 Oct local = 15:30 UTC on Wed 7 Oct. UTC dating put this night a day early.
    df = _fetch(monkeypatch, _records("2026-10-07T15:30:00.000Z", "2026-10-07T23:30:00.000Z", "2026-10-07T15:30:00.000Z", "2026-10-08T16:00:00.000Z"))
    by_day = {d.strftime("%Y-%m-%d"): row for d, row in df.iterrows()}
    assert by_day["2026-10-08"]["sleep_total_min"] == 360
    assert by_day["2026-10-08"]["steps"] == 10800                   # cycle midpoint is early afternoon on Thursday
    assert by_day["2026-10-08"]["hrv"] == 61                        # woke 9:30 am Thursday


def test_a_western_timezone_is_unchanged(monkeypatch):
    # US Eastern (UTC-4 in October): asleep 11 pm Wed, up 7 am Thu.
    df = _fetch(monkeypatch, _records("2026-10-08T03:00:00.000Z", "2026-10-08T11:00:00.000Z", "2026-10-08T03:00:00.000Z", "2026-10-09T03:00:00.000Z", tz="-04:00"))
    by_day = {d.strftime("%Y-%m-%d"): row for d, row in df.iterrows()}
    assert by_day["2026-10-07"]["sleep_total_min"] == 360
    assert by_day["2026-10-08"]["hrv"] == 61 and by_day["2026-10-08"]["steps"] == 10800


def test_no_step_data_means_no_steps_column_value(monkeypatch):
    for steps in (None, 0):
        df = _fetch(monkeypatch, _records("2026-10-07T12:30:00.000Z", "2026-10-07T20:30:00.000Z", "2026-10-07T12:30:00.000Z", "2026-10-08T13:00:00.000Z", steps=steps))
        assert "steps" not in df.columns or df["steps"].isna().all()


def test_the_current_unfinished_cycle_still_gets_a_date(monkeypatch):
    records = _records("2026-10-07T12:30:00.000Z", "2026-10-07T20:30:00.000Z", "2026-10-07T12:30:00.000Z", None)
    df = _fetch(monkeypatch, records)
    by_day = {d.strftime("%Y-%m-%d"): row for d, row in df.iterrows()}
    assert by_day["2026-10-08"]["steps"] == 10800


def test_timezone_helpers():
    assert whoop_sync._offset("+10:00").total_seconds() == 36000
    assert whoop_sync._offset("-05:30").total_seconds() == -19800
    assert whoop_sync._offset("Z").total_seconds() == 0 and whoop_sync._offset(None).total_seconds() == 0
    assert whoop_sync._local_date("2026-10-07T15:30:00.000Z", "+10:00") == "2026-10-08"
    assert whoop_sync._local_date("garbage", "+10:00") == ""

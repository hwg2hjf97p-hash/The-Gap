import asyncio

import pandas as pd

from sync import recent_refresh as rr

TODAY = pd.Timestamp("2026-10-19")


def frame(rows: dict) -> pd.DataFrame:
    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index = pd.to_datetime(df.index)
    df.index.name = "date"
    return df.sort_index()


def run(coro):
    return asyncio.run(coro)


def test_fresh_days_replace_saved_ones_and_old_days_are_kept():
    old = frame({"2026-10-01": {"hrv": 50.0}, "2026-10-08": {"hrv": 60.0}, "2026-10-15": {"hrv": 70.0}})
    fresh = frame({"2026-10-10": {"hrv": 61.0}, "2026-10-15": {"hrv": 72.0}, "2026-10-19": {"hrv": 80.0}})
    out = rr.overlay_recent(old, fresh, TODAY)  # cut-off is 9 Oct: older days stay, newer come from the fresh read
    assert out.loc["2026-10-01", "hrv"] == 50.0 and out.loc["2026-10-08", "hrv"] == 60.0
    assert out.loc["2026-10-15", "hrv"] == 72.0 and out.loc["2026-10-19", "hrv"] == 80.0
    assert out.loc["2026-10-10", "hrv"] == 61.0
    assert list(out.index) == sorted(out.index)


def test_a_day_that_vanished_from_the_fresh_read_is_not_kept_stale():
    old = frame({"2026-10-12": {"hrv": 70.0, "recovery_score": 40.0}})
    fresh = frame({"2026-10-12": {"hrv": 71.0}})
    out = rr.overlay_recent(old, fresh, TODAY)
    assert out.loc["2026-10-12", "hrv"] == 71.0


def test_an_empty_fresh_read_leaves_the_saved_data_alone():
    old = frame({"2026-10-12": {"hrv": 70.0}})
    assert rr.overlay_recent(old, pd.DataFrame(), TODAY).equals(old)


def test_the_full_read_happens_once_then_only_recent_reads(monkeypatch):
    rr._saved.clear()
    calls = []

    async def fetch(token, days_back):
        calls.append(days_back)
        today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
        return frame({str((today - pd.Timedelta(days=d)).date()): {"hrv": float(d)} for d in range(min(days_back, 20))})

    first = run(rr.fetch_recent_first("u1", "whoop", "tok", fetch, now=1000.0))
    second = run(rr.fetch_recent_first("u1", "whoop", "tok", fetch, now=1000.0 + 3600))
    assert calls == [rr.FULL_DAYS, rr.RECENT_DAYS]
    assert len(second) >= len(first) - 1


def test_the_saved_copy_expires_after_a_day_and_is_per_person(monkeypatch):
    rr._saved.clear()
    calls = []

    async def fetch(token, days_back):
        calls.append((token, days_back))
        return frame({"2026-10-18": {"hrv": 1.0}})

    run(rr.fetch_recent_first("u1", "whoop", "a", fetch, now=0.0))
    run(rr.fetch_recent_first("u2", "whoop", "b", fetch, now=10.0))                 # another person: their own full read
    run(rr.fetch_recent_first("u1", "whoop", "a", fetch, now=rr.FULL_REFRESH_SECONDS + 1))  # a day later: full read again
    assert [d for _, d in calls] == [rr.FULL_DAYS, rr.FULL_DAYS, rr.FULL_DAYS]

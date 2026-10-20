import asyncio
import math
from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from routers import checkin, journal


class _Resp:
    def __init__(self, rows=None, status=200, text=""):
        self._rows, self.status_code, self.text = rows if rows is not None else [], status, text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")

    def json(self):
        return self._rows


# ── the coffee count ─────────────────────────────────────────────────────────

def test_the_coffee_count_is_accepted_between_zero_and_thirty():
    assert checkin.CheckInRequest(date="2026-10-09", caffeine_drinks=5).caffeine_drinks == 5
    assert checkin.CheckInRequest(date="2026-10-09", caffeine_drinks=0).caffeine_drinks == 0
    assert checkin.CheckInRequest(date="2026-10-09").caffeine_drinks is None
    with pytest.raises(ValidationError):
        checkin.CheckInRequest(date="2026-10-09", caffeine_drinks=31)


def _frame(monkeypatch, rows):
    monkeypatch.setattr(checkin.httpx, "get", lambda *a, **k: _Resp(rows))
    return checkin.get_checkin_dataframe("u1")


def test_five_coffees_before_2pm_is_a_heavy_caffeine_day_the_afternoon_question_cannot_see(monkeypatch):
    df = _frame(
        monkeypatch,
        [
            {"date": "2026-10-01", "alcohol": False, "afternoon_caffeine": False, "caffeine_drinks": 5, "stress_score": 3},
            {"date": "2026-10-02", "alcohol": False, "afternoon_caffeine": False, "caffeine_drinks": 1, "stress_score": 3},
            {"date": "2026-10-03", "alcohol": False, "afternoon_caffeine": True, "stress_score": 3},
        ],
    )
    heavy, light, unanswered = df.iloc[0], df.iloc[1], df.iloc[2]
    assert heavy["afternoon_caffeine"] == 0 and heavy["caffeine_drinks"] == 5 and heavy["high_caffeine_flag"] == 1
    assert light["caffeine_drinks"] == 1 and light["high_caffeine_flag"] == 0
    assert math.isnan(unanswered["caffeine_drinks"]) and math.isnan(unanswered["high_caffeine_flag"])


def test_a_day_logged_only_by_voice_leaves_the_other_questions_unanswered(monkeypatch):
    df = _frame(
        monkeypatch,
        [
            {"date": "2026-10-01", "alcohol": None, "afternoon_caffeine": None, "cigarettes": 3, "caffeine_drinks": 2, "partial": True, "stress_score": None},
            {"date": "2026-10-02", "alcohol": False, "afternoon_caffeine": False, "cigarettes": 0, "stress_score": 4},
        ],
    )
    voice, full = df.iloc[0], df.iloc[1]
    assert math.isnan(voice["alcohol_flag"]) and math.isnan(voice["afternoon_caffeine"]) and math.isnan(voice["alcohol_drinks"])
    assert voice["cigarettes"] == 3 and voice["caffeine_drinks"] == 2
    assert full["alcohol_flag"] == 0 and full["afternoon_caffeine"] == 0 and full["alcohol_drinks"] == 0


def test_a_voice_beer_counts_as_an_answered_yes(monkeypatch):
    df = _frame(monkeypatch, [{"date": "2026-10-01", "alcohol": True, "alcohol_drinks": 2, "afternoon_caffeine": None, "partial": True}])
    assert df.iloc[0]["alcohol_flag"] == 1 and df.iloc[0]["alcohol_drinks"] == 2


# ── a full check-in replaces a partial one; a partial one isn't a check-in ───

def _post_env(monkeypatch, fail_on=()):
    posted = []

    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, params=None, json=None):
            for col in fail_on:
                if col in json:
                    return _Resp(status=400, text=f"PGRST204 Could not find the '{col}' column of 'daily_checkins'")
            posted.append(dict(json))
            return _Resp(status=201)

    async def streak(user_id, local_date=None):
        return 1

    monkeypatch.setattr(checkin.httpx, "AsyncClient", lambda **kw: _Client())
    monkeypatch.setattr(checkin, "_get_streak", streak)
    return posted


def test_saving_the_full_check_in_clears_the_partial_mark_and_saves_the_coffee_count(monkeypatch):
    posted = _post_env(monkeypatch)
    asyncio.run(checkin.submit_checkin(checkin.CheckInRequest(date="2026-10-09", caffeine_drinks=4), user_id="u1"))
    assert posted[0]["partial"] is False and posted[0]["caffeine_drinks"] == 4


def test_a_database_without_the_new_columns_still_saves_the_rest(monkeypatch):
    posted = _post_env(monkeypatch, fail_on=("partial", "caffeine_drinks"))
    response = asyncio.run(checkin.submit_checkin(checkin.CheckInRequest(date="2026-10-09", caffeine_drinks=4, cigarettes=2), user_id="u1"))
    assert response.status_code == 200
    assert "partial" not in posted[0] and "caffeine_drinks" not in posted[0] and posted[0]["cigarettes"] == 2


def test_the_streak_does_not_count_a_day_that_only_has_a_voice_log(monkeypatch):
    today = date.today()
    rows = [
        {"date": today.isoformat(), "partial": True},
        {"date": (today - timedelta(days=1)).isoformat(), "partial": False},
        {"date": (today - timedelta(days=2)).isoformat()},
    ]

    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None, params=None):
            return _Resp(rows)

    monkeypatch.setattr(checkin.httpx, "AsyncClient", lambda **kw: _Client())
    assert asyncio.run(checkin._get_streak("u1", today.isoformat())) == 2


# ── Quick Entry: exact time, and a day is summarised again when its entries change ──

def test_the_clock_time_leads_the_text_where_the_person_was():
    row = {"entry_text": "boss yelled at me", "occurred_at": "2026-10-09T04:15:00+00:00", "tz": "Australia/Brisbane"}
    assert journal.with_clock_time(row) == "[2:15 pm] boss yelled at me"
    assert journal.with_clock_time({"entry_text": "old entry"}) == "old entry"
    assert journal.with_clock_time({"entry_text": "x", "occurred_at": "garbage", "tz": "Nope/Nope"}) == "x"


def test_a_cached_day_is_summarised_again_when_a_new_entry_was_added(monkeypatch):
    day = (datetime.now(timezone.utc) - timedelta(days=2)).date().isoformat()   # a past day: the old rule never revisited it
    rows = [
        {"entry_text": "slept badly", "created_at": f"{day}T01:00:00Z", "local_date": day, "occurred_at": None, "tz": None},
        {"entry_text": "argued with my boss", "created_at": f"{day}T05:00:00Z", "local_date": day, "occurred_at": f"{day}T05:00:00+00:00", "tz": "Australia/Brisbane"},
    ]
    extracted = []

    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None, params=None):
            return _Resp(rows)

    async def cached(user_id, since):
        return {day: {"entry_count": 1, "mood_score": 0, "stress_event": 0, "travel_event": 0, "illness_event": 0, "conflict_event": 0, "big_win_event": 0}}

    async def extract(entries):
        extracted.append(entries)
        return {"mood_score": -0.5, "stress_event": 1, "travel_event": 0, "illness_event": 0, "conflict_event": 1, "big_win_event": 0, "summary": "x"}

    async def save(*a, **k):
        return None

    async def allowed(user_id):
        return True

    monkeypatch.setattr(journal.httpx, "AsyncClient", lambda **kw: _Client())
    monkeypatch.setattr(journal, "_get_cached_extractions", cached)
    monkeypatch.setattr(journal, "extract_daily_signals", extract)
    monkeypatch.setattr(journal, "_save_extraction", save)
    monkeypatch.setattr(journal, "ai_allowed", allowed)
    df = asyncio.run(journal.get_journal_dataframe("u1"))
    assert extracted == [["slept badly", "[3:00 pm] argued with my boss"]]
    assert df.iloc[0]["conflict_event"] == 1


def test_a_cached_day_with_the_same_number_of_entries_is_not_summarised_again(monkeypatch):
    day = (datetime.now(timezone.utc) - timedelta(days=2)).date().isoformat()
    rows = [{"entry_text": "slept badly", "created_at": f"{day}T01:00:00Z", "local_date": day, "occurred_at": None, "tz": None}]
    extracted = []

    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None, params=None):
            return _Resp(rows)

    async def cached(user_id, since):
        return {day: {"entry_count": 1, "mood_score": -0.2, "stress_event": 0, "travel_event": 0, "illness_event": 0, "conflict_event": 0, "big_win_event": 0}}

    async def extract(entries):
        extracted.append(entries)
        return None

    async def allowed(user_id):
        return True

    monkeypatch.setattr(journal.httpx, "AsyncClient", lambda **kw: _Client())
    monkeypatch.setattr(journal, "_get_cached_extractions", cached)
    monkeypatch.setattr(journal, "extract_daily_signals", extract)
    monkeypatch.setattr(journal, "ai_allowed", allowed)
    df = asyncio.run(journal.get_journal_dataframe("u1"))
    assert extracted == [] and df.iloc[0]["mood_score"] == -0.2


def test_todays_notes_are_only_read_again_when_they_have_changed():
    same = {"entry_count": 2}
    assert journal.needs_reading(["a", "b"], same) is False   # nothing new: reuse the saved reading, even for today
    assert journal.needs_reading(["a", "b", "c"], same) is True  # a new note was logged
    assert journal.needs_reading(["a"], None) is True         # never read before

import asyncio
from datetime import datetime, timezone

import pytest

from routers import log as log_module

BRISBANE = "Australia/Brisbane"


def at(local_hour: int, local_minute: int = 0) -> datetime:
    """A moment that is local_hour:local_minute in Brisbane (UTC+10) on 9 Oct 2026."""
    total = local_hour * 60 + local_minute - 600
    day = 9
    if total < 0:
        total += 24 * 60
        day = 8
    return datetime(2026, 10, day, total // 60, total % 60, tzinfo=timezone.utc)


class _Resp:
    def __init__(self, status=200, rows=None, text=""):
        self.status_code, self._rows, self.text = status, rows if rows is not None else [], text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self._rows


class FakeDB:
    def __init__(self, checkin=None, water=None, foods=None, meals=None, fail_columns=()):
        self.checkin, self.water, self.foods, self.meals = checkin, list(water or []), foods or [], meals or []
        self.fail_columns = fail_columns
        self.posts, self.patches = [], []

    def posted(self, table):
        return [p for t, p in self.posts if t == table]


def install(monkeypatch, db: FakeDB, weights=None):
    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None, params=None):
            table = url.rsplit("/", 1)[-1]
            rows = {"daily_checkins": [db.checkin] if db.checkin else [], "water_log": db.water, "saved_foods": db.foods, "saved_meals": db.meals}.get(table, [])
            return _Resp(200, rows)

        async def post(self, url, headers=None, params=None, json=None):
            table = url.rsplit("/", 1)[-1]
            if table == "daily_checkins":
                for col in db.fail_columns:
                    if col in json:
                        return _Resp(400, text=f"PGRST204 Could not find the '{col}' column of 'daily_checkins'")
            if table == "food_log" and isinstance(json, list):
                db.posts.extend((table, row) for row in json)
            else:
                db.posts.append((table, json))
            if table == "water_log":
                db.water.append(json)
            return _Resp(201, json if isinstance(json, list) else [json])

        async def patch(self, url, headers=None, params=None, json=None):
            db.patches.append((url.rsplit("/", 1)[-1], json))
            return _Resp(200)

    async def count_today(user_id, day):
        return 1

    async def streak(user_id, day):
        return 1

    async def save_weight(user_id, day, kg):
        weights.append((user_id, day, kg)) if weights is not None else None

    monkeypatch.setattr(log_module.httpx, "AsyncClient", lambda **kw: _Client())
    monkeypatch.setattr(log_module, "_count_today", count_today)
    monkeypatch.setattr(log_module, "_get_streak", streak)
    monkeypatch.setattr(log_module, "save_weight", save_weight)


def run(text, when=None, source="siri"):
    return asyncio.run(log_module.process_log_text("u1", text, None, when or at(12), BRISBANE, source))


# ── check-in counts ──────────────────────────────────────────────────────────

def test_a_cigarette_on_a_day_with_no_check_in_starts_a_partial_one_that_answers_nothing_else(monkeypatch):
    db = FakeDB()
    install(monkeypatch, db)
    result = run("just had a cigarette")
    assert [i["kind"] for i in result["logged"]] == ["cigarettes"]
    assert db.posted("daily_checkins") == [{"user_id": "u1", "date": "2026-10-09", "cigarettes": 1, "partial": True, "alcohol": None, "afternoon_caffeine": None}]
    assert result["spoken"] == "Logged 1 cigarette, 1 today."


def test_a_cigarette_adds_to_an_existing_check_in_without_touching_the_rest(monkeypatch):
    db = FakeDB(checkin={"user_id": "u1", "date": "2026-10-09", "cigarettes": 2, "alcohol": False, "partial": False})
    install(monkeypatch, db)
    result = run("had a cigarette")
    assert db.posted("daily_checkins") == [{"user_id": "u1", "date": "2026-10-09", "cigarettes": 3}]
    assert "3 today" in result["spoken"]


def test_a_coffee_in_the_afternoon_also_marks_afternoon_caffeine(monkeypatch):
    db = FakeDB()
    install(monkeypatch, db)
    run("just had a coffee", at(15, 30))
    payload = db.posted("daily_checkins")[0]
    assert payload["caffeine_drinks"] == 1 and payload["afternoon_caffeine"] is True


def test_a_morning_coffee_counts_but_does_not_claim_afternoon_caffeine(monkeypatch):
    db = FakeDB()
    install(monkeypatch, db)
    run("five coffees this morning", at(9))
    payload = db.posted("daily_checkins")[0]
    assert payload["caffeine_drinks"] == 5 and payload["afternoon_caffeine"] is None


def test_a_beer_in_the_evening_sets_the_alcohol_fields(monkeypatch):
    db = FakeDB()
    install(monkeypatch, db)
    run("had a beer", at(21))
    payload = db.posted("daily_checkins")[0]
    assert payload["alcohol"] is True and payload["alcohol_drinks"] == 1 and payload["alcohol_time"] == "evening"


def test_a_second_beer_keeps_the_time_of_the_first(monkeypatch):
    db = FakeDB(checkin={"alcohol_drinks": 1, "alcohol_time": "afternoon", "partial": True})
    install(monkeypatch, db)
    run("another beer", at(21))
    payload = db.posted("daily_checkins")[0]
    assert payload["alcohol_drinks"] == 2 and "alcohol_time" not in payload


def test_a_missing_column_loses_that_count_but_never_the_note(monkeypatch):
    db = FakeDB(fail_columns=("caffeine_drinks",))
    install(monkeypatch, db)
    result = run("had a coffee")
    assert result["logged"] == [] and result["spoken"] == "Saved to your journal."
    assert len(db.posted("quick_entries")) == 1


# ── water, weight ────────────────────────────────────────────────────────────

def test_water_is_logged_with_the_time_and_the_day_total_is_said(monkeypatch):
    db = FakeDB(water=[{"amount_ml": 500}])
    install(monkeypatch, db)
    result = run("just drank 300ml of water", at(12))
    assert db.posted("water_log") == [{"user_id": "u1", "local_date": "2026-10-09", "amount_ml": 300, "local_hour": 12.0}]
    assert "800 ml today" in result["spoken"]


def test_weight_is_saved_for_the_local_day(monkeypatch):
    weights = []
    install(monkeypatch, FakeDB(), weights)
    result = run("I weigh 72.4 kg")
    assert weights == [("u1", "2026-10-09", 72.4)] and "72.4" in result["spoken"]


# ── saved foods and meals ────────────────────────────────────────────────────

PROTEIN = {"id": "f1", "name": "Protein drink", "aliases": [], "calories": 150, "protein_g": 25, "carbs_g": 5, "fat_g": 2, "default_servings": 1, "serving_label": "1 bottle", "serving_grams": None, "brand": None, "use_count": 2}
BREKKY = {"id": "m1", "name": "Brekky", "aliases": [], "meal": "breakfast", "use_count": 5, "items": [
    {"food_name": "Egg", "servings": 2, "serving_label": "1 egg", "per_serving": {"calories": 70, "protein_g": 6, "carbs_g": 0.5, "fat_g": 5}},
    {"food_name": "Toast", "servings": 1, "serving_label": "1 slice", "per_serving": {"calories": 80, "protein_g": 3, "carbs_g": 15, "fat_g": 1}},
]}


def test_my_regular_protein_drink_is_logged_to_nutrition_at_that_time(monkeypatch):
    db = FakeDB(foods=[PROTEIN])
    install(monkeypatch, db)
    result = run("just drank my regular protein drink", at(8, 15))
    [row] = db.posted("food_log")
    assert row["food_name"] == "Protein drink" and row["calories"] == 150 and row["servings"] == 1
    assert row["local_hour"] == 8.25 and row["meal"] == "breakfast" and row["local_date"] == "2026-10-09"
    assert db.patches == [("saved_foods", {"use_count": 3, "last_used": db.patches[0][1]["last_used"]})]
    assert result["spoken"] == "Logged your Protein drink."
    assert result["logged"][0]["summary"] == "Protein drink (150 kcal)"


def test_two_servings_doubles_the_numbers(monkeypatch):
    db = FakeDB(foods=[PROTEIN])
    install(monkeypatch, db)
    run("had two protein drinks", at(8))
    assert db.posted("food_log")[0]["calories"] == 300 and db.posted("food_log")[0]["servings"] == 2


def test_a_saved_meal_logs_every_item_in_it(monkeypatch):
    db = FakeDB(meals=[BREKKY])
    install(monkeypatch, db)
    result = run("had my usual brekky", at(7, 30))
    rows = db.posted("food_log")
    assert [r["food_name"] for r in rows] == ["Egg", "Toast"]
    assert rows[0]["servings"] == 2 and rows[0]["calories"] == 140 and rows[1]["calories"] == 80
    assert all(r["local_hour"] == 7.5 and r["meal"] == "breakfast" for r in rows)
    assert result["logged"][0]["summary"] == "Brekky (220 kcal)"


def test_a_food_nobody_saved_is_kept_as_a_note_to_finish_in_the_app(monkeypatch):
    db = FakeDB()
    install(monkeypatch, db)
    result = run("had a banana")
    assert result["logged"] == [] and result["food_note"] is True
    assert db.posted("food_log") == [] and db.posted("daily_checkins") == []
    note = db.posted("quick_entries")[0]
    assert note["entry_text"] == "had a banana" and note["food_note"] is True
    assert "kept it as a note" in result["spoken"]


# ── the note, and the time ───────────────────────────────────────────────────

def test_every_sentence_is_kept_as_a_note_with_its_exact_time_and_source(monkeypatch):
    db = FakeDB()
    install(monkeypatch, db)
    result = run("boss just yelled at me", at(14, 20), source="siri")
    note = db.posted("quick_entries")[0]
    assert note["entry_text"] == "boss just yelled at me" and note["source"] == "siri" and note["tz"] == BRISBANE
    assert note["occurred_at"].startswith("2026-10-09T04:20:00") and note["local_date"] == "2026-10-09"
    assert note["routed_to"] is None and note["food_note"] is False
    assert result["logged"] == [] and result["spoken"] == "Saved to your journal."


def test_what_was_logged_is_recorded_on_the_note(monkeypatch):
    db = FakeDB()
    install(monkeypatch, db)
    run("just had a cigarette")
    note = db.posted("quick_entries")[0]
    assert note["routed_to"] == [{"kind": "cigarettes", "summary": "1 cigarette (1 today)"}]


def test_a_late_night_entry_is_filed_under_the_local_day_not_the_utc_day(monkeypatch):
    db = FakeDB()
    install(monkeypatch, db)
    run("had a beer", at(1, 30))                      # 1:30 am Brisbane on the 9th is still the 8th in UTC
    assert db.posted("daily_checkins")[0]["date"] == "2026-10-09"


def test_the_clock_uses_the_given_zone_then_falls_back():
    moment = datetime(2026, 10, 9, 4, 20, tzinfo=timezone.utc)
    _, local, zone = log_module.local_clock(moment, "America/New_York")
    assert zone == "America/New_York" and local.hour == 0
    _, local, zone = log_module.local_clock(moment, "Not/AZone")
    assert zone == BRISBANE and local.hour == 14
    _, local, _ = log_module.local_clock(datetime(2026, 10, 9, 4, 20), BRISBANE)   # no zone given: taken as UTC
    assert local.hour == 14 and log_module.hour_of(local) == 14.33


def test_empty_text_is_refused():
    with pytest.raises(Exception):
        asyncio.run(log_module.log_text(log_module.LogTextBody(text="   "), user_id="u1"))

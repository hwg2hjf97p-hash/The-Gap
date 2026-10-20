from datetime import date, datetime, timedelta, timezone

import pandas as pd

from utils import headsups as hu

DAY = date(2026, 10, 15)


def build(**kw):
    args = dict(today={}, usual={}, hour=15.0, day=DAY, user_key="u1", nutrition={}, nutrition_goals={}, insights=[], goal_cols=set())
    args.update(kw)
    return hu.build_headsups(**args)


def kinds(items):
    return [i["kind"] for i in items]


def test_a_big_step_day_says_how_far_over_the_persons_usual_it_is():
    items = build(today={"steps": 16000}, usual={"steps": 10000})
    assert kinds(items) == ["steps_high"]
    body = items[0]["body"]
    assert "16,000" in body and "60%" in body and "10,000" in body and items[0]["push"] is True


def test_an_ordinary_busy_day_is_not_a_heads_up():
    assert build(today={"steps": 11000}, usual={"steps": 10000}) == []
    assert build(today={"steps": 5000}, usual={"steps": 3000}) == []  # under 6,000 is never "big"


def test_it_waits_until_mid_morning_before_judging_the_steps():
    assert build(today={"steps": 16000}, usual={"steps": 10000}, hour=8.0) == []


def test_it_needs_the_persons_usual_to_say_anything():
    assert build(today={"steps": 16000}, usual={}) == []


def step_insight(ate, confidence="moderate", **extra):
    return {"hypothesis_id": "steps_hrv", "treatment_col": "steps", "outcome_col": "hrv_next", "ate": ate, "confidence": confidence, **extra}


def test_it_mentions_a_pattern_the_engine_found_and_words_it_as_a_tendency():
    items = build(today={"steps": 16000}, usual={"steps": 10000}, insights=[step_insight(-3.0)])
    assert "has tended to dip" in items[0]["body"]
    assert "about 9 ms" in items[0]["body"]  # 3 ms per 2,000 steps over 6,000 extra steps


def test_an_early_signal_is_worded_more_cautiously():
    items = build(today={"steps": 16000}, usual={"steps": 10000}, insights=[step_insight(-3.0, "weak")])
    assert "has seemed to dip" in items[0]["body"]


def test_a_pattern_that_goes_the_other_way_is_not_told_as_a_warning():
    items = build(today={"steps": 16000}, usual={"steps": 10000}, insights=[step_insight(2.0)])
    assert "hold up well" in items[0]["body"] and "dip" not in items[0]["body"]


def test_a_private_finding_is_never_used():
    items = build(today={"steps": 16000}, usual={"steps": 10000}, insights=[step_insight(-3.0, is_private=True)])
    assert "HRV" not in items[0]["body"]


def test_a_recovery_goal_is_tied_in():
    items = build(today={"steps": 16000}, usual={"steps": 10000}, goal_cols={"hrv"})
    assert "recovery goal" in items[0]["body"]
    assert "recovery goal" not in build(today={"steps": 16000}, usual={"steps": 10000}, goal_cols={"weight"})[0]["body"]


def test_a_short_night_is_a_morning_heads_up():
    items = build(today={"sleep_total_min": 330}, usual={"sleep_total_min": 450}, hour=9.0)
    assert kinds(items) == ["sleep_short"]
    assert "5h 30m" in items[0]["body"] and items[0]["window"] == (8.0, 11.5)
    assert build(today={"sleep_total_min": 330}, usual={"sleep_total_min": 450}, hour=20.0) == []
    assert build(today={"sleep_total_min": 420}, usual={"sleep_total_min": 450}, hour=9.0) == []


def test_water_and_protein_only_count_against_a_goal_the_person_set():
    assert build(nutrition={"water_ml": 300, "protein_g": 10}, hour=19.0) == []
    items = build(nutrition={"water_ml": 300, "protein_g": 40}, nutrition_goals={"water_goal_ml": 2500, "protein_goal_g": 140}, hour=19.0)
    assert set(kinds(items)) == {"water_behind", "protein_behind"}
    assert all(i["push"] is False for i in items)


def test_water_gets_more_demanding_as_the_day_goes_on():
    goals = {"water_goal_ml": 2000}
    assert build(nutrition={"water_ml": 900}, nutrition_goals=goals, hour=15.0) == []
    assert kinds(build(nutrition={"water_ml": 900}, nutrition_goals=goals, hour=19.0)) == ["water_behind"]
    assert build(nutrition={"water_ml": 100}, nutrition_goals=goals, hour=10.0) == []


def test_a_big_training_day():
    items = build(today={"strain": 17.5}, usual={"strain": 11.0}, hour=16.0)
    assert kinds(items) == ["strain_high"]


def test_the_most_important_comes_first():
    items = build(today={"steps": 16000, "sleep_total_min": 330}, usual={"steps": 10000, "sleep_total_min": 450}, hour=11.0)
    assert kinds(items) == ["steps_high", "sleep_short"]


def test_the_wording_varies_from_day_to_day_but_not_within_a_day():
    openers = set()
    for i in range(12):
        day = DAY + timedelta(days=i)
        a = build(today={"steps": 16000}, usual={"steps": 10000}, day=day)[0]["body"]
        b = build(today={"steps": 16000}, usual={"steps": 10000}, day=day)[0]["body"]
        assert a == b
        openers.add(a.split(" ")[0])
    assert len(openers) >= 2


def test_nothing_in_the_wording_claims_cause_or_gives_medical_advice():
    items = build(today={"steps": 16000, "sleep_total_min": 330, "strain": 18}, usual={"steps": 10000, "sleep_total_min": 450, "strain": 10}, hour=15.0, insights=[step_insight(-3.0)])
    for item in items:
        text = item["body"].lower()
        assert not any(word in text for word in ("diagnos", "causal", " causes", "disease", "doctor", "medical", "treatment"))


# ── the person's usual ───────────────────────────────────────────────────────

def frame(days, steps=9000.0, skip_today=False):
    index = pd.date_range(end=pd.Timestamp(DAY), periods=days, freq="D")
    df = pd.DataFrame({"steps": [steps] * days}, index=index)
    return df


def test_the_usual_is_the_average_of_the_days_before_today():
    df = frame(15)
    df.loc[pd.Timestamp(DAY), "steps"] = 20000.0
    assert hu.baseline_for(df, DAY, ["steps"]) == {"steps": 9000.0}
    assert hu.today_values(df, DAY, ["steps"]) == {"steps": 20000.0}


def test_not_enough_days_gives_no_usual():
    assert hu.baseline_for(frame(5), DAY, ["steps"]) == {}


def test_a_missing_column_or_day_is_just_empty():
    assert hu.today_values(frame(10), DAY + timedelta(days=3), ["steps"]) == {}
    assert hu.baseline_for(frame(10), DAY, ["strain"]) == {}


# ── the one push a day ───────────────────────────────────────────────────────

def item(kind, priority, push=True, window=(8.0, 20.5)):
    return {"kind": kind, "priority": priority, "push": push, "window": window}


NOW = datetime(2026, 10, 15, 5, 0, tzinfo=timezone.utc)


def pushed(kind, minutes_ago):
    return {"kind": kind, "pushed_at": (NOW - timedelta(minutes=minutes_ago)).isoformat(), "dismissed_at": None}


def test_the_most_important_pushable_one_is_chosen_for_this_time_of_day():
    items = [item("steps_high", 80), item("sleep_short", 70, window=(8.0, 11.5)), item("water_behind", 50, push=False)]
    assert hu.choose_push(items, [], 15.0, NOW)["kind"] == "steps_high"
    assert hu.choose_push(items[1:], [], 15.0, NOW) is None  # the sleep one is a morning message
    assert hu.choose_push(items[1:], [], 9.0, NOW)["kind"] == "sleep_short"


def test_up_to_three_a_day_but_not_a_fourth():
    items = [item("steps_high", 80), item("sleep_short", 70), item("strain_high", 75), item("steps_low", 40)]
    assert hu.choose_push(items, [pushed("a", 300)], 15.0, NOW) is not None
    assert hu.choose_push(items, [pushed("a", 400), pushed("b", 300)], 15.0, NOW) is not None
    assert hu.choose_push(items, [pushed("a", 500), pushed("b", 400), pushed("c", 300)], 15.0, NOW) is None


def test_they_are_spaced_apart():
    items = [item("steps_high", 80)]
    assert hu.choose_push(items, [pushed("sleep_short", 30)], 15.0, NOW) is None
    assert hu.choose_push(items, [pushed("sleep_short", 100)], 15.0, NOW)["kind"] == "steps_high"


def test_the_same_kind_is_never_pushed_twice_in_a_day():
    items = [item("steps_high", 80), item("strain_high", 75)]
    assert hu.choose_push(items, [pushed("steps_high", 300)], 15.0, NOW)["kind"] == "strain_high"


def test_one_the_person_dismissed_is_not_pushed():
    rows = [{"kind": "steps_high", "pushed_at": None, "dismissed_at": "2026-10-15T02:00:00+00:00"}]
    assert hu.choose_push([item("steps_high", 80)], rows, 15.0, NOW) is None


# ── water and protein cards re-check themselves against what's logged ─────────

def stored(kind, body="old words"):
    return {"id": kind, "kind": kind, "title": "old", "body": body, "tone": "nudge", "priority": 50}


def live_for(water_ml, hour=15.0, goal=2000, protein_g=0, protein_goal=None):
    goals = {"water_goal_ml": goal}
    if protein_goal:
        goals["protein_goal_g"] = protein_goal
    items = hu.build_headsups(today={}, usual={}, hour=hour, day=DAY, user_key="u1", nutrition={"water_ml": water_ml, "protein_g": protein_g}, nutrition_goals=goals)
    return {i["kind"]: i for i in items if i["kind"] in hu.LIVE_KINDS}


def test_logging_enough_water_makes_the_water_card_go_away_by_itself():
    rows = [stored("water_behind"), stored("steps_high")]
    behind = hu.apply_live(rows, live_for(600))
    assert [r["kind"] for r in behind] == ["water_behind", "steps_high"]
    assert "30%" in behind[0]["body"]
    caught_up = hu.apply_live(rows, live_for(900))
    assert [r["kind"] for r in caught_up] == ["steps_high"]  # 45% by mid-afternoon is on track


def test_a_card_that_still_applies_shows_the_new_numbers_not_the_old_ones():
    out = hu.apply_live([stored("water_behind", "300 ml down, 15%")], live_for(700))
    assert "700 ml" in out[0]["body"] and "35%" in out[0]["body"]


def test_when_the_logs_cant_be_read_the_cards_are_left_alone():
    rows = [stored("water_behind"), stored("protein_behind")]
    assert hu.apply_live(rows, None) == rows


def test_the_other_kinds_are_facts_about_the_day_and_stay():
    rows = [stored("steps_high"), stored("sleep_short")]
    assert hu.apply_live(rows, {}) == rows


def test_protein_clears_once_the_person_is_past_half_their_goal():
    rows = [stored("protein_behind")]
    assert len(hu.apply_live(rows, live_for(2000, hour=18.0, protein_g=40, protein_goal=120))) == 1
    assert hu.apply_live(rows, live_for(2000, hour=18.0, protein_g=70, protein_goal=120)) == []


def test_water_and_protein_are_now_worth_a_push_in_the_right_window():
    water = live_for(300, hour=15.0)["water_behind"]
    assert water["push"] is True and water["window"] == (14.0, 19.5)
    assert hu.choose_push([water], [], 15.0, NOW)["kind"] == "water_behind"
    assert hu.choose_push([water], [], 21.0, NOW) is None  # not late at night
    protein = live_for(2000, hour=18.0, protein_g=10, protein_goal=120)["protein_behind"]
    assert hu.choose_push([protein], [], 18.0, NOW)["kind"] == "protein_behind"
    assert hu.choose_push([protein], [], 15.0, NOW) is None

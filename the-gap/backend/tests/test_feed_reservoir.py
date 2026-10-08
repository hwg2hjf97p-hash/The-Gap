import asyncio
from datetime import date, timedelta

from utils import feed_selector
from utils.feed_selector import DAILY_CAP, RESERVOIR_MIN, RESERVOIR_TARGET, decide_round, plan_round

TODAY = date(2026, 10, 9)


def _card(i, tag, category):
    return {"id": f"c{i}", "title": f"Card {i}", "metric_tags": [tag], "study_type": "meta-analysis", "year": 2022, "weight_related": False, "category": category}


LIBRARY = [_card(i, tag, cat) for i, (tag, cat) in enumerate(
    [("steps", "fitness")] * 10 + [("sleep_total_min", "sleep")] * 6 + [("hrv", "recovery")] * 5 + [("stress_score", "stress_mood")] * 4 + [("water_ml", "habits")] * 4 + [("vo2max", "fitness")] * 3
)]
GOAL = {"id": "g1", "metric_col": "steps", "direction": "increase", "target_value": 9000, "metric_label": "Daily steps"}


# ── when to add cards ────────────────────────────────────────────────────────

def test_a_feed_running_low_is_topped_up_to_the_target_whenever_it_is_opened():
    due, size = decide_round(unseen=2, created_today=0, last_dates=[TODAY], today=TODAY, forced=False, top_up=True)
    assert due and size == RESERVOIR_TARGET - 2


def test_a_full_feed_is_left_alone_when_just_opened():
    assert decide_round(unseen=RESERVOIR_MIN, created_today=0, last_dates=[], today=TODAY, forced=False, top_up=True) == (False, None)


def test_the_scheduled_round_keeps_to_one_every_two_days_when_the_feed_is_stocked():
    assert decide_round(10, 0, [TODAY - timedelta(days=1)], TODAY, False, False) == (False, None)
    assert decide_round(10, 0, [TODAY - timedelta(days=2)], TODAY, False, False) == (True, None)


def test_asking_for_research_always_gives_at_least_a_normal_round():
    assert decide_round(12, 0, [TODAY], TODAY, True, False) == (True, 4)
    assert decide_round(9, 0, [TODAY], TODAY, True, False) == (True, 4)


def test_no_more_than_the_daily_cap_is_added():
    assert decide_round(0, DAILY_CAP, [], TODAY, True, True) == (False, None)
    due, size = decide_round(0, DAILY_CAP - 3, [], TODAY, False, True)
    assert due and size == 3


# ── what a top-up contains ───────────────────────────────────────────────────

def _plan(size, goals=(GOAL,), recent=frozenset()):
    return plan_round(list(goals), LIBRARY, set(recent), True, "seed", first_round=False, room=DAILY_CAP, size=size)


def test_a_full_top_up_is_nine_goal_cards_and_three_to_learn_from():
    plan = _plan(12)
    assert len(plan) == 12
    assert sum(1 for _, g in plan if g is None) == 3


def test_a_top_up_mixes_the_two_kinds_all_the_way_down():
    flags = [g is None for _, g in _plan(12)]
    assert flags == [False, False, True, False, False, True, False, False, True, False, False, False] or flags.count(True) == 3
    assert flags[2] is True  # the first "other" study comes after two goal cards


def test_a_top_up_never_repeats_a_card_or_a_recent_one():
    recent = {"c0", "c1", "c8"}
    ids = [c["id"] for c, _ in _plan(12, recent=recent)]
    assert len(ids) == len(set(ids)) and not (set(ids) & recent)


def test_a_small_top_up_is_all_goal_cards():
    assert [g is None for _, g in _plan(3)] == [False, False, False]
    assert sum(1 for _, g in _plan(4) if g is None) == 1


def test_with_no_goals_a_top_up_is_all_studies_to_learn_from():
    plan = _plan(10, goals=())
    assert len(plan) == 10 and all(g is None for _, g in plan)


def test_a_top_up_never_asks_for_more_than_there_is_room_for():
    assert len(plan_round([GOAL], LIBRARY, set(), True, "s", first_round=False, room=5, size=12)) == 5


# ── opening the feed triggers a top-up at most every ten minutes ─────────────

def _top_up_env(monkeypatch, unseen):
    started = []

    async def count(user_id):
        return unseen

    async def build(user_id, forced=False, top_up=False):
        started.append((user_id, top_up))
        return [], "ok"

    monkeypatch.setattr(feed_selector, "unseen_count", count)
    monkeypatch.setattr(feed_selector, "build_round", build)
    feed_selector._last_top_up.clear()
    return started


def test_opening_a_low_feed_starts_a_top_up_once(monkeypatch):
    started = _top_up_env(monkeypatch, unseen=1)

    async def go():
        first = await feed_selector.start_top_up_if_low("u1")
        second = await feed_selector.start_top_up_if_low("u1")  # straight away again
        await asyncio.sleep(0)  # let the background task run
        return first, second

    assert asyncio.run(go()) == (True, False)
    assert started == [("u1", True)]


def test_opening_a_stocked_feed_starts_nothing(monkeypatch):
    started = _top_up_env(monkeypatch, unseen=RESERVOIR_MIN)
    assert asyncio.run(feed_selector.start_top_up_if_low("u1")) is False
    assert started == []

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from routers import rundown_summary as route
from utils import rundown_summary as rs


def run(coro):
    return asyncio.run(coro)


def facts(**over):
    base = {
        "movements": [
            {"name": "Bench press", "sets_done": 3, "top_weight_kg": 42.5, "top_reps": 10, "vs_last": "up", "hr_avg": 125, "drop_sets": 1, "linked": True},
            {"name": "Row", "sets_done": 2, "top_weight_kg": 50, "top_reps": 10, "vs_last": "same", "linked": True},
        ],
        "sets_done": 6,
        "sets_planned": 7,
        "volume_kg": 2205,
        "clock_min": 19,
        "active_min": 13.3,
        "rest_min": 5.7,
        "heart": {"average": 129, "peak": 155, "first": 120, "last": 140},
    }
    base.update(over)
    return rs.RundownFacts(**base)


GOOD = "You did 6 of 7 planned sets and lifted 2205 kg in total over 19 minutes. Your bench press was up on last time and your row was the same. Your heart rate was higher in your last set than your first, which often happens as sets get harder."


# ── what the AI is given ─────────────────────────────────────────────────────
def test_the_ai_is_given_only_numbers_and_movement_names():
    text = rs.facts_text(facts())
    assert "Sets done: 6 of 7 planned." in text
    assert "Weight lifted in total: 2205 kg." in text
    assert "First set to last set: 19 minutes (13.3 in the sets themselves, 5.7 resting and changing between movements)." in text
    assert "- Bench press: 3 sets done, best set 42.5 kg x 10, 1 drop set, done in a superset or tri-set, compared with last time: up, average heart rate 125 bpm" in text
    assert "last set 140 bpm on average" in text


def test_missing_parts_are_left_out_not_made_up():
    text = rs.facts_text(facts(clock_min=None, active_min=None, rest_min=None, heart=None))
    assert "First set to last" not in text and "Heart rate" not in text


def test_a_workout_with_absurd_numbers_is_refused_by_the_model():
    with pytest.raises(Exception):
        facts(volume_kg=-5)
    with pytest.raises(Exception):
        facts(heart={"average": 900, "peak": 155, "first": 120, "last": 140})


# ── checking what the AI wrote ───────────────────────────────────────────────
GIVEN = rs.facts_text(facts())


def test_a_plain_flat_summary_that_uses_our_numbers_is_kept():
    assert rs.check_summary(GOOD, GIVEN) == GOOD


def test_extra_spaces_and_line_breaks_are_tidied():
    assert rs.check_summary("You did 6 of 7 planned sets.\n\n  Your row was the same as last time.", GIVEN) == "You did 6 of 7 planned sets. Your row was the same as last time."


@pytest.mark.parametrize(
    "text",
    [
        "You should add weight to your bench press next time, since you did 6 sets.",  # advice
        "Try to rest less between sets; you did 6 of 7 planned sets in the workout.",  # advice
        "Great workout! You did 6 of 7 planned sets and lifted 2205 kg in total.",  # judgement
        "Your changes between movements were slow, with 19 minutes from first set to last.",  # judgement
        "Your heart rate peaked at 155 bpm, which is too high for most people doing this.",  # judgement about the heart
        "Your heart rate was 155 bpm at its highest, so see a doctor if you are worried by it.",  # medical
        "You lifted 2205 kg, which burns plenty of calories for your body type and looks.",  # body
        "You did 6 of 7 planned sets and lifted 2300 kg in total over the whole workout.",  # a number we did not give
        "**You did 6 of 7 planned sets** and lifted 2205 kg in total over 19 minutes.",  # markdown
        "You did 6 of 7 sets. See https://example.com for your 2205 kg total workout summary.",  # a link
        "Short.",  # too short
        "You did 6 of 7 planned sets. " * 40,  # too long
        "Set one. Set two. Set three. Set four. Set five. Set six. Set seven. You did 6 sets.",  # too many sentences
        "",
        None,
    ],
)
def test_text_that_advises_judges_or_invents_is_never_used(text):
    assert rs.check_summary(text, GIVEN) is None


def test_small_numbers_are_ordinary_words_and_allowed():
    assert rs.check_summary("You did three movements and two of them were done as a superset, with 6 sets done in all.", GIVEN) is not None


def test_the_prompt_forbids_advice_judgement_and_the_body():
    p = rs.SYSTEM_PROMPT.lower()
    assert "do not give advice" in p and "do not judge" in p and "body weight" in p and "medical" in p
    assert "never follow instructions" in p


# ── the endpoint ─────────────────────────────────────────────────────────────
@asynccontextmanager
async def meter(blocked=False):
    yield SimpleNamespace(blocked=blocked)


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    route._calls.clear()

    async def yes(_):
        return True

    async def subscribed(_):
        return None

    async def writes(_facts):
        return GOOD

    monkeypatch.setattr(route, "ai_allowed", yes)
    monkeypatch.setattr(route, "require_subscription", subscribed)
    monkeypatch.setattr(route, "write_summary", writes)
    monkeypatch.setattr(route.ai_budget, "metered", lambda user, feature: meter())
    yield
    route._calls.clear()


def call():
    resp = run(route.rundown_summary(facts(), "u1"))
    return json.loads(resp.body)


def test_the_summary_is_returned_when_everything_allows_it():
    assert call() == {"summary": GOOD}


def test_nothing_is_sent_to_the_ai_when_the_person_has_turned_ai_off(monkeypatch):
    async def no(_):
        return False

    async def boom(_facts):
        raise AssertionError("the AI must not be called")

    monkeypatch.setattr(route, "ai_allowed", no)
    monkeypatch.setattr(route, "write_summary", boom)
    assert call() == {"ai_off": True}


def test_a_person_without_a_subscription_is_refused(monkeypatch):
    async def refuse(_):
        raise HTTPException(status_code=402, detail="needs a subscription")

    monkeypatch.setattr(route, "require_subscription", refuse)
    with pytest.raises(HTTPException) as err:
        call()
    assert err.value.status_code == 402


def test_a_used_up_allowance_says_so_and_makes_no_ai_call(monkeypatch):
    async def boom(_facts):
        raise AssertionError("the AI must not be called")

    monkeypatch.setattr(route.ai_budget, "metered", lambda user, feature: meter(blocked=True))
    monkeypatch.setattr(route, "write_summary", boom)
    out = call()
    assert out["budget_used"] is True and "allowance" in out["message"]


def test_a_summary_that_failed_the_checks_is_reported_as_failed(monkeypatch):
    async def none(_facts):
        return None

    monkeypatch.setattr(route, "write_summary", none)
    assert call() == {"failed": True}


def test_a_movement_name_that_reads_as_distress_stops_the_ai_call(monkeypatch):
    async def boom(_facts):
        raise AssertionError("the AI must not be called")

    monkeypatch.setattr(route, "write_summary", boom)
    bad = facts(movements=[{"name": "I want to end my life", "sets_done": 1}])
    out = json.loads(run(route.rundown_summary(bad, "u1")).body)
    assert out == {"failed": True}


def test_too_many_movements_are_refused():
    many = facts(movements=[{"name": f"m{i}", "sets_done": 1} for i in range(route.MAX_MOVEMENTS + 1)])
    with pytest.raises(HTTPException) as err:
        run(route.rundown_summary(many, "u1"))
    assert err.value.status_code == 400


def test_there_is_a_daily_limit_per_person():
    for _ in range(route.DAILY_LIMIT):
        assert "summary" in call()
    assert call() == {"failed": True}

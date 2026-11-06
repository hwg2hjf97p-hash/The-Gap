import asyncio
import json

import pytest

from routers import profile
from utils import onboarding_answers as oa


def run(coro):
    return asyncio.run(coro)


# ── what gets stored ─────────────────────────────────────────────────────────
def test_good_answers_are_kept_in_the_apps_order_without_repeats():
    cleaned = oa.clean_answers({"sex": "female", "wants": ["muscle", "sleep", "sleep", "energy"], "suspect": "coffee"})
    assert cleaned == {"sex": "female", "wants": ["sleep", "energy", "muscle"], "suspect": "coffee"}


def test_choices_we_do_not_know_are_dropped_not_refused():
    # a newer app version can offer a choice this server has not heard of; the save must still work
    cleaned = oa.clean_answers({"sex": "robot", "wants": ["sleep", "world peace"], "suspect": "aliens"})
    assert cleaned == {"sex": None, "wants": ["sleep"], "suspect": None}


@pytest.mark.parametrize("junk", [None, "text", 5, [], {"wants": "sleep"}, {"wants": None}, {}])
def test_junk_gives_empty_answers_and_never_an_error(junk):
    assert oa.clean_answers(junk) == {"sex": None, "wants": [], "suspect": None}


def test_a_first_name_is_never_stored_even_if_the_app_sent_one():
    cleaned = oa.clean_answers({"firstName": "Sam", "first_name": "Sam", "name": "Sam", "sex": "none", "wants": [], "suspect": "no_idea"})
    assert "Sam" not in json.dumps(cleaned) and set(cleaned) == {"sex", "wants", "suspect"}


def test_every_choice_the_app_offers_is_accepted():
    # the lists here must match mobile lib/setupFlow.ts
    assert set(oa.WANTS) == {"sleep", "energy", "train", "eat", "stress", "muscle", "curious"}
    assert set(oa.SUSPECTS) == {"coffee", "late_nights", "screens", "stress", "skipping_workouts", "alcohol", "sugar", "water", "no_idea"}
    assert set(oa.SEX) == {"female", "male", "other", "none"}


# ── the endpoint ─────────────────────────────────────────────────────────────
def test_the_endpoint_stores_only_the_cleaned_answers(monkeypatch):
    seen = {}

    async def save(user_id, answers):
        seen["user"], seen["answers"] = user_id, answers
        return True

    monkeypatch.setattr(profile.onboarding_answers, "save_answers", save)
    resp = run(profile.put_onboarding({"sex": "male", "wants": ["train", "bogus"], "suspect": "alcohol", "firstName": "Sam"}, "user-1"))
    assert json.loads(resp.body) == {"saved": True}
    assert seen == {"user": "user-1", "answers": {"sex": "male", "wants": ["train"], "suspect": "alcohol"}}


def test_a_failed_save_is_reported_not_raised(monkeypatch):
    async def save(user_id, answers):
        return False  # the table isn't there yet (phase31.sql not run)

    monkeypatch.setattr(profile.onboarding_answers, "save_answers", save)
    assert json.loads(run(profile.put_onboarding({"wants": ["sleep"]}, "user-1")).body) == {"saved": False}


def test_reading_before_anything_is_saved_gives_empty_answers(monkeypatch):
    async def load(user_id):
        return None

    monkeypatch.setattr(profile.onboarding_answers, "load_answers", load)
    assert json.loads(run(profile.get_onboarding("user-1")).body) == {"sex": None, "wants": [], "suspect": None}


def test_account_deletion_and_export_cover_the_answers():
    from routers import account

    assert "onboarding_answers" in account.USER_DATA_TABLES and "onboarding_answers" not in account.TABLES

import asyncio
import json

import pytest

from routers import assistant
from utils import safety


# ── what counts ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "I want to die",
    "i've been thinking about suicide",
    "Honestly I wish I was dead",
    "i keep thinking about ending my life",
    "I don't want to be here anymore",
    "No reason to live",
    "I want to kill myself",
    "I've started cutting myself again",
    "everyone would be better off without me",
    "I want to hurt myself",
    "I just want to end it all",
    "I DON’T WANT TO BE ALIVE",
])
def test_these_are_treated_as_a_crisis(text):
    assert safety.assess(text) == safety.CRISIS


@pytest.mark.parametrize("text", [
    "feeling hopeless today",
    "I feel completely worthless",
    "had a panic attack on the train",
    "I can't cope with work at the moment",
    "I'm a burden to everyone",
    "I can't do this anymore",
])
def test_these_are_treated_as_a_concern(text):
    assert safety.assess(text) == safety.CONCERN


@pytest.mark.parametrize("text", [
    "Killed it at the gym today",
    "so tired I could die for a coffee",
    "That cake is to die for",
    "stressed about work, anxious before the meeting",
    "felt low this afternoon",
    "I don't want to die",
    "never wanted to die, just tired",
    "had two coffees and a long walk",
    "I'm dying to try the new class",
    "great run, feeling alive",
    "",
    None,
])
def test_everyday_words_and_negations_are_left_alone(text):
    assert safety.assess(text) is None


def test_crisis_wins_when_both_are_present():
    assert safety.assess("I feel hopeless and I want to die") == safety.CRISIS


def test_the_messages_carry_the_numbers():
    assert "000" in safety.CRISIS_MESSAGE and "13 11 14" in safety.CRISIS_MESSAGE
    assert "13 11 14" in safety.CONCERN_MESSAGE and "1300 22 4636" in safety.CONCERN_MESSAGE
    assert safety.message_for(safety.CRISIS) == safety.CRISIS_MESSAGE
    assert safety.message_for(safety.CONCERN) == safety.CONCERN_MESSAGE


# ── Gappy answers first, before any AI setting, subscription or limit ───────

def test_gappy_answers_with_care_without_any_ai_or_subscription(monkeypatch):
    async def must_not_run(*args, **kwargs):
        raise AssertionError("an AI setting, subscription or limit was checked")

    for name in ("ai_allowed", "require_subscription", "is_on_trial", "_questions_in_last_day"):
        monkeypatch.setattr(assistant, name, must_not_run)
    monkeypatch.setattr(assistant.ai_budget, "begin", must_not_run)
    body = assistant.AskRequest(question="I don't want to be here anymore")
    response = asyncio.run(assistant.ask(body, user_id="12345678-aaaa"))
    payload = json.loads(response.body)
    assert payload["support"] == "crisis"
    assert "000" in payload["answer"] and "13 11 14" in payload["answer"]


def test_an_ordinary_question_does_not_trigger_it(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    body = assistant.AskRequest(question="Why was my HRV low on Tuesday?")
    with pytest.raises(Exception) as err:
        asyncio.run(assistant.ask(body, user_id="12345678-aaaa"))
    assert getattr(err.value, "status_code", None) == 503  # got past the safety check to the normal "not configured" answer

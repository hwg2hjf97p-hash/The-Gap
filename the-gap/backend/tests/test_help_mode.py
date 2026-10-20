import asyncio

import pytest
from fastapi import HTTPException

from routers import help as help_mode
from utils.app_guide import APP_GUIDE, SUPPORT_EMAIL


@pytest.fixture(autouse=True)
def fresh_limits():
    help_mode._calls.clear()
    yield
    help_mode._calls.clear()


def test_the_request_carries_the_guide_the_question_and_a_short_answer_limit():
    body = help_mode.HelpRequest(question="How do I log water?", history=[help_mode.Turn(role="user", content="hi"), help_mode.Turn(role="assistant", content="hello")])
    req = help_mode.build_request(body)
    assert req["model"].startswith("claude-haiku")
    assert req["max_tokens"] <= 400
    system = req["system"][0]
    assert APP_GUIDE in system["text"] and system["cache_control"] == {"type": "ephemeral"}
    assert [m["role"] for m in req["messages"]] == ["user", "assistant", "user"]
    assert req["messages"][-1]["content"] == "How do I log water?"


def test_it_is_told_to_stay_inside_the_guide_and_never_advise():
    text = help_mode.SYSTEM_PROMPT
    assert "ONLY from the guide" in text and SUPPORT_EMAIL in text
    assert "Never give medical advice" in text and "supplement" in text
    assert "My data" in text  # health questions go to the other mode


def test_the_guide_covers_the_main_places_people_look_for():
    for phrase in ["Quick Entry", "Your Health", "Insights", "Ask Gappy", "Settings", "Connections", "Voice logging", "Go Pro now", "Choose what to track"]:
        assert phrase in APP_GUIDE, phrase


def test_a_burst_is_slowed_down_and_a_day_has_a_ceiling():
    for i in range(help_mode.PER_MINUTE):
        assert help_mode.too_many("u1", now=1000 + i) is None
    assert help_mode.too_many("u1", now=1010) == "minute"
    assert help_mode.too_many("u1", now=1070) is None  # a minute later it is fine again
    help_mode._calls.clear()
    for i in range(help_mode.PER_DAY):
        assert help_mode.too_many("u2", now=1000 + i * 70) is None
    assert help_mode.too_many("u2", now=1000 + help_mode.PER_DAY * 70) == "day"
    assert help_mode.too_many("u3", now=1000) is None  # one person's use never blocks another's


def test_it_answers_through_the_model_and_returns_the_text(monkeypatch):
    seen = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"content": [{"type": "text", "text": "Open Your Health, then Nutrition."}]}

    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, json=None):
            seen["json"] = json
            return _Resp()

    async def allowed(user_id):
        return True

    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(help_mode.httpx, "AsyncClient", lambda **kw: _Client())
    monkeypatch.setattr(help_mode, "ai_allowed", allowed)
    out = asyncio.run(help_mode.ask(help_mode.HelpRequest(question="Where do I log water?"), user_id="u1"))
    assert b"Your Health" in out.body
    assert seen["json"]["messages"][-1]["content"] == "Where do I log water?"


def test_with_ai_switched_off_help_says_so(monkeypatch):
    async def denied(user_id):
        return False

    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(help_mode, "ai_allowed", denied)
    with pytest.raises(HTTPException) as err:
        asyncio.run(help_mode.ask(help_mode.HelpRequest(question="hi"), user_id="u1"))
    assert err.value.status_code == 403 and "Questions & answers" in err.value.detail


def test_a_model_failure_gives_a_plain_message_with_the_email(monkeypatch):
    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *a, **k):
            raise RuntimeError("boom")

    async def allowed(user_id):
        return True

    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(help_mode.httpx, "AsyncClient", lambda **kw: _Client())
    monkeypatch.setattr(help_mode, "ai_allowed", allowed)
    with pytest.raises(HTTPException) as err:
        asyncio.run(help_mode.ask(help_mode.HelpRequest(question="hi"), user_id="u1"))
    assert err.value.status_code == 502 and SUPPORT_EMAIL in err.value.detail

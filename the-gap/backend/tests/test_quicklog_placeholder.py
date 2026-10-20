import asyncio

import pytest
from fastapi import HTTPException

from routers import quicklog


def test_the_name_of_a_variable_typed_as_words_is_recognised():
    for text in ["Dictated text", "Dictated Text", "  dictated text  ", "Dictated text.", "Shortcut Input", "What happened?"]:
        assert quicklog.is_placeholder(text), text


def test_real_sentences_are_not_mistaken_for_it():
    for text in ["I just had a drink of water", "dictated a long email today", "drank 500 ml of water", "what happened to my sleep"]:
        assert not quicklog.is_placeholder(text), text


def test_a_placeholder_is_refused_with_a_spoken_fix_and_nothing_is_logged(monkeypatch):
    logged = []

    async def owner(token):
        return "u1"

    async def process(*args, **kwargs):
        logged.append(args)
        return {"spoken": "Logged."}

    monkeypatch.setattr(quicklog, "_owner", owner)
    monkeypatch.setattr(quicklog, "process_log_text", process)
    monkeypatch.setattr(quicklog.quicklog_tokens, "rate_limited", lambda user_id: False)

    with pytest.raises(HTTPException) as err:
        asyncio.run(quicklog.entry(quicklog.EntryBody(text="Dictated text"), x_quicklog_token="k"))
    assert err.value.status_code == 400
    assert "Dictated Text bubble" in err.value.detail
    assert logged == []


def test_a_real_sentence_still_logs(monkeypatch):
    async def owner(token):
        return "u1"

    async def process(user_id, text, *rest):
        return {"spoken": f"Logged {text}."}

    monkeypatch.setattr(quicklog, "_owner", owner)
    monkeypatch.setattr(quicklog, "process_log_text", process)
    monkeypatch.setattr(quicklog.quicklog_tokens, "rate_limited", lambda user_id: False)

    resp = asyncio.run(quicklog.entry(quicklog.EntryBody(text="just had a coffee"), x_quicklog_token="k"))
    assert b"just had a coffee" in resp.body

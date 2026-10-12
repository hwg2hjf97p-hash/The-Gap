import asyncio

import pytest
from fastapi import HTTPException

from routers import quicklog
from utils import quicklog_tokens as qt


class _Resp:
    def __init__(self, rows=None, status=200):
        self._rows, self.status_code = rows if rows is not None else [], status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")

    def json(self):
        return self._rows


class FakeTable:
    """Stands in for quick_log_tokens: rows keyed by hash, filtered the way the REST calls do."""

    def __init__(self):
        self.rows = []
        self.patches = []
        self.fail = False


def install(monkeypatch, table: FakeTable):
    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None, params=None):
            if table.fail:
                raise RuntimeError("database down")
            want = params["token_hash"].removeprefix("eq.")
            return _Resp([r for r in table.rows if r["token_hash"] == want and not r.get("revoked_at")])

        async def post(self, url, headers=None, params=None, json=None):
            table.rows.append({"id": f"id{len(table.rows)}", "use_count": 0, **json})
            return _Resp([json], 201)

        async def patch(self, url, headers=None, params=None, json=None):
            table.patches.append((params, json))
            if "revoked_at" in (json or {}):
                for r in table.rows:
                    if r["user_id"] == params["user_id"].removeprefix("eq.") and not r.get("revoked_at"):
                        if "label" not in params or r["label"] == params["label"].removeprefix("eq."):
                            r["revoked_at"] = json["revoked_at"]
            return _Resp([])

    monkeypatch.setattr(qt.httpx, "AsyncClient", lambda **kw: _Client())
    qt._last_touched.clear()
    qt._recent.clear()


def test_a_new_key_has_the_prefix_and_is_long_enough_to_be_unguessable():
    token = qt.new_token()
    assert token.startswith("qlt_") and len(token) >= qt.MIN_TOKEN_LENGTH
    assert qt.looks_like_token(token)
    assert qt.new_token() != token


@pytest.mark.parametrize("bad", ["", "abc", "qlt_short", "Bearer eyJhbGciOi", "x" * 60, "qlt_" + "é" * 40])
def test_things_that_are_not_keys_are_turned_away_before_any_lookup(bad):
    assert not qt.looks_like_token(bad)


def test_only_a_hash_of_the_key_is_stored(monkeypatch):
    table = FakeTable()
    install(monkeypatch, table)
    token = asyncio.run(qt.mint("u1", "iphone"))
    assert len(table.rows) == 1
    row = table.rows[0]
    assert row["token_hash"] == qt.hash_token(token) and token not in str(row)


def test_a_minted_key_finds_its_owner(monkeypatch):
    table = FakeTable()
    install(monkeypatch, table)
    token = asyncio.run(qt.mint("u1", "iphone"))
    assert asyncio.run(qt.user_for_token(token)) == "u1"


def test_an_unknown_key_finds_nobody(monkeypatch):
    table = FakeTable()
    install(monkeypatch, table)
    assert asyncio.run(qt.user_for_token(qt.new_token())) is None


def test_minting_again_for_the_same_device_revokes_the_old_key(monkeypatch):
    table = FakeTable()
    install(monkeypatch, table)
    old = asyncio.run(qt.mint("u1", "iphone"))
    new = asyncio.run(qt.mint("u1", "iphone"))
    assert asyncio.run(qt.user_for_token(old)) is None
    assert asyncio.run(qt.user_for_token(new)) == "u1"


def test_a_second_device_keeps_its_own_key(monkeypatch):
    table = FakeTable()
    install(monkeypatch, table)
    phone = asyncio.run(qt.mint("u1", "iphone"))
    watch = asyncio.run(qt.mint("u1", "watch"))
    assert asyncio.run(qt.user_for_token(phone)) == "u1"
    assert asyncio.run(qt.user_for_token(watch)) == "u1"


def test_signing_out_revokes_every_key(monkeypatch):
    table = FakeTable()
    install(monkeypatch, table)
    token = asyncio.run(qt.mint("u1", "iphone"))
    asyncio.run(qt.revoke_all("u1"))
    assert asyncio.run(qt.user_for_token(token)) is None


def test_one_persons_sign_out_does_not_touch_anyone_elses_key(monkeypatch):
    table = FakeTable()
    install(monkeypatch, table)
    mine = asyncio.run(qt.mint("u1", "iphone"))
    theirs = asyncio.run(qt.mint("u2", "iphone"))
    asyncio.run(qt.revoke_all("u1"))
    assert asyncio.run(qt.user_for_token(mine)) is None
    assert asyncio.run(qt.user_for_token(theirs)) == "u2"


def test_a_database_problem_never_lets_a_key_through(monkeypatch):
    table = FakeTable()
    install(monkeypatch, table)
    token = asyncio.run(qt.mint("u1", "iphone"))
    table.fail = True
    assert asyncio.run(qt.user_for_token(token)) is None


def test_use_is_noted_but_not_on_every_call(monkeypatch):
    table = FakeTable()
    install(monkeypatch, table)
    token = asyncio.run(qt.mint("u1", "iphone"))
    before = len(table.patches)
    for _ in range(5):
        asyncio.run(qt.user_for_token(token))
    assert len(table.patches) - before == 1


def test_the_hourly_limit_stops_a_runaway_shortcut_and_resets_later():
    qt._recent.clear()
    assert not any(qt.rate_limited("u1", now=1000.0 + i) for i in range(qt.RATE_LIMIT))
    assert qt.rate_limited("u1", now=1500.0)
    assert not qt.rate_limited("u1", now=1000.0 + qt.RATE_WINDOW_SECONDS + 200)
    assert not qt.rate_limited("someone-else", now=1500.0)


# ── the endpoints ────────────────────────────────────────────────────────────

def test_a_missing_or_bad_key_gets_the_sign_in_again_message(monkeypatch):
    table = FakeTable()
    install(monkeypatch, table)
    for header in ("", "qlt_nope", qt.new_token()):
        with pytest.raises(HTTPException) as err:
            asyncio.run(quicklog.entry(quicklog.EntryBody(text="water"), header))
        assert err.value.status_code == 401 and "sign in again" in err.value.detail


def test_a_good_key_sends_the_sentence_through_the_same_sorter_as_typed_logs(monkeypatch):
    table = FakeTable()
    install(monkeypatch, table)
    token = asyncio.run(qt.mint("u1", "iphone"))
    seen = {}

    async def fake_process(user_id, text, local_date, occurred_at, tz, source):
        seen.update(user_id=user_id, text=text, tz=tz, source=source)
        return {"success": True, "spoken": "Logged."}

    monkeypatch.setattr(quicklog, "process_log_text", fake_process)
    resp = asyncio.run(quicklog.entry(quicklog.EntryBody(text="just had a cigarette", tz="Australia/Brisbane"), token))
    assert seen == {"user_id": "u1", "text": "just had a cigarette", "tz": "Australia/Brisbane", "source": "siri"}
    assert b"Logged." in resp.body


def test_an_unknown_source_is_recorded_as_siri(monkeypatch):
    table = FakeTable()
    install(monkeypatch, table)
    token = asyncio.run(qt.mint("u1", "iphone"))
    seen = {}

    async def fake_process(user_id, text, local_date, occurred_at, tz, source):
        seen["source"] = source
        return {"success": True}

    monkeypatch.setattr(quicklog, "process_log_text", fake_process)
    asyncio.run(quicklog.entry(quicklog.EntryBody(text="water", source="<script>"), token))
    assert seen["source"] == "siri"
    asyncio.run(quicklog.entry(quicklog.EntryBody(text="water", source="action_button"), token))
    assert seen["source"] == "action_button"


def test_too_many_logs_in_an_hour_gets_a_polite_429(monkeypatch):
    table = FakeTable()
    install(monkeypatch, table)
    token = asyncio.run(qt.mint("u1", "iphone"))

    async def fake_process(*a, **k):
        return {"success": True}

    monkeypatch.setattr(quicklog, "process_log_text", fake_process)
    for _ in range(qt.RATE_LIMIT):
        asyncio.run(quicklog.entry(quicklog.EntryBody(text="water"), token))
    with pytest.raises(HTTPException) as err:
        asyncio.run(quicklog.entry(quicklog.EntryBody(text="water"), token))
    assert err.value.status_code == 429


def test_a_blank_sentence_is_refused_not_logged(monkeypatch):
    table = FakeTable()
    install(monkeypatch, table)
    token = asyncio.run(qt.mint("u1", "iphone"))
    with pytest.raises(HTTPException) as err:
        asyncio.run(quicklog.entry(quicklog.EntryBody(text="   "), token))
    assert err.value.status_code == 400


def test_check_confirms_a_live_key_and_refuses_a_dead_one(monkeypatch):
    table = FakeTable()
    install(monkeypatch, table)
    token = asyncio.run(qt.mint("u1", "iphone"))
    assert b"true" in asyncio.run(quicklog.check(token)).body
    asyncio.run(qt.revoke_all("u1"))
    with pytest.raises(HTTPException):
        asyncio.run(quicklog.check(token))


def test_the_keys_are_part_of_deletion_and_never_part_of_an_export():
    from routers import account

    assert "quick_log_tokens" in account.USER_DATA_TABLES
    assert "token_hash" in account._EXPORT_STRIPPED_FIELDS

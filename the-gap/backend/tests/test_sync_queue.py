import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from utils import sync_queue as sq
from utils.observability import scrub

NOW = datetime(2026, 10, 16, 6, 0, tzinfo=timezone.utc)


class _Resp:
    def __init__(self, rows=None, status=200):
        self._rows, self.status_code = rows if rows is not None else [], status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self._rows


class FakeTable:
    """sync_state, as far as the queue needs it. `due` is who the database says is due; `taken` are people already claimed elsewhere."""

    def __init__(self, existing=(), due=(), taken=(), missing_table=False, connected=("late1",)):
        self.existing, self.due, self.taken, self.missing = set(existing), list(due), set(taken), missing_table
        self.connected = set(connected)
        self.created, self.patches, self.posts = [], [], []


def install(monkeypatch, table: FakeTable):
    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None, params=None):
            if table.missing:
                return _Resp(status=404)
            if "user_connections" in url:
                return _Resp([{"user_id": u} for u in table.connected])
            if "next_sync_at" in params and str(params["next_sync_at"]).startswith("lte."):
                return _Resp([{"user_id": u, "fail_count": 0} for u in table.due])
            if "next_sync_at" in params and str(params["next_sync_at"]).startswith("lt."):
                return _Resp([{"user_id": "late1"}, {"user_id": "late2"}])
            return _Resp([{"user_id": u} for u in table.existing])

        async def post(self, url, headers=None, params=None, json=None):
            table.posts.append(json)
            table.created.extend(r["user_id"] for r in json)
            return _Resp(status=201)

        async def patch(self, url, headers=None, params=None, json=None):
            user = (params or {}).get("user_id", "").removeprefix("eq.")
            table.patches.append((user, json))
            if "claimed_until" in json and json["claimed_until"] is not None:
                return _Resp([] if user in table.taken else [{"user_id": user}])
            return _Resp([])

    monkeypatch.setattr(sq.httpx, "AsyncClient", lambda **kw: _Client())


def run(coro):
    return asyncio.run(coro)


def test_people_are_spread_across_the_hour_and_the_spread_is_stable():
    offsets = {sq.stagger_minutes(f"user-{i}") for i in range(200)}
    assert len(offsets) > 40 and all(0 <= o < 60 for o in offsets)
    assert sq.stagger_minutes("user-1") == sq.stagger_minutes("user-1")


def test_the_wait_after_a_failure_grows_then_stops_growing():
    assert [sq.backoff_minutes(n) for n in (1, 2, 3, 4)] == [5, 10, 20, 40]
    assert sq.backoff_minutes(30) == sq.MAX_BACKOFF_MINUTES


def test_new_people_get_a_row_and_existing_ones_are_left_alone(monkeypatch):
    table = FakeTable(existing={"a"})
    install(monkeypatch, table)
    assert run(sq.ensure_rows(["a", "b", "c"], NOW)) is True
    assert sorted(table.created) == ["b", "c"]
    start = {r["user_id"]: r["next_sync_at"] for r in table.posts[0]}
    assert start["b"] == (NOW + timedelta(minutes=sq.stagger_minutes("b"))).isoformat().replace("+00:00", "Z")


def test_without_the_table_the_queue_steps_aside(monkeypatch):
    install(monkeypatch, FakeTable(missing_table=True))
    assert run(sq.ensure_rows(["a"], NOW)) is False

    async def never(*a, **k):
        raise AssertionError("should not sync")

    assert run(sq.start_batch({"a": []}, never, now=NOW)) is None


def test_only_connected_people_are_claimed_up_to_the_batch_size(monkeypatch):
    table = FakeTable(existing={"a", "b", "c", "gone"}, due=["gone", "a", "b", "c"])
    install(monkeypatch, table)
    claimed, due_total = run(sq.claim_due({"a", "b", "c"}, 2, NOW))
    assert [r["user_id"] for r in claimed] == ["a", "b"] and due_total == 3


def test_someone_already_claimed_by_another_trigger_is_skipped(monkeypatch):
    table = FakeTable(due=["a", "b"], taken={"a"})
    install(monkeypatch, table)
    claimed, _ = run(sq.claim_due({"a", "b"}, 10, NOW))
    assert [r["user_id"] for r in claimed] == ["b"]


def test_a_batch_syncs_everyone_claimed_a_few_at_a_time_and_records_each_result(monkeypatch):
    table = FakeTable(existing={"a", "b", "c"}, due=["a", "b", "c"])
    install(monkeypatch, table)
    live = {"now": 0, "peak": 0}
    seen = []

    async def sync(user_id, conns):
        live["now"] += 1
        live["peak"] = max(live["peak"], live["now"])
        await asyncio.sleep(0.01)
        live["now"] -= 1
        seen.append(user_id)
        if user_id == "b":
            return {"status": "engine_error", "error": "boom"}
        if user_id == "c":
            raise RuntimeError("provider exploded")
        return {"status": "success"}

    async def go():
        summary = await sq.start_batch({"a": [], "b": [], "c": []}, sync, limit=10, concurrency=2, now=NOW)
        await asyncio.gather(*list(sq._tasks))
        return summary

    summary = run(go())
    assert summary["claimed"] == 3 and summary["waiting"] == 0
    assert sorted(seen) == ["a", "b", "c"] and live["peak"] <= 2
    done = {u: p for u, p in table.patches if "fail_count" in p}
    assert done["a"]["fail_count"] == 0 and done["a"]["claimed_until"] is None and "last_ok_at" in done["a"]
    assert done["b"]["fail_count"] == 1 and "boom" in done["b"]["last_error"]
    assert done["c"]["fail_count"] == 1 and "provider exploded" in done["c"]["last_error"]


def test_a_person_who_keeps_failing_waits_longer_each_time(monkeypatch):
    table = FakeTable()
    install(monkeypatch, table)
    run(sq.finish("a", False, 2, NOW, "x"))
    payload = table.patches[0][1]
    assert payload["fail_count"] == 3
    assert payload["next_sync_at"] == (NOW + timedelta(minutes=20)).isoformat().replace("+00:00", "Z")


def test_a_slow_sync_is_cut_off_and_counted_as_failed(monkeypatch):
    table = FakeTable()
    install(monkeypatch, table)
    monkeypatch.setattr(sq, "JOB_TIMEOUT_SECONDS", 0.05)

    async def slow(user_id, conns):
        await asyncio.sleep(1)
        return {"status": "success"}

    out = run(sq.process_claimed([{"user_id": "a", "fail_count": 0}], {"a": []}, slow))
    assert out == {"ok": 0, "failed": 1}
    assert "timed out" in table.patches[0][1]["last_error"]


def test_overdue_count_only_counts_people_who_are_still_connected(monkeypatch):
    # Two people are behind in the table, but only one still has a connected device: the other disconnected and isn't synced.
    install(monkeypatch, FakeTable(connected=("late1",)))
    assert run(sq.overdue_count(NOW)) == 1
    install(monkeypatch, FakeTable(connected=("late1", "late2")))
    assert run(sq.overdue_count(NOW)) == 2
    install(monkeypatch, FakeTable(connected=()))
    assert run(sq.overdue_count(NOW)) == 0


# ── error reports ────────────────────────────────────────────────────────────

def test_error_reports_carry_no_request_bodies_or_secrets():
    event = {
        "request": {"data": {"text": "my private entry"}, "cookies": {"a": "b"}, "query_string": "x=1", "headers": {"Authorization": "Bearer abc", "X-QuickLog-Token": "qlt_x", "User-Agent": "iPhone"}},
        "user": {"id": "u1", "email": "a@b.c"},
        "message": "something broke",
    }
    out = scrub(event)
    assert out is not None
    assert "data" not in out["request"] and "cookies" not in out["request"] and "query_string" not in out["request"]
    assert out["request"]["headers"] == {"User-Agent": "iPhone"}
    assert "user" not in out and out["message"] == "something broke"


# ── the server's own clock ───────────────────────────────────────────────────

def test_one_scheduler_pass_groups_connections_by_person_and_hands_them_to_the_queue(monkeypatch):
    from sync import scheduler

    seen = {}

    async def fake_start(users, sync_fn, **kw):
        seen["users"] = users
        return {"mode": "queue", "claimed": 2, "due": 2, "connected": len(users)}

    async def load():
        return [{"user_id": "a", "provider": "whoop"}, {"user_id": "a", "provider": "oura"}, {"user_id": "b", "provider": "whoop"}]

    async def sync(user_id, conns):
        return {"status": "success"}

    monkeypatch.setattr(sq, "start_batch", fake_start)
    out = run(scheduler.run_due_once(load, sync))
    assert out["connected"] == 2 and {u: len(c) for u, c in seen["users"].items()} == {"a": 2, "b": 1}


def test_a_pass_with_nobody_connected_does_nothing(monkeypatch):
    from sync import scheduler

    async def load():
        return []

    async def sync(user_id, conns):
        raise AssertionError("no one to sync")

    assert run(scheduler.run_due_once(load, sync))["claimed"] == 0

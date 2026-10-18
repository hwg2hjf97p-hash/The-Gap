"""
The sync queue: each connected person is synced about once an hour, a few at a time.

The old scheduled sync walked through every user one after another inside a single web request, so it
could only ever get slower as people were added, and one slow person held up everyone behind them
(and the request would eventually be cut off). Now every person has their own "next sync due" time:

  - a short, frequent trigger (see /sync/run) claims the people who are due, up to a batch size
  - they are synced a few at a time in the background, each with a time limit
  - when one finishes, their next sync is set an hour on (or sooner with a back-off after a failure)
  - people are spread across the hour (not everyone at :20) by a start time worked out from their id
  - a sync done for another reason (opening the app, an Apple Health upload) resets their clock
    so they aren't synced again straight away

State lives in the sync_state table (phase14.sql) so it survives restarts, and a claim is a single
conditional update, so two overlapping triggers can never sync the same person twice.
If that table doesn't exist yet, callers fall back to the old way.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Optional

import httpx

logger = logging.getLogger(__name__)

SYNC_EVERY_MINUTES = 60
CLAIM_MINUTES = 12            # a claimed person is not picked again for this long (covers a crash mid-sync)
JOB_TIMEOUT_SECONDS = 240
BASE_BACKOFF_MINUTES = 5
MAX_BACKOFF_MINUTES = 360
DEFAULT_BATCH = 30
DEFAULT_CONCURRENCY = 3
OVERDUE_GRACE_MINUTES = 120

SyncFn = Callable[[str, list[dict]], Awaitable[dict]]
_tasks: set[asyncio.Task] = set()  # keeps background batches from being garbage-collected mid-run


def stagger_minutes(user_id: str) -> int:
    """Where in the hour this person starts, so not everyone is due at once."""
    return int(hashlib.sha256(user_id.encode()).hexdigest(), 16) % SYNC_EVERY_MINUTES


def backoff_minutes(fail_count: int) -> int:
    """How long to wait after the nth failure in a row: 5, 10, 20, 40 ... up to six hours."""
    return min(MAX_BACKOFF_MINUTES, BASE_BACKOFF_MINUTES * (2 ** max(0, fail_count - 1)))


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


async def ensure_rows(user_ids: list[str], now: datetime) -> bool:
    """Make sure each person has a sync_state row (new people start at their staggered time).
    False when the table isn't there yet or can't be reached, so the caller can use the old way."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            existing = await client.get(_sb_url("sync_state"), headers=_sb_headers(), params={"select": "user_id", "limit": "100000"})
            existing.raise_for_status()
            have = {r["user_id"] for r in (existing.json() or [])}
            missing = [u for u in user_ids if u not in have]
            if missing:
                rows = [{"user_id": u, "next_sync_at": _iso(now + timedelta(minutes=stagger_minutes(u)))} for u in missing]
                created = await client.post(
                    _sb_url("sync_state"), headers=_sb_headers("resolution=ignore-duplicates,return=minimal"),
                    params={"on_conflict": "user_id"}, json=rows,
                )
                created.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("Sync queue table unavailable (using the old sync): %s", exc)
        return False


async def claim_due(user_ids: set[str], limit: int, now: datetime) -> tuple[list[dict], int]:
    """Claim up to `limit` of the connected people whose sync is due. Returns (claimed rows, how many were due)."""
    stamp = _iso(now)
    not_claimed = f"(claimed_until.is.null,claimed_until.lt.{stamp})"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            _sb_url("sync_state"), headers=_sb_headers(),
            params={"next_sync_at": f"lte.{stamp}", "or": not_claimed, "order": "next_sync_at.asc", "select": "user_id,fail_count", "limit": "1000"},
        )
        resp.raise_for_status()
        due = [r for r in (resp.json() or []) if r["user_id"] in user_ids]
        claimed: list[dict] = []
        for row in due:
            if len(claimed) >= limit:
                break
            # One conditional update per person: it only succeeds if nobody else claimed them in the meantime.
            took = await client.patch(
                _sb_url("sync_state"), headers=_sb_headers("return=representation"),
                params={"user_id": f"eq.{row['user_id']}", "or": not_claimed},
                json={"claimed_until": _iso(now + timedelta(minutes=CLAIM_MINUTES))},
            )
            took.raise_for_status()
            if took.json():
                claimed.append(row)
    return claimed, len(due)


async def finish(user_id: str, ok: bool, previous_failures: int, now: datetime, error: Optional[str] = None) -> None:
    fails = 0 if ok else previous_failures + 1
    wait = SYNC_EVERY_MINUTES if ok else backoff_minutes(fails)
    payload: dict = {"next_sync_at": _iso(now + timedelta(minutes=wait)), "claimed_until": None, "fail_count": fails, "last_error": None if ok else (error or "")[:300]}
    if ok:
        payload["last_ok_at"] = _iso(now)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.patch(_sb_url("sync_state"), headers=_sb_headers("return=minimal"), params={"user_id": f"eq.{user_id}"}, json=payload)
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("Recording a sync result failed for %s: %s", user_id[:8], exc)


async def touch(user_id: str) -> None:
    """A sync just happened for some other reason (app opened, Apple Health upload): push their next one back an hour."""
    now = datetime.now(timezone.utc)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                _sb_url("sync_state"), headers=_sb_headers("resolution=merge-duplicates,return=minimal"),
                params={"on_conflict": "user_id"},
                json=[{"user_id": user_id, "next_sync_at": _iso(now + timedelta(minutes=SYNC_EVERY_MINUTES)), "last_ok_at": _iso(now), "fail_count": 0}],
            )
            resp.raise_for_status()
    except Exception:
        pass  # best effort; the table may not exist yet


async def overdue_count(now: Optional[datetime] = None) -> Optional[int]:
    """
    How many people with a connected device or app are more than OVERDUE_GRACE_MINUTES past due, or None if the queue
    isn't set up. Someone who has disconnected everything keeps an old row but is never synced, so they don't count.
    """
    now = now or datetime.now(timezone.utc)
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                _sb_url("sync_state"), headers=_sb_headers(),
                params={"next_sync_at": f"lt.{_iso(now - timedelta(minutes=OVERDUE_GRACE_MINUTES))}", "select": "user_id", "limit": "1000"},
            )
            resp.raise_for_status()
            late = {r["user_id"] for r in (resp.json() or [])}
            if not late:
                return 0
            conns = await client.get(
                _sb_url("user_connections"), headers=_sb_headers(),
                params={"is_active": "eq.true", "select": "user_id", "limit": "100000"},
            )
            conns.raise_for_status()
            connected = {r["user_id"] for r in (conns.json() or [])}
            return len(late & connected)
    except Exception:
        return None


async def process_claimed(claimed: list[dict], connections_by_user: dict[str, list[dict]], sync_fn: SyncFn, concurrency: int = DEFAULT_CONCURRENCY) -> dict:
    """Sync the claimed people a few at a time, each with a time limit, and record how each went."""
    gate = asyncio.Semaphore(max(1, concurrency))
    tally = {"ok": 0, "failed": 0}

    async def one(row: dict) -> None:
        user_id = row["user_id"]
        async with gate:
            error: Optional[str] = None
            ok = False
            try:
                result = await asyncio.wait_for(sync_fn(user_id, connections_by_user.get(user_id, [])), timeout=JOB_TIMEOUT_SECONDS)
                ok = (result or {}).get("status") != "engine_error"
                if not ok:
                    error = str((result or {}).get("error", "engine error"))
            except asyncio.TimeoutError:
                error = "timed out"
            except Exception as exc:  # one person's failure must not stop the others
                error = f"{type(exc).__name__}: {exc}"
            tally["ok" if ok else "failed"] += 1
            if not ok:
                logger.error("SYNC_QUEUE_FAILED user=%s error=%s", user_id[:8], error)
            await finish(user_id, ok, int(row.get("fail_count") or 0), datetime.now(timezone.utc), error)

    await asyncio.gather(*(one(r) for r in claimed))
    return tally


async def start_batch(connections_by_user: dict[str, list[dict]], sync_fn: SyncFn, limit: int = DEFAULT_BATCH, concurrency: int = DEFAULT_CONCURRENCY, now: Optional[datetime] = None) -> Optional[dict]:
    """
    Claim whoever is due and sync them in the background. Returns straight away with how many were claimed and
    how many are still waiting, or None when the queue table isn't available (use the old way then).
    """
    now = now or datetime.now(timezone.utc)
    user_ids = list(connections_by_user)
    if not await ensure_rows(user_ids, now):
        return None
    claimed, due_total = await claim_due(set(user_ids), limit, now)
    if claimed:
        task = asyncio.create_task(process_claimed(claimed, connections_by_user, sync_fn, concurrency))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)
    return {"mode": "queue", "connected": len(user_ids), "due": due_total, "claimed": len(claimed), "waiting": due_total - len(claimed)}

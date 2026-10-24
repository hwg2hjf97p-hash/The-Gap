"""
Stops a person's manual syncs piling up.

Tapping Refresh, the refresh every five minutes while Home is open, and pulling the page down all end up here, and each one runs
the whole pipeline (fetch from the connected devices, then the analysis). The app limits how often it asks, but a server shouldn't
rely on that: this refuses a second sync while one is still running for the same person, or one that comes within a few seconds of
the last, and says so instead of doing the work again. The scheduled hourly sync is separate and not affected.

Kept in this process's memory, which is right while the server is a single process (a restart just forgets it).
"""

from __future__ import annotations

import time
from typing import Optional

MIN_GAP_SECONDS = 15
_MAX_TRACKED = 5000

_last_finished: dict[str, float] = {}
_running: set[str] = set()


def check(user_id: str, now: Optional[float] = None) -> Optional[dict]:
    """None if a sync may start now; otherwise what to tell the app instead of syncing."""
    now = time.monotonic() if now is None else now
    if user_id in _running:
        return {"status": "running"}
    last = _last_finished.get(user_id)
    if last is not None and now - last < MIN_GAP_SECONDS:
        return {"status": "recent", "seconds_ago": int(now - last)}
    return None


def start(user_id: str) -> None:
    _running.add(user_id)


def finish(user_id: str, now: Optional[float] = None) -> None:
    _running.discard(user_id)
    _last_finished[user_id] = time.monotonic() if now is None else now
    if len(_last_finished) > _MAX_TRACKED:
        # Forget the oldest half rather than grow for ever.
        for key, _ in sorted(_last_finished.items(), key=lambda kv: kv[1])[: _MAX_TRACKED // 2]:
            _last_finished.pop(key, None)

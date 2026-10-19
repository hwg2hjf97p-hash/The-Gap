"""
The server's own clock for syncing.

GitHub's scheduled workflows are best-effort: in practice the "every 4 hours" sync ran every 6 to 9 hours, and
none ran for two days. So the server also checks for due syncs itself, every few minutes, while it is running.
It uses the same queue as the external trigger (utils/sync_queue.py), whose claims are atomic, so the two can
never sync the same person twice. Set DISABLE_SCHEDULER=1 to turn this off.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from utils import sync_queue

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 300
FIRST_DELAY_SECONDS = 60

LoadFn = Callable[[], Awaitable[list[dict]]]


async def run_due_once(load_connections: Optional[LoadFn] = None, sync_fn: Optional[sync_queue.SyncFn] = None) -> Optional[dict]:
    """One pass: claim whoever is due and start syncing them in the background. None if the queue table isn't set up."""
    if load_connections is None or sync_fn is None:
        from sync import daily_sync  # imported here: it pulls in the whole analysis pipeline

        async def _load() -> list[dict]:
            return await daily_sync._supabase_get("user_connections", {"is_active": "eq.true", "select": "*"})

        load_connections = load_connections or _load
        sync_fn = sync_fn or daily_sync._sync_user

    users: dict[str, list[dict]] = {}
    for conn in await load_connections():
        users.setdefault(conn["user_id"], []).append(conn)
    if not users:
        return {"mode": "queue", "connected": 0, "claimed": 0}
    return await sync_queue.start_batch(users, sync_fn)


async def scheduler_loop(interval_seconds: float = INTERVAL_SECONDS, first_delay_seconds: float = FIRST_DELAY_SECONDS) -> None:
    await asyncio.sleep(first_delay_seconds)  # let the server finish starting
    while True:
        try:
            summary = await run_due_once()
            if summary and summary.get("claimed"):
                logger.info("SCHEDULER claimed=%s due=%s connected=%s", summary.get("claimed"), summary.get("due"), summary.get("connected"))
            from utils.push import flush_queue

            await flush_queue()  # pushes held during quiet hours that are now due
            from utils.provider_caps import notify_open

            await notify_open()  # tell people waiting for a full service that there is room now
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # the loop must never die
            logger.warning("Scheduler pass failed (will try again): %s", exc)
        await asyncio.sleep(interval_seconds)

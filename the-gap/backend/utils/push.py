"""
Push notification sending via Expo's push API — the app is Expo/React
Native, so Expo's own push service (which relays to APNs for us) is the
simplest path, with no separate Apple push certificate to manage.

Table DDL (run once in Supabase SQL editor):
  CREATE TABLE IF NOT EXISTS push_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    expo_push_token TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, expo_push_token)
  );
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import httpx

from utils.quiet_hours import in_quiet_hours

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


async def _get_tokens_for_user(user_id: str) -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _sb_url("push_tokens"),
                headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "select": "expo_push_token"},
            )
            resp.raise_for_status()
            return [r["expo_push_token"] for r in (resp.json() or [])]
    except Exception as exc:
        logger.warning("Fetching push tokens failed for %s: %s", user_id[:8], exc)
        return []


async def get_prefs(user_id: str) -> dict | None:
    """The person's time zone and quiet hours, or None if they haven't set any
    (or the table isn't there yet)."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _sb_url("notification_prefs"),
                headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "select": "tz,quiet_start,quiet_end", "limit": "1"},
            )
            resp.raise_for_status()
            rows = resp.json() or []
            return rows[0] if rows else None
    except Exception as exc:
        logger.warning("Notification prefs lookup failed for %s: %s", user_id[:8], exc)
        return None


def _quiet_now(prefs: dict | None) -> bool:
    if not prefs:
        return False
    start = prefs.get("quiet_start")
    end = prefs.get("quiet_end")
    return in_quiet_hours(
        datetime.now(timezone.utc),
        prefs.get("tz"),
        float(22 if start is None else start),
        float(7 if end is None else end),
    )


async def _enqueue(user_id: str, title: str, body: str, data: dict | None) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                _sb_url("push_queue"),
                headers=_sb_headers("return=minimal"),
                json={"user_id": user_id, "title": title, "body": body, "data": data or {}},
            )
            resp.raise_for_status()
            return True
    except Exception as exc:
        logger.warning("Queueing a push failed for %s: %s", user_id[:8], exc)
        return False


async def send_push(user_id: str, title: str, body: str, data: dict | None = None, respect_quiet: bool = True) -> None:
    """
    Best-effort push to every device this user has registered. Never raises —
    a failed push shouldn't ever take down the sync/engine run that triggered it.

    During the person's quiet hours the push is held and sent by flush_queue()
    once they're past it, rather than waking them.
    """
    if respect_quiet and _quiet_now(await get_prefs(user_id)):
        if await _enqueue(user_id, title, body, data):
            logger.info("PUSH_HELD user=%s title=%r", user_id[:8], title)
        return

    tokens = await _get_tokens_for_user(user_id)
    if not tokens:
        return

    messages = [
        {"to": token, "title": title, "body": body, "data": data or {}, "sound": "default"}
        for token in tokens
    ]

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(EXPO_PUSH_URL, json=messages, headers={"Content-Type": "application/json"})
            resp.raise_for_status()
            logger.info("PUSH_SENT user=%s count=%d title=%r", user_id[:8], len(tokens), title)
    except Exception as exc:
        logger.warning("Push send failed for %s: %s", user_id[:8], exc)


QUEUE_MAX_AGE_HOURS = 24
MAX_SENT_PER_PERSON_AFTER_QUIET = 3


async def flush_queue() -> int:
    """Send held pushes to people who are no longer in quiet hours. Anything
    older than a day is dropped as stale. Returns how many were sent. Never raises."""
    sent = 0
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=QUEUE_MAX_AGE_HOURS)).isoformat()
        async with httpx.AsyncClient(timeout=15) as client:
            await client.delete(_sb_url("push_queue"), headers=_sb_headers("return=minimal"), params={"created_at": f"lt.{cutoff}"})
            resp = await client.get(
                _sb_url("push_queue"), headers=_sb_headers(),
                params={"select": "id,user_id,title,body,data", "order": "created_at.asc", "limit": "500"},
            )
            resp.raise_for_status()
            rows = resp.json() or []

            by_user: dict[str, list[dict]] = {}
            for r in rows:
                by_user.setdefault(r["user_id"], []).append(r)

            for user_id, items in by_user.items():
                if _quiet_now(await get_prefs(user_id)):
                    continue
                # Several at once would be a pile-up: send only the newest few.
                for item in items[-MAX_SENT_PER_PERSON_AFTER_QUIET:]:
                    await send_push(user_id, item["title"], item["body"], item.get("data"), respect_quiet=False)
                    sent += 1
                ids = ",".join(str(i["id"]) for i in items)
                await client.delete(_sb_url("push_queue"), headers=_sb_headers("return=minimal"), params={"id": f"in.({ids})"})
    except Exception as exc:
        logger.warning("Flushing the push queue failed: %s", exc)
    return sent

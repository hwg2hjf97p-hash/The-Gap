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

# The person decides which notifications from The Gap they get. Each kind below sits behind one of their switches
# (notification_prefs.push_kinds, see phase29.sql) and stays OFF until they turn it on. A kind not listed here is not
# held back by this: a test notification, and a coach heads-up, which has its own switch.
PUSH_SWITCHES = ("findings", "recap", "followups", "connections")
PUSH_KIND_SWITCH = {
    "discovery": "findings",
    "proactive_nudge": "findings",
    "digest": "recap",
    "intervention_followup": "followups",
    "connection_expired": "connections",
    "connection_open": "connections",
}


def kind_allowed(prefs: dict | None, kind: str | None) -> bool:
    """False for a gated kind of notification the person hasn't switched on (the default)."""
    switch = PUSH_KIND_SWITCH.get(kind or "")
    if switch is None:
        return True
    return ((prefs or {}).get("push_kinds") or {}).get(switch) is True


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
            for select in ("tz,quiet_start,quiet_end,push_kinds", "tz,quiet_start,quiet_end"):
                resp = await client.get(
                    _sb_url("notification_prefs"),
                    headers=_sb_headers(),
                    params={"user_id": f"eq.{user_id}", "select": select, "limit": "1"},
                )
                if resp.status_code == 400 and "push_kinds" in select:
                    continue  # phase29.sql hasn't been run yet: read what's there without it
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


EXPO_RECEIPTS_URL = "https://exp.host/--/api/v2/push/getReceipts"


def read_tickets(tokens: list[str], tickets: list[dict]) -> dict:
    """
    What Expo said about each message: how many it accepted, the plain-words problems, the ticket ids (to ask about
    delivery later) and which tokens belong to a phone that is gone (to forget them).
    """
    accepted, errors, ids, dead = 0, [], [], []
    for token, ticket in zip(tokens, tickets):
        if ticket.get("status") == "ok":
            accepted += 1
            if ticket.get("id"):
                ids.append(ticket["id"])
            continue
        code = (ticket.get("details") or {}).get("error") or "error"
        errors.append(f"{code}: {ticket.get('message', '')}".strip())
        if code == "DeviceNotRegistered":
            dead.append(token)
    return {"accepted": accepted, "errors": errors, "ticket_ids": ids, "dead_tokens": dead}


async def _forget_tokens(user_id: str, tokens: list[str]) -> None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            for token in tokens:
                await client.delete(_sb_url("push_tokens"), headers=_sb_headers("return=minimal"), params={"user_id": f"eq.{user_id}", "expo_push_token": f"eq.{token}"})
    except Exception as exc:
        logger.warning("Forgetting dead push tokens failed for %s: %s", user_id[:8], exc)


async def get_receipts(ticket_ids: list[str]) -> dict:
    """Expo's later word on delivery (for example a bad Apple key shows up here, not in the first answer)."""
    if not ticket_ids:
        return {}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(EXPO_RECEIPTS_URL, json={"ids": ticket_ids}, headers={"Content-Type": "application/json"})
            resp.raise_for_status()
            return (resp.json() or {}).get("data") or {}
    except Exception as exc:
        logger.warning("Fetching push receipts failed: %s", exc)
        return {}


async def send_push_detailed(user_id: str, title: str, body: str, data: dict | None = None, respect_quiet: bool = True) -> dict:
    """send_push, but telling the caller what happened: {"held", "tokens", "accepted", "errors", "ticket_ids"}. Never raises."""
    result: dict = {"held": False, "tokens": 0, "accepted": 0, "errors": [], "ticket_ids": []}
    prefs = await get_prefs(user_id)
    if not kind_allowed(prefs, (data or {}).get("kind")):
        logger.info("PUSH_OFF user=%s kind=%s (this person hasn't switched that notification on)", user_id[:8], (data or {}).get("kind"))
        result["off"] = True
        return result
    if respect_quiet and _quiet_now(prefs):
        if await _enqueue(user_id, title, body, data):
            logger.info("PUSH_HELD user=%s title=%r", user_id[:8], title)
        result["held"] = True
        return result

    tokens = await _get_tokens_for_user(user_id)
    result["tokens"] = len(tokens)
    if not tokens:
        logger.info("PUSH_NO_TOKEN user=%s title=%r (this person has no phone registered for notifications)", user_id[:8], title)
        return result

    messages = [{"to": token, "title": title, "body": body, "data": data or {}, "sound": "default"} for token in tokens]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(EXPO_PUSH_URL, json=messages, headers={"Content-Type": "application/json"})
            resp.raise_for_status()
            tickets = (resp.json() or {}).get("data") or []
    except Exception as exc:
        logger.warning("Push send failed for %s: %s", user_id[:8], exc)
        result["errors"].append(f"send failed: {exc}")
        return result

    read = read_tickets(tokens, tickets)
    result.update({k: read[k] for k in ("accepted", "errors", "ticket_ids")})
    if read["dead_tokens"]:
        await _forget_tokens(user_id, read["dead_tokens"])
    for problem in read["errors"]:
        logger.warning("PUSH_TICKET_ERROR user=%s %s", user_id[:8], problem)
    logger.info("PUSH_SENT user=%s tokens=%d accepted=%d title=%r", user_id[:8], len(tokens), read["accepted"], title)
    return result


async def send_push(user_id: str, title: str, body: str, data: dict | None = None, respect_quiet: bool = True) -> None:
    """
    Best-effort push to every device this user has registered. Never raises —
    a failed push shouldn't ever take down the sync/engine run that triggered it.

    During the person's quiet hours the push is held and sent by flush_queue()
    once they're past it, rather than waking them.
    """
    await send_push_detailed(user_id, title, body, data, respect_quiet)


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

"""
Member limits on connected services, and a "tell me when it opens" list.

Whoop and Oura only let an app connect 10 people until the app is approved for more (Strava is similar). Past the limit
the service refuses the sign-in, which looks like a bug to the person. So The Gap counts its own connections first and,
when a service is full, the app says so plainly and offers Apple Health instead, plus a notice when room opens.

Limits are in Render environment variables, so raising one after approval needs no code change:
  WHOOP_USER_CAP, OURA_USER_CAP, STRAVA_USER_CAP, WITHINGS_USER_CAP, POLAR_USER_CAP
A service with no variable uses CAP_DEFAULTS (10 for Whoop and Oura); "0" or "none" means no limit.

The waitlist is the provider_waitlist table (phase15.sql). Until it exists the list simply doesn't save and nothing breaks.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

CAP_DEFAULTS: dict[str, Optional[int]] = {"whoop": 10, "oura": 10}
CAPPED_PROVIDERS = ("whoop", "oura", "strava", "withings", "polar")
DISPLAY = {"whoop": "Whoop", "oura": "Oura", "strava": "Strava", "withings": "Withings", "polar": "Polar"}


def cap_for(provider: str) -> Optional[int]:
    """How many people may be connected to this service, or None for no limit."""
    raw = os.getenv(f"{provider.upper()}_USER_CAP", "").strip().lower()
    if raw in ("0", "none", "unlimited"):
        return None
    if raw.isdigit():
        return int(raw)
    return CAP_DEFAULTS.get(provider)


def has_room(cap: Optional[int], connected_users: set[str], user_id: str) -> bool:
    """Someone already connected can always reconnect; otherwise there must be a free place."""
    if cap is None or user_id in connected_users:
        return True
    return len(connected_users) < cap


def _sb_url(table: str) -> str:
    return f"{os.getenv('SUPABASE_URL', '').strip().rstrip('/')}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


async def connected_users(provider: str) -> set[str]:
    """Everyone with an active connection to this service."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            _sb_url("user_connections"), headers=_sb_headers(),
            params={"provider": f"eq.{provider}", "is_active": "eq.true", "select": "user_id", "limit": "100000"},
        )
        resp.raise_for_status()
        return {r["user_id"] for r in (resp.json() or [])}


async def is_full_for(user_id: str, provider: str) -> bool:
    """True when this service is at its limit and this person isn't already one of the connected. Fails open: a database error never blocks a connection."""
    cap = cap_for(provider)
    if cap is None:
        return False
    try:
        return not has_room(cap, await connected_users(provider), user_id)
    except Exception as exc:
        logger.warning("Capacity check failed for %s (allowing the connection): %s", provider, exc)
        return False


async def waiting_providers(user_id: str) -> set[str]:
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                _sb_url("provider_waitlist"), headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "notified_at": "is.null", "select": "provider"},
            )
            resp.raise_for_status()
            return {r["provider"] for r in (resp.json() or [])}
    except Exception:
        return set()


async def capacity_for(user_id: str) -> dict[str, dict]:
    """For each service that has a limit: is it full for this person, and are they on its waiting list."""
    waiting = await waiting_providers(user_id)
    out: dict[str, dict] = {}
    for provider in CAPPED_PROVIDERS:
        if cap_for(provider) is None:
            continue
        out[provider] = {"name": DISPLAY[provider], "full": await is_full_for(user_id, provider), "waiting": provider in waiting}
    return out


async def join_waitlist(user_id: str, provider: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.post(
                _sb_url("provider_waitlist"), headers=_sb_headers("resolution=merge-duplicates,return=minimal"),
                params={"on_conflict": "user_id,provider"},
                json={"user_id": user_id, "provider": provider, "notified_at": None},
            )
            resp.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("Waitlist save failed for %s/%s: %s", user_id[:8], provider, exc)
        return False


async def notify_open() -> dict[str, int]:
    """
    For each limited service that now has room, tell as many waiting people as there are free places (first in line first)
    that it is open, and mark them told. Best effort and quiet: any problem just means trying again next pass.
    """
    from utils.push import send_push

    told: dict[str, int] = {}
    for provider in CAPPED_PROVIDERS:
        cap = cap_for(provider)
        if cap is None:
            continue
        try:
            connected = await connected_users(provider)
            room = cap - len(connected)
            if room <= 0:
                continue
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    _sb_url("provider_waitlist"), headers=_sb_headers(),
                    params={"provider": f"eq.{provider}", "notified_at": "is.null", "select": "user_id", "order": "created_at.asc", "limit": str(room)},
                )
                resp.raise_for_status()
                people = [r["user_id"] for r in (resp.json() or []) if r["user_id"] not in connected]
                for user_id in people:
                    name = DISPLAY[provider]
                    await send_push(
                        user_id, f"{name} connections are open",
                        f"There's room to connect {name} to The Gap now. Open Settings, then Connections.",
                        data={"kind": "connection_open", "provider": provider},
                    )
                    mark = await client.patch(
                        _sb_url("provider_waitlist"), headers=_sb_headers("return=minimal"),
                        params={"user_id": f"eq.{user_id}", "provider": f"eq.{provider}"},
                        json={"notified_at": datetime.now(timezone.utc).isoformat()},
                    )
                    mark.raise_for_status()
                if people:
                    told[provider] = len(people)
        except Exception as exc:
            logger.debug("Waitlist notice for %s skipped: %s", provider, exc)
    return told

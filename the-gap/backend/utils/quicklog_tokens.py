"""
The key behind Siri and Shortcuts logging.

Siri can't use the person's normal login (its refresh tokens are single-use, so
refreshing one from Siri could log them out of the app). Instead the app asks
the server for a separate "quick-log" key after sign-in and keeps it in the
iPhone's Keychain. That key can only do one thing: add a quick log for that
person. It is revocable, only a one-way hash of it is stored here, and it is
removed on sign-out and when the account is deleted.

Table DDL: see phase11.sql (quick_log_tokens).
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

PREFIX = "qlt_"
RATE_LIMIT = 100          # quick logs per hour per person
RATE_WINDOW_SECONDS = 3600
MIN_TOKEN_LENGTH = 40
_TOUCH_EVERY_SECONDS = 600

_recent: dict[str, deque] = defaultdict(deque)
_last_touched: dict[str, float] = {}


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


def new_token() -> str:
    return PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def looks_like_token(token: str) -> bool:
    return token.startswith(PREFIX) and len(token) >= MIN_TOKEN_LENGTH and token.isascii()


def rate_limited(user_id: str, now: Optional[float] = None) -> bool:
    """True when this person has already used up their quick logs for the hour. Counts the attempt otherwise."""
    now = time.time() if now is None else now
    window = _recent[user_id]
    while window and now - window[0] > RATE_WINDOW_SECONDS:
        window.popleft()
    if len(window) >= RATE_LIMIT:
        return True
    window.append(now)
    return False


async def mint(user_id: str, label: str) -> str:
    """A new key for this person's device. An older key for the same device is revoked first. The key is returned once and never stored."""
    token = new_token()
    now = datetime.now(timezone.utc).isoformat()
    async with httpx.AsyncClient(timeout=15) as client:
        revoke = await client.patch(
            _sb_url("quick_log_tokens"),
            headers=_sb_headers("return=minimal"),
            params={"user_id": f"eq.{user_id}", "label": f"eq.{label}", "revoked_at": "is.null"},
            json={"revoked_at": now},
        )
        revoke.raise_for_status()
        created = await client.post(
            _sb_url("quick_log_tokens"),
            headers=_sb_headers("return=minimal"),
            json={"user_id": user_id, "token_hash": hash_token(token), "label": label},
        )
        created.raise_for_status()
    return token


async def revoke_all(user_id: str, label: Optional[str] = None) -> None:
    params = {"user_id": f"eq.{user_id}", "revoked_at": "is.null"}
    if label:
        params["label"] = f"eq.{label}"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.patch(_sb_url("quick_log_tokens"), headers=_sb_headers("return=minimal"), params=params, json={"revoked_at": datetime.now(timezone.utc).isoformat()})
        resp.raise_for_status()


async def user_for_token(token: str) -> Optional[str]:
    """Whose key this is, or None when it isn't a live key (unknown, malformed or revoked)."""
    if not looks_like_token(token):
        return None
    digest = hash_token(token)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _sb_url("quick_log_tokens"),
                headers=_sb_headers(),
                params={"token_hash": f"eq.{digest}", "revoked_at": "is.null", "select": "id,user_id,use_count", "limit": "1"},
            )
            resp.raise_for_status()
            rows = resp.json() or []
            if not rows:
                return None
            row = rows[0]
            # Noting use is for the person's benefit (a "last used" they can see), so it is best effort and not every call.
            now = time.time()
            if now - _last_touched.get(digest, 0.0) > _TOUCH_EVERY_SECONDS:
                _last_touched[digest] = now
                await client.patch(
                    _sb_url("quick_log_tokens"),
                    headers=_sb_headers("return=minimal"),
                    params={"id": f"eq.{row['id']}"},
                    json={"last_used_at": datetime.now(timezone.utc).isoformat(), "use_count": int(row.get("use_count") or 0) + 1},
                )
            return row["user_id"]
    except Exception as exc:
        logger.warning("Quick-log key lookup failed: %s", exc)
        return None

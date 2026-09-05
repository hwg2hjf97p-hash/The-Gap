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

import httpx

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


async def send_push(user_id: str, title: str, body: str, data: dict | None = None) -> None:
    """
    Best-effort push to every device this user has registered. Never raises —
    a failed push shouldn't ever take down the sync/engine run that triggered it.
    """
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

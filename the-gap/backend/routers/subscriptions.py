"""
RevenueCat subscription webhook — keeps a Supabase mirror of each user's
entitlement so the backend can check subscription status itself (defense
in depth beyond the app-side paywall gate), without ever calling out to
RevenueCat's API on the hot path.

Table DDL (run once in Supabase SQL editor):
  CREATE TABLE IF NOT EXISTS user_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT false,
    product_id TEXT,
    expires_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW()
  );

Configure this endpoint's URL in the RevenueCat dashboard (Project Settings
-> Integrations -> Webhooks), and set the same secret you enter there as
this backend's REVENUECAT_WEBHOOK_SECRET env var — RevenueCat sends it
back as "Authorization: Bearer <secret>" on every webhook call.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

REVENUECAT_WEBHOOK_SECRET = os.getenv("REVENUECAT_WEBHOOK_SECRET", "")

# Event types that mean "this user should have active access right now".
# CANCELLATION means the user turned off auto-renew but keeps access until
# their current period's expiry — EXPIRATION is the event that actually
# ends access, so CANCELLATION alone must not flip is_active off.
ACTIVE_EVENT_TYPES = {
    "INITIAL_PURCHASE", "RENEWAL", "UNCANCELLATION", "PRODUCT_CHANGE",
    "NON_RENEWING_PURCHASE", "SUBSCRIPTION_EXTENDED", "TRANSFER",
    "CANCELLATION", "BILLING_ISSUE",
}
INACTIVE_EVENT_TYPES = {"EXPIRATION"}


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


@router.post("/webhook")
async def revenuecat_webhook(request_body: dict, authorization: str = Header(default="")) -> JSONResponse:
    if REVENUECAT_WEBHOOK_SECRET and authorization != f"Bearer {REVENUECAT_WEBHOOK_SECRET}":
        raise HTTPException(status_code=401, detail="Invalid webhook secret.")

    event = request_body.get("event") or {}
    event_type = event.get("type", "")
    user_id = event.get("app_user_id")
    if not user_id:
        logger.warning("RevenueCat webhook missing app_user_id: %s", event_type)
        return JSONResponse(content={"status": "ignored"})

    if event_type not in ACTIVE_EVENT_TYPES and event_type not in INACTIVE_EVENT_TYPES:
        logger.info("RC_WEBHOOK_UNHANDLED type=%s user=%s", event_type, user_id[:8])
        return JSONResponse(content={"status": "ignored"})

    is_active = event_type in ACTIVE_EVENT_TYPES
    expires_at_ms = event.get("expiration_at_ms")
    expires_at = (
        datetime.fromtimestamp(expires_at_ms / 1000, tz=timezone.utc).isoformat()
        if expires_at_ms else None
    )

    payload = {
        "user_id": user_id,
        "is_active": is_active,
        "product_id": event.get("product_id"),
        "expires_at": expires_at,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _sb_url("user_subscriptions"),
                headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                params={"on_conflict": "user_id"},
                json=[payload],
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.error("RevenueCat webhook DB write failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Could not record subscription update.")

    logger.info("RC_WEBHOOK_PROCESSED type=%s user=%s is_active=%s", event_type, user_id[:8], is_active)
    return JSONResponse(content={"status": "ok"})


async def is_subscribed(user_id: str) -> bool:
    """Reusable check for any endpoint that wants server-side entitlement
    enforcement in addition to the app's own paywall gate."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _sb_url("user_subscriptions"),
                headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "select": "is_active,expires_at", "limit": 1},
            )
            resp.raise_for_status()
            rows = resp.json() or []
            if not rows:
                return False
            row = rows[0]
            if not row.get("is_active"):
                return False
            expires_at = row.get("expires_at")
            if expires_at and datetime.fromisoformat(expires_at.replace("Z", "+00:00")) < datetime.now(timezone.utc):
                return False
            return True
    except Exception as exc:
        logger.warning("is_subscribed check failed for %s: %s", user_id[:8], exc)
        return False

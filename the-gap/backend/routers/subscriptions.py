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
    period_type TEXT,            -- TRIAL while in the free month, NORMAL once paying (phase12.sql)
    updated_at TIMESTAMPTZ DEFAULT NOW()
  );

Configure this endpoint's URL in the RevenueCat dashboard (Project Settings
-> Integrations -> Webhooks), and set the same secret you enter there as
this backend's REVENUECAT_WEBHOOK_SECRET env var — RevenueCat sends it
back as "Authorization: Bearer <secret>" on every webhook call.
"""

from __future__ import annotations

import hmac
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse

from auth import get_current_user_id

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
    # Fails closed: with no secret configured nothing is accepted, so this
    # can never be used to grant someone an active subscription.
    expected = f"Bearer {REVENUECAT_WEBHOOK_SECRET}"
    if not REVENUECAT_WEBHOOK_SECRET or not hmac.compare_digest(authorization.encode(), expected.encode()):
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

    payload = mirror_payload(event_type, event, user_id)
    is_active = payload["is_active"]

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _sb_url("user_subscriptions"),
                headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                params={"on_conflict": "user_id"},
                json=[payload],
            )
            if resp.status_code == 400 and "period_type" in resp.text:
                # phase12.sql hasn't been run yet: record the rest rather than lose the update.
                payload.pop("period_type", None)
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


def mirror_payload(event_type: str, event: dict, user_id: str) -> dict:
    """The row to keep for a RevenueCat event.

    A PRODUCT_CHANGE (for example someone ending their free month early by
    switching to the same plan without the free month) only says which product
    they are moving to. When the change takes effect RevenueCat sends a
    RENEWAL with the real period and expiry, so a PRODUCT_CHANGE must not
    overwrite those with the old product's values (which could put someone who
    has just started paying back on "free month")."""
    now_iso = datetime.now(timezone.utc).isoformat()
    if event_type == "PRODUCT_CHANGE":
        return {
            "user_id": user_id,
            "is_active": True,
            "product_id": event.get("new_product_id") or event.get("product_id"),
            "updated_at": now_iso,
        }
    expires_at_ms = event.get("expiration_at_ms")
    expires_at = (
        datetime.fromtimestamp(expires_at_ms / 1000, tz=timezone.utc).isoformat()
        if expires_at_ms else None
    )
    return {
        "user_id": user_id,
        "is_active": event_type in ACTIVE_EVENT_TYPES,
        "product_id": event.get("product_id"),
        "expires_at": expires_at,
        "period_type": (event.get("period_type") or "").upper() or None,
        "updated_at": now_iso,
    }


REVENUECAT_API_URL = "https://api.revenuecat.com/v1/subscribers"
ENTITLEMENT_ID = os.getenv("REVENUECAT_ENTITLEMENT", "the_gap_premium")
_last_refresh: dict[str, float] = {}


def parse_subscriber(data: dict, user_id: str, now: Optional[datetime] = None, entitlement: str = "") -> dict:
    """The mirror row for a person, from RevenueCat's own record of them: is the
    entitlement active, on which product, until when, and is it the free month."""
    now = now or datetime.now(timezone.utc)
    subscriber = data.get("subscriber") or {}
    ent = (subscriber.get("entitlements") or {}).get(entitlement or ENTITLEMENT_ID) or {}
    product = ent.get("product_identifier")
    sub = (subscriber.get("subscriptions") or {}).get(product or "", {}) if product else {}
    expires_raw = ent.get("expires_date") or sub.get("expires_date")
    expires_at = None
    active = bool(ent)
    if expires_raw:
        try:
            expires_dt = datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
            expires_at = expires_dt.isoformat()
            active = expires_dt > now
        except ValueError:
            pass
    return {
        "user_id": user_id,
        "is_active": active,
        "product_id": product,
        "expires_at": expires_at,
        "period_type": (sub.get("period_type") or "").upper() or None,
        "updated_at": now.isoformat(),
    }


@router.post("/refresh")
async def refresh_my_subscription(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    """Asks RevenueCat directly what this person's subscription is now and updates our copy.
    The app calls it right after someone ends their free month early, so they get the paid
    allowance at once instead of waiting for RevenueCat's webhook. Needs REVENUECAT_API_KEY
    (RevenueCat's secret API key); without it nothing happens and the webhook is relied on."""
    key = os.getenv("REVENUECAT_API_KEY", "").strip()
    if not key:
        return JSONResponse(content={"refreshed": False, "reason": "not_configured"})
    now = time.time()
    if now - _last_refresh.get(user_id, 0) < 3:
        return JSONResponse(content={"refreshed": False, "reason": "too_soon"})
    _last_refresh[user_id] = now
    if len(_last_refresh) > 5000:
        _last_refresh.clear()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{REVENUECAT_API_URL}/{quote(user_id, safe='')}",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            row = parse_subscriber(resp.json(), user_id)
            write = await client.post(
                _sb_url("user_subscriptions"),
                headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                params={"on_conflict": "user_id"},
                json=[row],
            )
            write.raise_for_status()
    except Exception as exc:
        logger.warning("Subscription refresh failed for %s: %s", user_id[:8], exc)
        return JSONResponse(content={"refreshed": False, "reason": "failed"})
    return JSONResponse(content={"refreshed": True, "period_type": row.get("period_type"), "is_active": row.get("is_active")})


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


async def is_on_trial(user_id: str) -> bool:
    """True while this person is in their free month (a live subscription whose current period is the trial).
    Used to keep the costly features modest for people who haven't paid yet. If it can't be read, they are
    treated as paying: the limit is there to protect spend, not to lock anyone out."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _sb_url("user_subscriptions"),
                headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "select": "is_active,expires_at,period_type", "limit": 1},
            )
            resp.raise_for_status()
            rows = resp.json() or []
    except Exception as exc:
        logger.warning("is_on_trial check failed for %s: %s", user_id[:8], exc)
        return False
    if not rows:
        return False
    row = rows[0]
    if not row.get("is_active") or str(row.get("period_type") or "").upper() != "TRIAL":
        return False
    expires_at = row.get("expires_at")
    if expires_at and datetime.fromisoformat(expires_at.replace("Z", "+00:00")) < datetime.now(timezone.utc):
        return False
    return True

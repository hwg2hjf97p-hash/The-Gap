"""
OAuth connection router for The Gap.
Handles connect/callback flows for Whoop, Oura, and Google Calendar.

Flow:
  1. GET /connect/{provider}        → redirect user to provider OAuth page
  2. GET /connect/{provider}/callback → exchange code for tokens, store in Supabase
  3. GET /connect/status/{user_id}  → return which providers are connected
  4. DELETE /connect/{provider}/{user_id} → disconnect a provider
"""

from __future__ import annotations

import logging
import os
import secrets
import time
from typing import Optional
from urllib.parse import urlencode, urljoin

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse

from db.supabase_client import _get_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/connect")

# ── Provider config ───────────────────────────────────────────────────────────

PROVIDERS = {
    "strava": {
        "auth_url": "https://www.strava.com/oauth/authorize",
        "token_url": "https://www.strava.com/oauth/token",
        "scopes": "read,activity:read_all",
        "client_id_env": "STRAVA_CLIENT_ID",
        "client_secret_env": "STRAVA_CLIENT_SECRET",
    },
    "whoop": {
        "auth_url": "https://api.prod.whoop.com/oauth/oauth2/auth",
        "token_url": "https://api.prod.whoop.com/oauth/oauth2/token",
        "scopes": "offline read:recovery read:sleep read:body_measurement read:profile",
        "client_id_env": "WHOOP_CLIENT_ID",
        "client_secret_env": "WHOOP_CLIENT_SECRET",
    },
    "oura": {
        "auth_url": "https://cloud.ouraring.com/oauth/authorize",
        "token_url": "https://api.ouraring.com/oauth/token",
        "scopes": "daily heartrate personal workout session",
        "client_id_env": "OURA_CLIENT_ID",
        "client_secret_env": "OURA_CLIENT_SECRET",
    },
    "google": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": "https://www.googleapis.com/auth/calendar.readonly",
        "client_id_env": "GOOGLE_CLIENT_ID",
        "client_secret_env": "GOOGLE_CLIENT_SECRET",
    },
}

APP_BASE_URL = os.getenv("APP_BASE_URL", "https://the-gap-production.up.railway.app")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://app.causalme.com")


def _get_provider_config(provider: str) -> dict:
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")
    return PROVIDERS[provider]


def _get_client_credentials(provider: str) -> tuple[str, str]:
    cfg = _get_provider_config(provider)
    client_id = os.getenv(cfg["client_id_env"], "")
    client_secret = os.getenv(cfg["client_secret_env"], "")
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=503,
            detail=f"{provider.title()} integration not yet configured. Coming soon.",
        )
    return client_id, client_secret


def _redirect_uri(provider: str) -> str:
    return f"{APP_BASE_URL}/connect/{provider}/callback"


# ── Stateless signed state tokens ─────────────────────────────────────────────
# Encodes user_id + provider + expiry into the state string using HMAC-SHA256.
# No database or memory store needed — works across all Railway instances.
import hashlib
import hmac
import base64
import json as _json

_STATE_SECRET = (os.getenv("SYNC_SECRET") or "thegap-sync-2026").encode()


def _store_state(state_unused: str, user_id: str, provider: str) -> str:
    """Create a signed state token. Returns the token (ignore state_unused)."""
    # This function signature is kept for compatibility but now returns the token
    payload = _json.dumps({
        "u": user_id,
        "p": provider,
        "e": int(time.time()) + 600,  # expires in 10 min
    }, separators=(",", ":")).encode()
    b64 = base64.urlsafe_b64encode(payload).rstrip(b"=").decode()
    sig = hmac.new(_STATE_SECRET, b64.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{b64}.{sig}"


def _consume_state(state: str) -> Optional[dict]:
    """Verify and decode the signed state token. Returns None if invalid/expired."""
    try:
        parts = state.rsplit(".", 1)
        if len(parts) != 2:
            return None
        b64, sig = parts
        expected_sig = hmac.new(_STATE_SECRET, b64.encode(), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(sig, expected_sig):
            logger.warning("OAuth state signature mismatch")
            return None
        padding = 4 - len(b64) % 4
        payload = _json.loads(base64.urlsafe_b64decode(b64 + "=" * padding))
        if int(time.time()) > payload["e"]:
            logger.warning("OAuth state expired")
            return None
        return {"user_id": payload["u"], "provider": payload["p"]}
    except Exception as exc:
        logger.warning("Could not decode OAuth state: %s", exc)
        return None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/{provider}")
async def start_oauth(
    provider: str,
    user_id: str = Query(..., description="Unique user identifier"),
):
    """Redirect user to provider OAuth page."""
    cfg = _get_provider_config(provider)
    client_id, _ = _get_client_credentials(provider)

    state = _store_state("", user_id, provider)  # stateless signed token

    params = {
        "client_id": client_id,
        "redirect_uri": _redirect_uri(provider),
        "response_type": "code",
        "scope": cfg["scopes"],
        "state": state,
    }

    # Google needs access_type=offline for refresh tokens
    if provider == "google":
        params["access_type"] = "offline"
        params["prompt"] = "consent"

    # Strava needs approval_prompt
    if provider == "strava":
        params["approval_prompt"] = "auto"

    auth_url = cfg["auth_url"] + "?" + urlencode(params)
    logger.info("OAuth start: provider=%s user=%s", provider, user_id)
    return RedirectResponse(url=auth_url)


@router.get("/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: str = Query(...),
    state: str = Query(...),
    error: Optional[str] = Query(None),
):
    """Handle OAuth callback — exchange code for tokens and store."""
    received_at = time.time()
    logger.info("CALLBACK_RECEIVED provider=%s code_length=%d state_length=%d at=%.3f",
                provider, len(code), len(state), received_at)

    if error:
        logger.warning("OAuth error from %s: %s", provider, error)
        return RedirectResponse(
            url=f"{FRONTEND_URL}/connect?error={error}&provider={provider}"
        )

    state_data = _consume_state(state)
    state_decoded_at = time.time()
    logger.info("STATE_DECODED provider=%s elapsed=%.3fs state_valid=%s",
                provider, state_decoded_at - received_at, state_data is not None)

    if not state_data:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state.")

    user_id = state_data["user_id"]
    cfg = _get_provider_config(provider)
    client_id, client_secret = _get_client_credentials(provider)

    # Exchange code for tokens
    try:
        # Strava uses integer client_id
        cid = int(client_id) if provider == "strava" else client_id
        exchange_start = time.time()
        logger.info("TOKEN_EXCHANGE_START provider=%s code_prefix=%s redirect_uri=%s",
                    provider, code[:8], _redirect_uri(provider))
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                cfg["token_url"],
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": _redirect_uri(provider),
                    "client_id": cid,
                    "client_secret": client_secret,
                },
                headers={"Accept": "application/json"},
            )
            logger.info("TOKEN_EXCHANGE_DONE provider=%s status=%d elapsed=%.3fs",
                        provider, resp.status_code, time.time() - exchange_start)
            resp.raise_for_status()
            token_data = resp.json()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text if exc.response is not None else "no response"
        logger.error(
            "Token exchange failed for %s: status=%s body=%s",
            provider, exc.response.status_code if exc.response is not None else "?", body
        )
        return RedirectResponse(
            url=f"{FRONTEND_URL}/connect?error=token_exchange_failed&provider={provider}&detail={exc.response.status_code if exc.response is not None else 0}"
        )
    except httpx.HTTPError as exc:
        logger.error("Token exchange network error for %s: %s", provider, exc)
        return RedirectResponse(
            url=f"{FRONTEND_URL}/connect?error=token_exchange_failed&provider={provider}"
        )

    # Store tokens in Supabase
    try:
        _save_tokens(
            user_id=user_id,
            provider=provider,
            access_token=token_data.get("access_token", ""),
            refresh_token=token_data.get("refresh_token", ""),
            expires_in=token_data.get("expires_in", 3600),
        )
    except Exception as exc:
        logger.error("Token storage failed: %s", exc)
        return RedirectResponse(
            url=f"{FRONTEND_URL}/connect?error=storage_failed&provider={provider}"
        )

    logger.info("OAuth success: provider=%s user=%s", provider, user_id)
    return RedirectResponse(
        url=f"{FRONTEND_URL}/connect?success=true&provider={provider}"
    )


@router.get("/status/{user_id}")
async def connection_status(user_id: str):
    """Return which providers are connected for a user."""
    client = _get_client()
    if client is None:
        return JSONResponse(content={"connected": []})

    try:
        resp = (
            client.table("user_connections")
            .select("provider, connected_at, last_synced_at")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .execute()
        )
        return JSONResponse(content={"connected": resp.data or []})
    except Exception as exc:
        logger.error("Status check failed: %s", exc)
        return JSONResponse(content={"connected": []})


@router.delete("/{provider}/{user_id}")
async def disconnect(provider: str, user_id: str):
    """Disconnect a provider for a user."""
    client = _get_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Database unavailable.")

    try:
        client.table("user_connections").update(
            {"is_active": False}
        ).eq("user_id", user_id).eq("provider", provider).execute()
        return JSONResponse(content={"success": True})
    except Exception as exc:
        logger.error("Disconnect failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not disconnect.")


# ── Token storage helpers ─────────────────────────────────────────────────────

def _save_tokens(
    user_id: str,
    provider: str,
    access_token: str,
    refresh_token: str,
    expires_in: int,
) -> None:
    """Upsert OAuth tokens into Supabase user_connections table."""
    client = _get_client()
    if client is None:
        raise RuntimeError("Supabase unavailable — cannot store tokens.")

    expires_at = int(time.time()) + expires_in

    client.table("user_connections").upsert(
        {
            "user_id": user_id,
            "provider": provider,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
            "is_active": True,
            "connected_at": "now()",
        },
        on_conflict="user_id,provider",
    ).execute()

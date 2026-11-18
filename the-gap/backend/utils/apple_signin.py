"""
Sign in with Apple: removing the link between The Gap and the person's Apple ID when they delete their account.

App Store guideline 5.1.1(v) says an app that offers Sign in with Apple must revoke the person's token with Apple when the account is
deleted, so The Gap stops appearing under "Sign in with Apple" in their Apple ID settings. The way to do it:

  1. When the person deletes their account the app asks Apple for a fresh one-time authorization code (a quick Face ID check).
  2. This server swaps that code for a token at Apple (POST /auth/token), then
  3. tells Apple to revoke that token (POST /auth/revoke).

Nothing is stored: the code is used once, straight away. Both calls need a short-lived "client secret", a signed token made with the
Sign in with Apple key from the Apple Developer account. It is set in Render's environment variables (never in the code):

  APPLE_SIWA_TEAM_ID       the Team ID (10 characters)
  APPLE_SIWA_KEY_ID        the Key ID of the Sign in with Apple key (10 characters)
  APPLE_SIWA_PRIVATE_KEY   the whole contents of the downloaded .p8 file (newlines may be written as \\n)
  APPLE_SIWA_CLIENT_ID     optional; the app's bundle id, default com.causalme.thegap

Until those are set, revoking is skipped (and logged), and deleting the account carries on as before. A failure here never stops the
deletion: the person's data must always be deleted.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

APPLE_AUDIENCE = "https://appleid.apple.com"
TOKEN_URL = f"{APPLE_AUDIENCE}/auth/token"
REVOKE_URL = f"{APPLE_AUDIENCE}/auth/revoke"
DEFAULT_CLIENT_ID = "com.causalme.thegap"
MAX_CODE_CHARS = 2000


def _settings() -> tuple[str, str, str, str]:
    return (
        os.getenv("APPLE_SIWA_TEAM_ID", "").strip(),
        os.getenv("APPLE_SIWA_KEY_ID", "").strip(),
        os.getenv("APPLE_SIWA_PRIVATE_KEY", "").replace("\\n", "\n").strip(),
        os.getenv("APPLE_SIWA_CLIENT_ID", "").strip() or DEFAULT_CLIENT_ID,
    )


def configured() -> bool:
    team, key_id, key, _ = _settings()
    return bool(team and key_id and key)


def client_secret(now: Optional[float] = None) -> str:
    """The signed token Apple asks for with every call. Valid for five minutes, which is all a revoke needs."""
    import jwt  # PyJWT, with the cryptography package for ES256

    team, key_id, key, client_id = _settings()
    issued = int(now if now is not None else time.time())
    claims = {"iss": team, "iat": issued, "exp": issued + 300, "aud": APPLE_AUDIENCE, "sub": client_id}
    return jwt.encode(claims, key, algorithm="ES256", headers={"kid": key_id})


async def revoke_with_code(code: Optional[str]) -> str:
    """
    Swaps the one-time code for a token and revokes it. Returns "revoked", "no_code" (the app sent none), "not_configured" or "failed".
    Never raises.
    """
    code = (code or "").strip()
    if not code or len(code) > MAX_CODE_CHARS:
        return "no_code"
    if not configured():
        logger.warning("APPLE_REVOKE_SKIPPED the Sign in with Apple key isn't set up (see utils/apple_signin.py)")
        return "not_configured"
    try:
        _, _, _, client_id = _settings()
        secret = client_secret()
        async with httpx.AsyncClient(timeout=15) as client:
            token_resp = await client.post(
                TOKEN_URL,
                data={"client_id": client_id, "client_secret": secret, "code": code, "grant_type": "authorization_code"},
            )
            if token_resp.status_code != 200:
                logger.error("APPLE_REVOKE_TOKEN_FAILED status=%s body=%s", token_resp.status_code, token_resp.text[:200])
                return "failed"
            body = token_resp.json() or {}
            token, hint = (body.get("refresh_token"), "refresh_token") if body.get("refresh_token") else (body.get("access_token"), "access_token")
            if not token:
                logger.error("APPLE_REVOKE_NO_TOKEN Apple returned neither a refresh nor an access token")
                return "failed"
            revoke_resp = await client.post(
                REVOKE_URL,
                data={"client_id": client_id, "client_secret": secret, "token": token, "token_type_hint": hint},
            )
            if revoke_resp.status_code != 200:
                logger.error("APPLE_REVOKE_FAILED status=%s body=%s", revoke_resp.status_code, revoke_resp.text[:200])
                return "failed"
        return "revoked"
    except Exception as exc:
        logger.error("APPLE_REVOKE_ERROR %s", exc)
        return "failed"

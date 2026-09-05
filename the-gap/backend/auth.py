"""
Real user authentication — verifies a Supabase session token and returns the
verified user id, replacing the old model where every endpoint just trusted
whatever `user_id` the client handed it (a random UUID it generated itself).

Uses the same direct-httpx-REST pattern as every other Supabase access in
this codebase (see db/supabase_client.py) rather than pulling in a JWT
library — Supabase's own GoTrue server is the source of truth on whether a
token is valid, so we just ask it.
"""

from __future__ import annotations

import logging
import os

import httpx
from fastapi import Header, HTTPException

logger = logging.getLogger(__name__)


def _supabase_url() -> str:
    return os.getenv("SUPABASE_URL", "").strip().rstrip("/")


async def _verify_token(token: str) -> dict | None:
    """Ask Supabase's GoTrue server whether this access token is valid."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{_supabase_url()}/auth/v1/user",
                headers={
                    # Any valid project key works here — this just routes the
                    # request to the right Supabase project. The actual
                    # security boundary is the bearer token itself, which
                    # GoTrue independently validates.
                    "apikey": os.getenv("SUPABASE_SERVICE_KEY", "").strip(),
                    "Authorization": f"Bearer {token}",
                },
            )
            if resp.status_code != 200:
                return None
            return resp.json()
    except Exception as exc:
        logger.warning("Token verification request failed: %s", exc)
        return None


async def get_current_user_id(authorization: str = Header(default="")) -> str:
    """
    FastAPI dependency — extracts and verifies the bearer token, returns the
    real Supabase user id. Raises 401 on anything else.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header.")

    token = authorization[len("Bearer "):].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header.")

    user = await _verify_token(token)
    if not user or not user.get("id"):
        raise HTTPException(status_code=401, detail="Invalid or expired session — please sign in again.")

    return user["id"]

"""
Whether a person has allowed AI processing, checked before anything about them
is sent to the AI service (Anthropic's Claude).

The choice is made on the app's consent screen and can be changed in Settings;
it's stored in user_consents (see routers/consent.py).

  - A recorded "yes" allows AI features; a recorded "no" switches every one off.
  - No record at all means the person hasn't seen the consent screen yet (an
    older install). That's allowed by default so existing testers aren't cut
    off; set REQUIRE_AI_CONSENT=true in the environment, before a public
    release, and "no record" then means "no".
"""

from __future__ import annotations

import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)

_CACHE_SECONDS = 30
_cache: dict[str, tuple[float, bool]] = {}


def _strict() -> bool:
    return os.getenv("REQUIRE_AI_CONSENT", "").strip().lower() in ("1", "true", "yes")


def forget(user_id: str) -> None:
    """Drop the remembered answer, so a change in Settings takes effect at once."""
    _cache.pop(user_id, None)


async def ai_allowed(user_id: str) -> bool:
    hit = _cache.get(user_id)
    if hit and time.time() - hit[0] < _CACHE_SECONDS:
        return hit[1]

    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                f"{base}/rest/v1/user_consents",
                headers={"apikey": key, "Authorization": f"Bearer {key}"},
                params={"user_id": f"eq.{user_id}", "select": "ai_processing", "limit": "1"},
            )
            resp.raise_for_status()
            rows = resp.json() or []
    except Exception as exc:
        # Can't tell: in strict mode that means no. Not remembered, so the
        # next request tries again.
        logger.warning("Consent lookup failed for %s: %s", user_id[:8], exc)
        return not _strict()

    allowed = bool(rows[0].get("ai_processing")) if rows else not _strict()
    if len(_cache) > 5000:
        _cache.clear()
    _cache[user_id] = (time.time(), allowed)
    return allowed

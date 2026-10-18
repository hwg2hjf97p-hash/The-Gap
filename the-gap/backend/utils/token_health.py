"""When a connected app's saved login can't be renewed (kept apart from the sync code so it is easy to test)."""

from __future__ import annotations

PROVIDER_NAMES = {"google": "Google Calendar", "whoop": "Whoop", "oura": "Oura", "strava": "Strava", "withings": "Withings", "polar": "Polar"}


# Connections that are no longer offered. Any that still exist are switched off the next time they would sync.
RETIRED_PROVIDERS = {"google"}


def refresh_token_is_dead(exc: Exception) -> bool:
    """
    True when a token refresh failed because the provider says the saved login is no longer valid
    ("invalid_grant"), which no retry can fix. Other failures (a timeout, a server error, a wrong app secret on
    our side) are not this, so they keep raising alerts and never switch anyone's connection off.
    """
    response = getattr(exc, "response", None)
    if response is None or getattr(response, "status_code", None) not in (400, 401):
        return False
    try:
        return "invalid_grant" in str(response.text).lower()
    except Exception:
        return False

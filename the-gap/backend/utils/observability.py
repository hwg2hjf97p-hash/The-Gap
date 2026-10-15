"""
Error alerts. If SENTRY_DSN is set on the server (a free Sentry account is enough), every unhandled error and
every logged error is sent to Sentry, which emails you. With no DSN this does nothing.

Health data must never end up in an error report, so request bodies, local variables and personal
details are switched off, and anything that looks like a user's own text is dropped before sending.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_SCRUB_KEYS = ("authorization", "cookie", "x-quicklog-token", "x-sync-secret", "x-admin-secret", "token", "password", "secret")


def scrub(event: dict, hint: dict | None = None) -> dict | None:
    """Remove request bodies, headers and anything secret-looking from an error report before it leaves the server."""
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("data", None)
        request.pop("cookies", None)
        request.pop("query_string", None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {k: v for k, v in headers.items() if not any(w in str(k).lower() for w in _SCRUB_KEYS)}
    event.pop("user", None)
    return event


def init_sentry() -> bool:
    """Start error reporting when SENTRY_DSN is set. Never raises: monitoring must not stop the app starting."""
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk  # type: ignore

        sentry_sdk.init(
            dsn=dsn,
            environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
            traces_sample_rate=0.0,
            send_default_pii=False,
            include_local_variables=False,
            max_request_body_size="never",
            before_send=scrub,
        )
        logger.info("Error reporting is on (Sentry).")
        return True
    except Exception as exc:
        logger.warning("Couldn't start error reporting: %s", exc)
        return False

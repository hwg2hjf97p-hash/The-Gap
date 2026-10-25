"""
Crash reports from the app.

When the app hits an error it can't recover from, it sends a short report the next time it can: the error message, the code trace
(only file names and line numbers of the app's own code), the app version, which update of the app was running, and the iPhone's
system version. No health data, no journal text, no names. This keeps what arrives free of anything personal as a second line of
defence (the app already sends none): email addresses and sign-in tokens are blanked, and everything is cut to a sensible length.

The report is written to the server log as an error, which also reaches Sentry if that is switched on (utils/observability.py).
"""

from __future__ import annotations

import re
import time
from typing import Optional

MAX_MESSAGE = 500
MAX_STACK = 6000
MAX_FIELD = 60

# At most this many reports per person in an hour, so a crash loop can't flood the log.
MAX_PER_HOUR = 10
_WINDOW_SECONDS = 3600

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_TOKEN = re.compile(r"eyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{5,}")  # a signed-in session token
_LONG_SECRET = re.compile(r"\b[A-Za-z0-9_-]{40,}\b")

_recent: dict[str, list[float]] = {}


def scrub(text: Optional[str], limit: int) -> str:
    """The text with emails, tokens and long secret-looking strings blanked, cut to `limit` characters."""
    cleaned = str(text or "")
    cleaned = _TOKEN.sub("[token]", cleaned)
    cleaned = _EMAIL.sub("[email]", cleaned)
    cleaned = _LONG_SECRET.sub("[secret]", cleaned)
    return cleaned[:limit]


def one_line(text: Optional[str], limit: int = MAX_FIELD) -> str:
    return " ".join(scrub(text, limit).split())


def allowed(user_id: str, now: Optional[float] = None) -> bool:
    """True if this person may still send a report this hour (and counts it)."""
    now = time.monotonic() if now is None else now
    recent = [t for t in _recent.get(user_id, []) if now - t < _WINDOW_SECONDS]
    if len(recent) >= MAX_PER_HOUR:
        _recent[user_id] = recent
        return False
    recent.append(now)
    _recent[user_id] = recent
    if len(_recent) > 5000:
        _recent.clear()  # a long-running server must not grow without limit
    return True

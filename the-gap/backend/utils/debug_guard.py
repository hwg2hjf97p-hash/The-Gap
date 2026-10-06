"""Gate for the /debug-* pages, which reveal how the server is set up."""

from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException


def require_debug_secret(x_debug_secret: str = Header(default="")) -> None:
    """The debug pages answer 404 unless a DEBUG_SECRET is set in the
    environment, and then only for requests that send it in an X-Debug-Secret header."""
    expected = os.getenv("DEBUG_SECRET", "").strip()
    if not expected or not hmac.compare_digest(x_debug_secret.encode(), expected.encode()):
        raise HTTPException(status_code=404, detail="Not Found")

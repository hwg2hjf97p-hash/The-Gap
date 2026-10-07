"""
Server-side subscription check for paid, AI-backed features.

The app's paywall only stops people inside the app; anyone calling the server
directly would otherwise get these features (and spend AI credits) without
paying. This checks the subscription mirror kept by the RevenueCat webhook
(routers/subscriptions.py).

It does nothing until REQUIRE_SUBSCRIPTION=true is set in the environment, so
testers who were let in some other way aren't locked out. Switch it on at launch.
While FREE_ACCESS=true is set (the testing switch, see routers/app_config.py) the check is skipped too.
"""

from __future__ import annotations

import logging
import os

from fastapi import HTTPException

from routers.subscriptions import is_subscribed

logger = logging.getLogger(__name__)


def _required() -> bool:
    return os.getenv("REQUIRE_SUBSCRIPTION", "").strip().lower() in ("1", "true", "yes")


async def require_subscription(user_id: str) -> None:
    """Raises 402 when the feature is paid-only and this person has no active subscription."""
    if not _required() or os.getenv("FREE_ACCESS", "").strip().lower() in ("1", "true", "yes"):
        return
    if not await is_subscribed(user_id):
        raise HTTPException(status_code=402, detail="This feature needs an active subscription.")

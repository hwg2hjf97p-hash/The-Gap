"""
Settings the app reads at launch, changeable on the server without a new build.

  GET /config  -> {"free_access": bool}

free_access is true only while FREE_ACCESS=true is set in the server's
environment, to let testers in without a subscription. It is OFF by default,
so a missing or misspelt variable fails safe (the paywall shows). It only
decides what the app displays; paid features are enforced separately by
REQUIRE_SUBSCRIPTION (utils/entitlement.py).
"""

from __future__ import annotations

import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/config", tags=["config"])


def free_access_enabled() -> bool:
    return os.getenv("FREE_ACCESS", "").strip().lower() in ("1", "true", "yes")


@router.get("")
async def get_config() -> JSONResponse:
    return JSONResponse(content={"free_access": free_access_enabled()}, headers={"Cache-Control": "no-store"})

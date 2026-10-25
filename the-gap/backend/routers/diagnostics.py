"""
Crash reports from the app (see utils/client_errors.py).

  POST /diagnostics/client-error   {message, stack, fatal, source, app_version, build, update_id, os}

Needs a signed-in person. The report goes to the server log as an error, and to Sentry if that is switched on.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from auth import get_current_user_id
from utils import client_errors as ce

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


class ClientError(BaseModel):
    message: str = Field(default="", max_length=2000)
    stack: str = Field(default="", max_length=20000)
    fatal: bool = False
    source: str = Field(default="", max_length=30)
    app_version: str = Field(default="", max_length=30)
    build: str = Field(default="", max_length=30)
    update_id: str = Field(default="", max_length=60)
    os: str = Field(default="", max_length=40)


@router.post("/client-error")
async def client_error(body: ClientError, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    if not ce.allowed(user_id):
        return JSONResponse(content={"ok": True, "kept": False})
    logger.error(
        "CLIENT_ERROR user=%s source=%s fatal=%s version=%s build=%s update=%s os=%s message=%s stack=%s",
        user_id[:8],
        ce.one_line(body.source),
        body.fatal,
        ce.one_line(body.app_version),
        ce.one_line(body.build),
        ce.one_line(body.update_id),
        ce.one_line(body.os),
        ce.one_line(body.message, ce.MAX_MESSAGE),
        ce.scrub(body.stack, ce.MAX_STACK),
    )
    return JSONResponse(content={"ok": True, "kept": True})

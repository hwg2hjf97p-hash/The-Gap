"""
Consent record: the person's agreement to the privacy policy and terms, and
their choice about AI features.

  GET /consent  -> what's on record (or null if they haven't been through the
                   consent screen)
  PUT /consent  -> save a choice; every save is also appended to consent_log
                   so there's a history of what was agreed, and when.

Table DDL (run once in the Supabase SQL editor — see phase5.sql):
  CREATE TABLE IF NOT EXISTS user_consents (
    user_id TEXT PRIMARY KEY,
    policy_version INTEGER NOT NULL,
    ai_processing BOOLEAN NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
  );
  CREATE TABLE IF NOT EXISTS consent_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    policy_version INTEGER NOT NULL,
    ai_processing BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
  );
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from auth import get_current_user_id
from utils.consent import forget

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/consent", tags=["consent"])


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


class ConsentBody(BaseModel):
    policy_version: int = Field(ge=1, le=1000)
    ai_processing: bool


@router.get("")
async def get_consent(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _sb_url("user_consents"),
                headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "select": "policy_version,ai_processing,updated_at", "limit": "1"},
            )
            resp.raise_for_status()
            rows = resp.json() or []
    except Exception as exc:
        logger.error("Loading consent failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=503, detail="Couldn't check your settings. Please try again.")
    return JSONResponse(content={"consent": rows[0] if rows else None})


@router.put("")
async def put_consent(body: ConsentBody, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    now = datetime.now(timezone.utc).isoformat()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            current = await client.post(
                _sb_url("user_consents"),
                headers=_sb_headers("resolution=merge-duplicates,return=minimal"),
                params={"on_conflict": "user_id"},
                json={"user_id": user_id, "policy_version": body.policy_version, "ai_processing": body.ai_processing, "updated_at": now},
            )
            current.raise_for_status()
            # The history is best-effort: the choice itself is what counts.
            try:
                await client.post(
                    _sb_url("consent_log"),
                    headers=_sb_headers("return=minimal"),
                    json={"user_id": user_id, "policy_version": body.policy_version, "ai_processing": body.ai_processing},
                )
            except Exception as exc:
                logger.warning("Consent log write failed for %s: %s", user_id[:8], exc)
    except Exception as exc:
        logger.error("Saving consent failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Couldn't save your choice. Please try again.")

    forget(user_id)
    return JSONResponse(content={"consent": {"policy_version": body.policy_version, "ai_processing": body.ai_processing, "updated_at": now}})

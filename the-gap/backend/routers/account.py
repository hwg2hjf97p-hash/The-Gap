"""
Account — data export and deletion.

Aggregates/deletes across every table this app actually writes to for a
given user_id: user_connections, quick_entries, journal_extractions,
results. This is scoped to data we control directly — it does not (and
can't, via a single call) revoke the OAuth grant on each provider's own
side (Whoop/Oura/etc.), only our own stored copy of their tokens and data.
"""

from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/account", tags=["account"])

TABLES = ["user_connections", "quick_entries", "journal_extractions", "results"]


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers() -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


@router.get("/export")
async def export_my_data(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    """Everything stored for this user, across every table, as one JSON download."""
    export: dict = {"user_id": user_id, "tables": {}}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            for table in TABLES:
                resp = await client.get(
                    _sb_url(table),
                    headers=_sb_headers(),
                    params={"user_id": f"eq.{user_id}", "select": "*"},
                )
                resp.raise_for_status()
                export["tables"][table] = resp.json()
    except Exception as exc:
        logger.error("Export failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Export failed. Please try again.")

    return JSONResponse(content=export)


@router.delete("")
async def delete_my_account(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    """
    Delete every row this app has stored for this user, across all tables.
    Does not attempt to revoke the OAuth grant on each provider's own side —
    that requires the user to also disconnect via each provider's own
    account settings if they want to fully revoke access at the source.
    """
    deleted: dict[str, str] = {}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            for table in TABLES:
                resp = await client.delete(
                    _sb_url(table),
                    headers=_sb_headers(),
                    params={"user_id": f"eq.{user_id}"},
                )
                deleted[table] = "ok" if resp.status_code in (200, 204) else f"status={resp.status_code}"
    except Exception as exc:
        logger.error("Account deletion failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Deletion failed. Please try again.")

    logger.info("ACCOUNT_DELETED user=%s result=%s", user_id[:8], deleted)
    return JSONResponse(content={"deleted": True, "tables": deleted})


class ClaimRequest(BaseModel):
    old_user_id: str


@router.post("/claim")
async def claim_old_identity(body: ClaimRequest, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    """
    One-time migration: re-points every row for a pre-auth anonymous device
    UUID (the random id every install used to generate for itself before
    Sign in with Apple existed) to the now-authenticated user id, so
    existing history isn't orphaned the first time someone signs in.
    Safe to call repeatedly — a no-op once nothing matches the old id.
    """
    old_user_id = body.old_user_id.strip()
    if not old_user_id or old_user_id == user_id:
        return JSONResponse(content={"claimed": False, "tables": {}})

    claimed: dict[str, str] = {}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            for table in TABLES:
                resp = await client.patch(
                    _sb_url(table),
                    headers=_sb_headers(),
                    params={"user_id": f"eq.{old_user_id}"},
                    json={"user_id": user_id},
                )
                claimed[table] = "ok" if resp.status_code in (200, 204) else f"status={resp.status_code}"
    except Exception as exc:
        logger.error("Account claim failed for old=%s new=%s: %s", old_user_id[:8], user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Could not migrate old data. Please try again.")

    logger.info("ACCOUNT_CLAIMED old=%s new=%s result=%s", old_user_id[:8], user_id[:8], claimed)
    return JSONResponse(content={"claimed": True, "tables": claimed})

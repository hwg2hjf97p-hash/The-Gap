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
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/account", tags=["account"])

TABLES = ["user_connections", "quick_entries", "journal_extractions", "results"]


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers() -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


@router.get("/export/{user_id}")
async def export_my_data(user_id: str) -> JSONResponse:
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


@router.delete("/{user_id}")
async def delete_my_account(user_id: str) -> JSONResponse:
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

"""
Account — data export and deletion.

Aggregates/deletes across every table this app writes per-user data to
(USER_DATA_TABLES below). This is scoped to data we control directly — it
does not (and can't, via a single call) revoke the OAuth grant on each
provider's own side (Whoop/Oura/etc.), only our own stored copy of their
tokens and data.

REAL BUG FIXED HERE: export/deletion used to cover only 4 tables
(user_connections, quick_entries, journal_extractions, results) while the
app had grown to ~30 — "Delete account & data" left daily check-ins, Apple
Health history, metric history, profile (weight/height/age) and the saved
home address behind. Every table keyed by user_id is listed now; add any
new per-user table here when it's created.
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

# Only the tables that existed when anonymous device IDs did — used by
# /claim to re-point pre-auth history. Newer tables never held anonymous
# data, and re-pointing tables with unique constraints risks conflicts.
TABLES = ["user_connections", "quick_entries", "journal_extractions", "results"]

# Everything keyed by user_id. user_subscriptions is deliberately excluded:
# it's a billing-state mirror of RevenueCat/Apple (which outlive this
# database), not health data.
USER_DATA_TABLES = TABLES + [
    "daily_checkins", "apple_health_daily", "device_calendar_daily",
    "user_locations", "environment_daily", "user_profile", "push_tokens",
    "metric_history", "weekly_digests", "user_hypotheses", "user_goals",
    "improvement_plans", "improvement_plan_usage",
    "hypothesis_explanations", "hypothesis_explanation_usage",
    "metric_insights", "metric_insight_usage",
    "active_interventions", "proactive_nudges",
    "assistant_questions", "assistant_extractions",
    "workouts", "food_log", "water_log", "nutrition_goals",
]

# Credentials never belong in a data export, even the user's own.
_EXPORT_STRIPPED_FIELDS = {"access_token", "refresh_token"}


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
    async with httpx.AsyncClient(timeout=20) as client:
        for table in USER_DATA_TABLES:
            # One missing/unreachable table (e.g. not created yet) must not
            # sink the whole export.
            try:
                resp = await client.get(
                    _sb_url(table),
                    headers=_sb_headers(),
                    params={"user_id": f"eq.{user_id}", "select": "*"},
                )
                resp.raise_for_status()
                rows = resp.json() or []
                export["tables"][table] = [
                    {k: v for k, v in row.items() if k not in _EXPORT_STRIPPED_FIELDS} for row in rows
                ]
            except Exception as exc:
                logger.warning("Export skipped table %s for %s: %s", table, user_id[:8], exc)
                export["tables"][table] = {"error": "unavailable"}

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
    async with httpx.AsyncClient(timeout=20) as client:
        for table in USER_DATA_TABLES:
            # Keep going if one table fails (e.g. not created yet) so a
            # single problem can't leave everything else undeleted.
            try:
                resp = await client.delete(
                    _sb_url(table),
                    headers=_sb_headers(),
                    params={"user_id": f"eq.{user_id}"},
                )
                deleted[table] = "ok" if resp.status_code in (200, 204) else f"status={resp.status_code}"
            except Exception as exc:
                logger.warning("Account deletion hit an error on %s for %s: %s", table, user_id[:8], exc)
                deleted[table] = "error"

    # A table that failed for a reason other than "doesn't exist yet"
    # (404 means the table isn't created) is a real problem to surface.
    failed = {t: s for t, s in deleted.items() if s not in ("ok", "status=404")}
    if failed:
        logger.error("ACCOUNT_DELETE_INCOMPLETE user=%s failed=%s", user_id[:8], failed)
        raise HTTPException(status_code=500, detail="Deletion didn't fully complete. Please try again.")

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

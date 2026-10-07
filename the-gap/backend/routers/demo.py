"""
Sample data, so the app can be tried without a wearable and so App Review
(whose test phones have no health history) can see every screen.

  GET    /demo  -> {"active": bool, "can_load": bool}
  POST   /demo  -> adds twelve weeks of made-up readings and check-ins, then runs
                   the normal analysis on them. Only allowed on an empty account,
                   so it can never mix made-up numbers into real data.
  DELETE /demo  -> removes it again (only if sample data was loaded).

The data comes from utils/demo_data.py. The "demo" flag is kept inside the
person's source_prefs row (no new table).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from auth import get_current_user_id
from sync.apple_health_store import upsert_apple_health_rows
from utils.demo_data import generate_demo_data
from utils.source_merge import load_source_prefs

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/demo", tags=["demo"])

# Everything the sample data (and the analysis run on it) writes.
DEMO_TABLES = ["apple_health_daily", "daily_checkins", "metric_history", "results", "weekly_digests"]
# Columns added by later SQL files; dropped when a table doesn't have them yet.
OPTIONAL_CHECKIN_COLUMNS = ["screen_hours", "screen_last_use", "alcohol_drinks", "work_hours"]


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


async def _has_rows(client: httpx.AsyncClient, table: str, user_id: str) -> bool:
    resp = await client.get(_sb_url(table), headers=_sb_headers(), params={"user_id": f"eq.{user_id}", "select": "user_id", "limit": "1"})
    resp.raise_for_status()
    return bool(resp.json())


async def _account_is_empty(user_id: str) -> bool:
    async with httpx.AsyncClient(timeout=15) as client:
        for table in ("apple_health_daily", "daily_checkins", "user_connections"):
            if await _has_rows(client, table, user_id):
                return False
    return True


async def _set_demo_flag(user_id: str, active: bool) -> None:
    prefs = dict(await load_source_prefs(user_id) or {})
    if active:
        prefs["demo"] = True
    else:
        prefs.pop("demo", None)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            _sb_url("source_prefs"),
            headers=_sb_headers("resolution=merge-duplicates,return=minimal"),
            params={"on_conflict": "user_id"},
            json={"user_id": user_id, "prefs": prefs, "updated_at": datetime.now(timezone.utc).isoformat()},
        )
        resp.raise_for_status()


async def _save_checkins(user_id: str, rows: list[dict]) -> None:
    payload = [{"user_id": user_id, **row} for row in rows]
    async with httpx.AsyncClient(timeout=30) as client:
        for _ in range(len(OPTIONAL_CHECKIN_COLUMNS) + 1):
            resp = await client.post(
                _sb_url("daily_checkins"),
                headers=_sb_headers("resolution=merge-duplicates,return=minimal"),
                params={"on_conflict": "user_id,date"},
                json=payload,
            )
            if resp.status_code == 400 and "PGRST204" in resp.text:
                # A column from a later SQL file isn't there yet: leave it out and try again.
                missing = next((c for c in OPTIONAL_CHECKIN_COLUMNS if f"'{c}'" in resp.text), None)
                if missing:
                    logger.warning("daily_checkins has no %s column yet; loading demo data without it", missing)
                    payload = [{k: v for k, v in row.items() if k != missing} for row in payload]
                    continue
            resp.raise_for_status()
            return
    raise RuntimeError("daily_checkins rejected the sample rows")


@router.get("")
async def demo_status(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    prefs = await load_source_prefs(user_id) or {}
    active = bool(prefs.get("demo"))
    can_load = False
    if not active:
        try:
            can_load = await _account_is_empty(user_id)
        except Exception as exc:
            logger.warning("Demo availability check failed for %s: %s", user_id[:8], exc)
    return JSONResponse(content={"active": active, "can_load": can_load})


@router.post("")
async def load_demo(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        empty = await _account_is_empty(user_id)
    except Exception as exc:
        logger.error("Demo availability check failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=503, detail="Couldn't check your account. Please try again.")
    if not empty:
        raise HTTPException(status_code=409, detail="Sample data can only be added to an account with no data of its own.")

    last_day = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    health_rows, checkin_rows = generate_demo_data(last_day)

    await upsert_apple_health_rows(user_id, health_rows)
    try:
        await _save_checkins(user_id, checkin_rows)
        await _set_demo_flag(user_id, True)
    except Exception as exc:
        logger.error("Saving demo data failed for %s: %s", user_id[:8], exc)
        await _remove_demo_rows(user_id)
        raise HTTPException(status_code=500, detail="Couldn't load the sample data. Please try again.")

    # Imported here so this module stays light to load (the analysis pulls in the heavy engine).
    from sync.daily_sync import _sync_user

    result = await _sync_user(user_id, [])
    if result.get("status") != "success":
        logger.error("Demo analysis failed for %s: %s", user_id[:8], result)
        await _remove_demo_rows(user_id)
        await _set_demo_flag(user_id, False)
        raise HTTPException(status_code=500, detail="Couldn't analyse the sample data. Please try again.")

    logger.info("DEMO_LOADED user=%s insights=%s", user_id[:8], result.get("insights"))
    return JSONResponse(content={"loaded": True, "days": result.get("days"), "insights": result.get("insights")})


async def _remove_demo_rows(user_id: str) -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        for table in DEMO_TABLES:
            try:
                resp = await client.delete(_sb_url(table), headers=_sb_headers(), params={"user_id": f"eq.{user_id}"})
                resp.raise_for_status()
            except Exception as exc:
                logger.warning("Removing demo rows from %s failed for %s: %s", table, user_id[:8], exc)


@router.delete("")
async def remove_demo(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    prefs = await load_source_prefs(user_id) or {}
    if not prefs.get("demo"):
        raise HTTPException(status_code=409, detail="No sample data to remove.")
    await _remove_demo_rows(user_id)
    await _set_demo_flag(user_id, False)
    return JSONResponse(content={"removed": True})

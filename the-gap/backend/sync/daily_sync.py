"""
Daily sync job — runs for all connected users, fetches fresh data,
runs causal engine, stores updated results in Supabase.

Called via POST /sync/run (protected by SYNC_SECRET env var).
Can also be triggered manually or via a cron job (Railway cron or external).
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

import httpx
import pandas as pd
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

from db.supabase_client import save_results
from sync.whoop_sync import fetch_whoop_data, refresh_whoop_token
from sync.oura_sync import fetch_oura_data, refresh_oura_token
from utils.data_cleaning import clean_dataframe
from utils.snapshot import build_snapshot
from causal.engine import run_all_hypotheses
from routers.checkin import get_checkin_dataframe
from routers.journal import get_journal_dataframe

# Optional imports — don't crash if these aren't ready yet
try:
    from sync.google_sync import fetch_google_calendar_data, refresh_google_token
except ImportError:
    fetch_google_calendar_data = None  # type: ignore
    refresh_google_token = None  # type: ignore

try:
    from sync.strava_sync import fetch_strava_data, refresh_strava_token
except ImportError:
    fetch_strava_data = None  # type: ignore
    refresh_strava_token = None  # type: ignore

try:
    from parsers.google_calendar import merge_calendar_into_health
except ImportError:
    merge_calendar_into_health = None  # type: ignore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sync")

SYNC_SECRET = os.getenv("SYNC_SECRET", "")

REFRESH_FUNCS = {
    "whoop": refresh_whoop_token,
    "oura": refresh_oura_token,
    "google": refresh_google_token,
    "strava": refresh_strava_token,
}

FETCH_FUNCS = {
    "whoop": fetch_whoop_data,
    "oura": fetch_oura_data,
    "strava": fetch_strava_data,
}

CLIENT_ID_ENVS = {
    "whoop": "WHOOP_CLIENT_ID",
    "oura": "OURA_CLIENT_ID",
    "google": "GOOGLE_CLIENT_ID",
    "strava": "STRAVA_CLIENT_ID",
}
CLIENT_SECRET_ENVS = {
    "whoop": "WHOOP_CLIENT_SECRET",
    "oura": "OURA_CLIENT_SECRET",
    "google": "GOOGLE_CLIENT_SECRET",
    "strava": "STRAVA_CLIENT_SECRET",
}


# ── Supabase REST helpers ─────────────────────────────────────────────────────

def _supabase_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _supabase_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


async def _supabase_get(table: str, params: dict) -> list[dict]:
    """Generic async GET for Supabase REST."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            _supabase_url(table),
            headers=_supabase_headers(),
            params=params,
        )
        resp.raise_for_status()
        return resp.json() or []


async def _supabase_patch(table: str, params: dict, payload: dict) -> None:
    """Generic async PATCH for Supabase REST."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.patch(
            _supabase_url(table),
            headers=_supabase_headers(prefer="return=minimal"),
            params=params,
            json=payload,
        )
        resp.raise_for_status()


# ── Sync routes ───────────────────────────────────────────────────────────────

@router.post("/run")
async def run_sync(x_sync_secret: str = Header(default="")):
    """
    Run the daily sync for all connected users.
    Protected by X-Sync-Secret header.
    """
    if SYNC_SECRET and x_sync_secret != SYNC_SECRET:
        raise HTTPException(status_code=403, detail="Invalid sync secret.")

    # Get all active connections via REST (not supabase-py)
    try:
        connections = await _supabase_get(
            "user_connections",
            {"is_active": "eq.true", "select": "*"},
        )
    except Exception as exc:
        logger.error("Failed to fetch connections: %s", exc)
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}")

    logger.info("Daily sync: %d active connections", len(connections))

    results = []
    # Group by user_id
    users: dict[str, list[dict]] = {}
    for conn in connections:
        users.setdefault(conn["user_id"], []).append(conn)

    for user_id, user_connections in users.items():
        result = await _sync_user(user_id, user_connections)
        results.append(result)

    return JSONResponse(content={
        "synced_users": len(results),
        "results": results,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


async def _sync_user(user_id: str, connections: list[dict]) -> dict:
    """Sync one user — fetch all their data, run causal engine, save results."""
    t0 = time.perf_counter()
    health_df = None
    calendar_df = None
    providers_synced = []

    for conn in connections:
        provider = conn["provider"]
        access_token = conn.get("access_token", "").strip()
        refresh_token = conn.get("refresh_token", "").strip()
        expires_at = conn.get("expires_at") or 0

        logger.info("SYNC_USER provider=%s user=%s token_len=%d expires_at=%s",
                    provider, user_id[:8], len(access_token), expires_at)

        # Only refresh if token is actually expired (not just 0)
        # expires_at=0 means we don't know — try with existing token first
        token_expired = expires_at > 0 and time.time() > (expires_at - 300)
        if token_expired:
            logger.info("TOKEN_EXPIRED refreshing %s/%s", user_id[:8], provider)
            refresh_func = REFRESH_FUNCS.get(provider)
            if refresh_func and refresh_token:
                try:
                    client_id = os.getenv(CLIENT_ID_ENVS.get(provider, ""), "")
                    client_secret = os.getenv(CLIENT_SECRET_ENVS.get(provider, ""), "")
                    new_tokens = await refresh_func(refresh_token, client_id, client_secret)
                    access_token = new_tokens.get("access_token", access_token)
                    # Whoop's OAuth (Ory Hydra) issues single-use refresh tokens:
                    # every refresh returns a NEW refresh_token and immediately
                    # invalidates the old one. Not saving it here meant the very
                    # next refresh attempt (even a background/cron one) would
                    # permanently kill the connection — matching exactly what
                    # was happening before this fix.
                    new_refresh_token = new_tokens.get("refresh_token", refresh_token)
                    await _supabase_patch(
                        "user_connections",
                        {"user_id": f"eq.{user_id}", "provider": f"eq.{provider}"},
                        {
                            "access_token": access_token,
                            "refresh_token": new_refresh_token,
                            "expires_at": int(time.time()) + new_tokens.get("expires_in", 3600),
                        },
                    )
                    logger.info("TOKEN_REFRESHED %s/%s", user_id[:8], provider)
                except Exception as exc:
                    logger.error("TOKEN_REFRESH_FAILED %s/%s: %s — continuing with old token",
                                 user_id[:8], provider, exc)
                    # Don't skip — try with the existing token anyway

        # Fetch data
        try:
            logger.info("FETCH_START provider=%s user=%s", provider, user_id[:8])
            if provider == "google" and fetch_google_calendar_data is not None:
                calendar_df = await fetch_google_calendar_data(access_token)
                logger.info("FETCH_DONE provider=google rows=%s",
                            len(calendar_df) if calendar_df is not None else 0)
            elif provider == "whoop":
                fetched = await fetch_whoop_data(access_token)
                logger.info("FETCH_DONE provider=whoop rows=%d", len(fetched) if fetched is not None else 0)
                if fetched is not None and not fetched.empty:
                    health_df = fetched if health_df is None else health_df.combine_first(fetched)
                    providers_synced.append(provider)
            elif provider == "oura":
                fetched = await fetch_oura_data(access_token)
                logger.info("FETCH_DONE provider=oura rows=%d", len(fetched) if fetched is not None else 0)
                if fetched is not None and not fetched.empty:
                    health_df = fetched if health_df is None else health_df.combine_first(fetched)
                    providers_synced.append(provider)
            elif provider == "strava" and fetch_strava_data is not None:
                fetched = await fetch_strava_data(access_token)
                logger.info("FETCH_DONE provider=strava rows=%d", len(fetched) if fetched is not None else 0)
                if fetched is not None and not fetched.empty:
                    health_df = fetched if health_df is None else health_df.combine_first(fetched)
                    providers_synced.append(provider)

            # Update last_synced_at
            await _supabase_patch(
                "user_connections",
                {"user_id": f"eq.{user_id}", "provider": f"eq.{provider}"},
                {"last_synced_at": datetime.now(timezone.utc).isoformat()},
            )

        except Exception as exc:
            logger.error("FETCH_FAILED provider=%s user=%s error=%s", provider, user_id[:8], exc)

    logger.info("SYNC_DATA_COLLECTED user=%s health_df_rows=%s providers=%s elapsed=%.1fs",
                user_id[:8],
                len(health_df) if health_df is not None else 0,
                providers_synced,
                time.perf_counter() - t0)

    if health_df is None or health_df.empty:
        return {"user_id": user_id, "status": "no_data", "elapsed": round(time.perf_counter() - t0, 1)}

    # Merge calendar if available
    if calendar_df is not None and not calendar_df.empty and merge_calendar_into_health is not None:
        health_df = merge_calendar_into_health(health_df, calendar_df)

    # Merge daily check-ins (alcohol, caffeine, stress score) — this was
    # collected all along but never actually reached the causal engine
    # until now, so hypotheses like alcohol_hrv had no data to run against.
    try:
        health_df.index = pd.to_datetime(health_df.index)
        checkin_df = get_checkin_dataframe(user_id)
        if checkin_df is not None and not checkin_df.empty:
            checkin_df.index = pd.to_datetime(checkin_df.index)
            health_df = health_df.join(checkin_df, how="left")
    except Exception as exc:
        logger.warning("Check-in merge failed (continuing without it): %s", exc)

    # Merge Quick Entry signals (mood, stress, travel, illness, conflict)
    try:
        journal_df = await get_journal_dataframe(user_id)
        if journal_df is not None and not journal_df.empty:
            journal_df.index = pd.to_datetime(journal_df.index)
            health_df = health_df.join(journal_df, how="left")
    except Exception as exc:
        logger.warning("Journal merge failed (continuing without it): %s", exc)

    # Run causal engine
    try:
        logger.info("ENGINE_START user=%s days=%d", user_id[:8], len(health_df))
        df = clean_dataframe(health_df)
        insights = run_all_hypotheses(df)
        insights_dicts = [i.to_dict() for i in insights]
        snapshot = build_snapshot(df)
        logger.info("ENGINE_DONE user=%s insights=%d elapsed=%.1fs",
                    user_id[:8], len(insights_dicts), time.perf_counter() - t0)

        session_id = save_results(
            data_source=",".join(providers_synced),
            data_period_days=len(df),
            insights=insights_dicts,
            snapshot=snapshot,
        )

        return {
            "user_id": user_id,
            "status": "success",
            "insights": len(insights_dicts),
            "days": len(df),
            "session_id": session_id,
            "elapsed": round(time.perf_counter() - t0, 1),
        }
    except Exception as exc:
        logger.error("ENGINE_FAILED user=%s error=%s", user_id[:8], exc)
        return {"user_id": user_id, "status": "engine_error", "error": str(exc)}


@router.post("/user/{user_id}")
async def sync_single_user(user_id: str):
    """
    Immediately fetch data + run causal engine for one user.
    Called by the frontend "Run analysis now" button right after OAuth connect.
    No auth required — user_id is a random UUID from localStorage (not sensitive).
    """
    logger.info("Manual sync triggered for user: %s", user_id)

    # Fetch all active connections for this user
    try:
        connections = await _supabase_get(
            "user_connections",
            {
                "user_id": f"eq.{user_id}",
                "is_active": "eq.true",
                "select": "*",
            },
        )
    except Exception as exc:
        logger.error("Could not fetch connections for %s: %s", user_id, exc)
        raise HTTPException(status_code=503, detail="Database unavailable — please try again.")

    if not connections:
        raise HTTPException(
            status_code=404,
            detail="No connected devices found. Please connect Whoop or Oura first.",
        )

    result = await _sync_user(user_id, connections)

    if result.get("status") == "no_data":
        raise HTTPException(
            status_code=422,
            detail="Connected but no data retrieved yet. Your device may need a sync — open Whoop/Oura app and wait a minute, then try again.",
        )

    if result.get("status") == "engine_error":
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {result.get('error', 'unknown error')}",
        )

    return JSONResponse(content={
        "session_id": result.get("session_id"),
        "insights": result.get("insights", 0),
        "days": result.get("days", 0),
        "status": result.get("status"),
    })

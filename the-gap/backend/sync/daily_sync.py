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
from sync.google_sync import fetch_google_calendar_data, refresh_google_token
from sync.strava_sync import fetch_strava_data, refresh_strava_token
from parsers.google_calendar import merge_calendar_into_health
from utils.data_cleaning import clean_dataframe
from causal.engine import run_all_hypotheses

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
        access_token = conn.get("access_token", "")
        refresh_token = conn.get("refresh_token", "")
        expires_at = conn.get("expires_at", 0)

        # Refresh token if expired or expiring soon
        if time.time() > (expires_at - 300):  # refresh 5 min early
            try:
                client_id = os.getenv(CLIENT_ID_ENVS.get(provider, ""), "")
                client_secret = os.getenv(CLIENT_SECRET_ENVS.get(provider, ""), "")
                new_tokens = await REFRESH_FUNCS[provider](
                    refresh_token, client_id, client_secret
                )
                access_token = new_tokens.get("access_token", access_token)
                # Update stored token via REST
                await _supabase_patch(
                    "user_connections",
                    {"user_id": f"eq.{user_id}", "provider": f"eq.{provider}"},
                    {
                        "access_token": access_token,
                        "expires_at": int(time.time()) + new_tokens.get("expires_in", 3600),
                    },
                )
                logger.info("Token refreshed for %s/%s", user_id, provider)
            except Exception as exc:
                logger.error("Token refresh failed for %s/%s: %s", user_id, provider, exc)
                continue

        # Fetch data
        try:
            if provider == "google":
                calendar_df = await fetch_google_calendar_data(access_token)
            elif provider in FETCH_FUNCS:
                fetched = await FETCH_FUNCS[provider](access_token)
                if health_df is None:
                    health_df = fetched
                else:
                    # Merge multiple health sources
                    health_df = health_df.combine_first(fetched)
                providers_synced.append(provider)

            # Update last_synced_at via REST
            await _supabase_patch(
                "user_connections",
                {"user_id": f"eq.{user_id}", "provider": f"eq.{provider}"},
                {"last_synced_at": datetime.now(timezone.utc).isoformat()},
            )

        except Exception as exc:
            logger.error("Fetch failed for %s/%s: %s", user_id, provider, exc)

    if health_df is None or health_df.empty:
        return {"user_id": user_id, "status": "no_data", "elapsed": round(time.perf_counter() - t0, 1)}

    # Merge calendar if available
    if calendar_df is not None and not calendar_df.empty:
        health_df = merge_calendar_into_health(health_df, calendar_df)

    # Run causal engine
    try:
        df = clean_dataframe(health_df)
        insights = run_all_hypotheses(df)
        insights_dicts = [i.to_dict() for i in insights]

        session_id = save_results(
            data_source=",".join(providers_synced),
            data_period_days=len(df),
            insights=insights_dicts,
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
        logger.error("Engine failed for %s: %s", user_id, exc)
        return {"user_id": user_id, "status": "engine_error", "error": str(exc)}

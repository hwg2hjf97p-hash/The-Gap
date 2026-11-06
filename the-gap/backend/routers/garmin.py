"""
Garmin: where Garmin's pushes arrive, what the app shows of them, and how a person's Garmin data is removed.

  POST /garmin/push/{token}/{kind}   Garmin's pushes (kind: dailies, sleeps, hrv, deregistrations, permissions). Answers 200 at once
                                     (Garmin needs that within 30 seconds, before any processing) and files the numbers afterwards.
  GET  /garmin/recent                the last week of the person's Garmin numbers, for the card in the app.

The sign-in itself (start, callback, disconnect) is in routers/connect.py. All of the rules, and why, are in utils/garmin.py. In short:
Garmin numbers live in garmin_daily, apart from everything else, and only reach the insights engine and Gappy when GARMIN_AI_ALLOWED is on.

Tables (phase30.sql): garmin_links (which Garmin account is which person) and garmin_daily (one row per person per day).
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from auth import get_current_user_id
from utils import garmin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/garmin", tags=["garmin"])


# ── Supabase REST ─────────────────────────────────────────────────────────────

def _sb_url(table: str) -> str:
    return f"{os.getenv('SUPABASE_URL', '').strip().rstrip('/')}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        headers["Prefer"] = prefer
    return headers


async def user_for(garmin_user_id: str) -> Optional[str]:
    """The person a Garmin account belongs to, or None if we don't know it (someone who disconnected, or a stray push)."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(_sb_url("garmin_links"), headers=_sb_headers(), params={"garmin_user_id": f"eq.{garmin_user_id}", "select": "user_id", "limit": "1"})
            resp.raise_for_status()
            rows = resp.json() or []
        return rows[0]["user_id"] if rows else None
    except Exception as exc:
        logger.warning("Garmin link lookup failed: %s", exc)
        return None


async def link_user(user_id: str, garmin_user_id: str) -> None:
    """Remember which Garmin account is this person. If that Garmin account was linked to someone else, the newest connection wins."""
    async with httpx.AsyncClient(timeout=10) as client:
        old = await client.delete(_sb_url("garmin_links"), headers=_sb_headers("return=minimal"), params={"garmin_user_id": f"eq.{garmin_user_id}", "user_id": f"neq.{user_id}"})
        old.raise_for_status()
        resp = await client.post(
            _sb_url("garmin_links"),
            headers=_sb_headers("resolution=merge-duplicates,return=minimal"),
            params={"on_conflict": "user_id"},
            json={"user_id": user_id, "garmin_user_id": garmin_user_id},
        )
        resp.raise_for_status()


async def _load_day(client: httpx.AsyncClient, user_id: str, local_date: str) -> Optional[dict]:
    resp = await client.get(_sb_url("garmin_daily"), headers=_sb_headers(), params={"user_id": f"eq.{user_id}", "local_date": f"eq.{local_date}", "select": "data", "limit": "1"})
    resp.raise_for_status()
    rows = resp.json() or []
    return rows[0].get("data") if rows else None


async def _save_day(client: httpx.AsyncClient, user_id: str, local_date: str, data: dict) -> None:
    resp = await client.post(
        _sb_url("garmin_daily"),
        headers=_sb_headers("resolution=merge-duplicates,return=minimal"),
        params={"on_conflict": "user_id,local_date"},
        json={"user_id": user_id, "local_date": local_date, "data": data, "updated_at": datetime.now(timezone.utc).isoformat()},
    )
    resp.raise_for_status()


async def recent_rows(user_id: str, days: int) -> list[dict]:
    since = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            _sb_url("garmin_daily"),
            headers=_sb_headers(),
            params={"user_id": f"eq.{user_id}", "local_date": f"gte.{since}", "select": "local_date,data", "order": "local_date.desc", "limit": str(days + 1)},
        )
        resp.raise_for_status()
        return resp.json() or []


async def forget_data(user_id: str) -> None:
    """Remove the person's stored Garmin numbers and the link to their Garmin account."""
    async with httpx.AsyncClient(timeout=15) as client:
        for table in ("garmin_daily", "garmin_links"):
            try:
                resp = await client.delete(_sb_url(table), headers=_sb_headers("return=minimal"), params={"user_id": f"eq.{user_id}"})
                resp.raise_for_status()
            except Exception as exc:
                logger.warning("Removing %s for a person failed: %s", table, exc)


async def disconnect_user(user_id: str, tokens: Optional[dict]) -> None:
    """
    The person disconnected Garmin in the app (or is deleting their account). Garmin's licence says we must then remove their
    registration at Garmin too, so that is done first (with a fresh login if theirs has expired), then their numbers and link go.
    Never raises: a failure at Garmin is logged and the local removal still happens.
    """
    try:
        access = (tokens or {}).get("access_token") or ""
        refresh = (tokens or {}).get("refresh_token") or ""
        expires_at = (tokens or {}).get("expires_at") or 0
        if refresh and (not access or (expires_at and time.time() > expires_at - 300)):
            fresh = await garmin.refresh_tokens(refresh)
            access = fresh.get("access_token", access)
        if access:
            await garmin.delete_registration(access)
    except Exception as exc:
        logger.warning("Garmin deregistration for a disconnecting person failed: %s", exc)
    await forget_data(user_id)


# ── Garmin's pushes ───────────────────────────────────────────────────────────

async def process_push(kind: str, payload) -> None:
    """File one push. Runs after the 200 has been sent, so it must never raise."""
    try:
        if kind in garmin.KEPT_SUMMARIES:
            items = garmin.parse_push(kind, payload)
            if not items:
                return
            people: dict[str, Optional[str]] = {}
            async with httpx.AsyncClient(timeout=15) as client:
                for garmin_user, local_date, patch in items:
                    if garmin_user not in people:
                        people[garmin_user] = await user_for(garmin_user)
                    user_id = people[garmin_user]
                    if not user_id:
                        continue
                    existing = await _load_day(client, user_id, local_date)
                    await _save_day(client, user_id, local_date, garmin.merge_day(existing, patch))
        elif kind == "deregistrations":
            for garmin_user in garmin.parse_deregistrations(payload):
                user_id = await user_for(garmin_user)
                if user_id:
                    await _turn_off(user_id)
        elif kind == "permissions":
            for garmin_user, permissions in garmin.parse_permission_changes(payload):
                if garmin.REQUIRED_PERMISSION not in permissions:
                    # they stopped sharing health data: their numbers go too
                    user_id = await user_for(garmin_user)
                    if user_id:
                        await _clear_days(user_id)
    except Exception as exc:
        logger.error("Filing a Garmin %s push failed: %s", kind, exc)


async def _clear_days(user_id: str) -> None:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.delete(_sb_url("garmin_daily"), headers=_sb_headers("return=minimal"), params={"user_id": f"eq.{user_id}"})
        resp.raise_for_status()


async def _turn_off(user_id: str) -> None:
    """Garmin says this person is disconnected: switch the connection off, clear its login, and remove their Garmin numbers."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.patch(
                _sb_url("user_connections"),
                headers=_sb_headers("return=minimal"),
                params={"user_id": f"eq.{user_id}", "provider": "eq.garmin"},
                json={"is_active": False, "access_token": "", "refresh_token": ""},
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("Switching a Garmin connection off failed: %s", exc)
    await forget_data(user_id)


@router.post("/push/{token}/{kind}")
async def receive_push(token: str, kind: str, request: Request, background: BackgroundTasks) -> Response:
    # Anything that doesn't know the secret address, or asks for a kind we don't use, gets a plain 404.
    if not garmin.push_token_ok(token) or kind not in garmin.PUSH_KINDS:
        raise HTTPException(status_code=404, detail="Not Found")
    try:
        payload = await request.json()
    except Exception:
        payload = None
    background.add_task(process_push, kind, payload)
    return Response(status_code=200)


# ── For the app ───────────────────────────────────────────────────────────────

@router.get("/recent")
async def recent(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    """The last week of the person's own Garmin numbers, as Garmin sent them, for the Garmin card."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            link = await client.get(_sb_url("garmin_links"), headers=_sb_headers(), params={"user_id": f"eq.{user_id}", "select": "user_id", "limit": "1"})
            link.raise_for_status()
            connected = bool(link.json())
        rows = await recent_rows(user_id, 7) if connected else []
    except Exception as exc:
        logger.warning("Reading Garmin numbers failed: %s", exc)
        return JSONResponse(content={"connected": False, "days": [], "used_in_insights": garmin.engine_allowed()})
    days = [garmin.day_view(str(r["local_date"]), r.get("data") or {}) for r in rows]
    # used_in_insights tells the card, truthfully, whether these numbers also feed the insights (only when GARMIN_AI_ALLOWED is on)
    return JSONResponse(content={"connected": connected, "days": days, "used_in_insights": garmin.engine_allowed()})

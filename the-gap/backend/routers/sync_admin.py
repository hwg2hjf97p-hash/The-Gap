"""
Is syncing healthy? A private page for the owner (website /admin/sync), protected by ADMIN_SECRET like the
research review. Shows how many people are synced, due, running or failing, from the sync queue
(utils/sync_queue.py). Only the first eight characters of a person's id are shown.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from routers.evidence_admin import require_admin
from utils.sync_queue import OVERDUE_GRACE_MINUTES

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/sync", tags=["admin"], dependencies=[Depends(require_admin)])


def _when(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def summarise(rows: list[dict], connected_user_ids: set[str], now: datetime) -> dict:
    """Counts and a short list of who needs a look, from the sync_state rows."""
    due = running = failing = overdue = 0
    people = []
    for row in rows:
        user_id = str(row.get("user_id", ""))
        if connected_user_ids and user_id not in connected_user_ids:
            continue
        next_at = _when(row.get("next_sync_at"))
        claimed = _when(row.get("claimed_until"))
        fails = int(row.get("fail_count") or 0)
        is_running = bool(claimed and claimed > now)
        is_due = bool(next_at and next_at <= now and not is_running)
        is_overdue = bool(next_at and (now - next_at).total_seconds() > OVERDUE_GRACE_MINUTES * 60)
        running += is_running
        due += is_due
        failing += fails > 0
        overdue += is_overdue
        last_ok = _when(row.get("last_ok_at"))
        if fails > 0 or is_overdue:
            people.append({
                "who": user_id[:8],
                "state": "overdue" if is_overdue else "failing",
                "fail_count": fails,
                "last_error": (row.get("last_error") or "")[:200],
                "last_ok_minutes_ago": round((now - last_ok).total_seconds() / 60) if last_ok else None,
                "next_sync_in_minutes": round((next_at - now).total_seconds() / 60) if next_at else None,
            })
    people.sort(key=lambda p: (-p["fail_count"], p["who"]))
    return {"tracked": len([r for r in rows if not connected_user_ids or r.get("user_id") in connected_user_ids]), "due_now": due, "running": running, "failing": failing, "overdue": overdue, "needs_a_look": people[:25]}


@router.get("/status")
async def status(request: Request) -> JSONResponse:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    now = datetime.now(timezone.utc)
    out: dict = {"checked_at": now.isoformat(), "queue": None, "connected_people": None, "queue_table": "missing"}
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            conns = await client.get(f"{base}/rest/v1/user_connections", headers=headers, params={"is_active": "eq.true", "select": "user_id", "limit": "100000"})
            conns.raise_for_status()
            connected = {r["user_id"] for r in (conns.json() or [])}
            out["connected_people"] = len(connected)
            try:
                state = await client.get(f"{base}/rest/v1/sync_state", headers=headers, params={"select": "*", "limit": "100000"})
                state.raise_for_status()
                out["queue_table"] = "ok"
                out["queue"] = summarise(state.json() or [], connected, now)
            except Exception:
                out["queue_table"] = "missing"
    except Exception as exc:
        logger.warning("Sync status failed: %s", exc)
        out["error"] = "Couldn't read the database."
    task = getattr(request.app.state, "scheduler", None)
    out["server_clock"] = "running" if task is not None and not task.done() else ("switched off" if os.getenv("DISABLE_SCHEDULER", "").strip().lower() in ("1", "true", "yes") else "not running")
    out["error_alerts"] = "on" if os.getenv("SENTRY_DSN", "").strip() else "off"
    return JSONResponse(content=out)

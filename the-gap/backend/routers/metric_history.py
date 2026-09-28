"""
Full history for a single metric — "since you first connected", not just
the last 7 days kept in the snapshot. Populated as a byproduct of every
sync (see sync/daily_sync.py's _persist_metric_history) rather than
re-fetched from providers on demand, so opening a chart is instant.

Table DDL (run once in Supabase SQL editor):
  CREATE TABLE IF NOT EXISTS metric_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    date DATE NOT NULL,
    metric TEXT NOT NULL,
    value NUMERIC NOT NULL,
    UNIQUE(user_id, date, metric)
  );
  CREATE INDEX IF NOT EXISTS idx_metric_history_user_metric
    ON metric_history (user_id, metric, date);
"""

from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from auth import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/metric-history", tags=["metric-history"])


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers() -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


@router.get("/{metric}")
async def get_metric_history(metric: str, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                _sb_url("metric_history"),
                headers=_sb_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "metric": f"eq.{metric}",
                    "select": "date,value",
                    "order": "date.asc",
                },
            )
            resp.raise_for_status()
            return JSONResponse(content={"metric": metric, "history": resp.json() or []})
    except Exception as exc:
        logger.error("Metric history fetch failed for %s/%s: %s", user_id[:8], metric, exc)
        return JSONResponse(content={"metric": metric, "history": []})

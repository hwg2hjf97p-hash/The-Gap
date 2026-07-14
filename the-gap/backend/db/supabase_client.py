"""
Supabase client — insert analysis results and retrieve by session ID or by user.
Uses direct httpx REST calls to avoid supabase-py DNS resolution issues on Railway.

Table DDL (run once in Supabase SQL editor):

  CREATE TABLE results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    data_source TEXT NOT NULL,
    data_period_days INTEGER,
    insights JSONB NOT NULL,
    snapshot JSONB,
    experiments JSONB,
    share_url TEXT
  );

  CREATE INDEX IF NOT EXISTS idx_results_user_created
    ON results (user_id, created_at DESC);
"""

from __future__ import annotations

import logging
import os
from typing import Optional
from uuid import uuid4

import httpx

logger = logging.getLogger(__name__)


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def _is_configured() -> bool:
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    if not url or not key:
        logger.warning("SUPABASE_URL / SUPABASE_SERVICE_KEY not set — DB operations skipped")
        return False
    if not url.startswith("https://"):
        logger.warning("SUPABASE_URL does not look valid (%s)", url[:30])
        return False
    return True


def save_results(
    *,
    data_source: str,
    data_period_days: Optional[int],
    insights: list[dict],
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    snapshot: Optional[dict] = None,
    experiments: Optional[list[dict]] = None,
) -> str:
    """
    Persist analysis results to Supabase via direct REST API.
    Returns the session_id (UUID string).
    If Supabase is unavailable the results are still returned — just not stored.
    """
    session_id = session_id or str(uuid4())
    share_url = f"https://causalme.com/results/{session_id}"

    if not _is_configured():
        logger.warning("Supabase unavailable — results not persisted (session: %s)", session_id)
        return session_id

    payload = {
        "id": session_id,
        "user_id": user_id,
        "data_source": data_source,
        "data_period_days": data_period_days,
        "insights": insights,
        "snapshot": snapshot,
        "experiments": experiments,
        "share_url": share_url,
    }

    try:
        resp = httpx.post(
            _sb_url("results"),
            headers=_sb_headers(prefer="resolution=merge-duplicates,return=minimal"),
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        logger.info("Results saved to Supabase (session: %s, user: %s)", session_id, user_id[:8])
    except Exception as exc:
        logger.error("Supabase insert failed: %s", exc)
        # Don't raise — return session_id anyway so user still gets results

    return session_id


def get_results(session_id: str) -> Optional[dict]:
    """
    Retrieve a previously saved analysis by session_id.
    Returns None if not found or DB is unavailable.
    """
    if not _is_configured():
        return None

    try:
        resp = httpx.get(
            _sb_url("results"),
            headers=_sb_headers(),
            params={
                "id": f"eq.{session_id}",
                "select": "*",
                "limit": "1",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return data[0] if data else None
    except Exception as exc:
        logger.error("Supabase fetch failed for %s: %s", session_id, exc)
        return None


def get_latest_results(user_id: str) -> Optional[dict]:
    """
    Retrieve the most recent analysis for a user — this is what powers the
    always-on Home dashboard, as opposed to get_results() which needs an
    exact session_id from the one-time response right after analysis runs.
    """
    if not _is_configured():
        return None

    try:
        resp = httpx.get(
            _sb_url("results"),
            headers=_sb_headers(),
            params={
                "user_id": f"eq.{user_id}",
                "select": "*",
                "order": "created_at.desc",
                "limit": "1",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return data[0] if data else None
    except Exception as exc:
        logger.error("Supabase latest-results fetch failed for %s: %s", user_id[:8], exc)
        return None


# Keep _get_client for any legacy imports — returns None so callers degrade gracefully
def _get_client():
    logger.warning("_get_client() called — supabase-py is no longer used. Returning None.")
    return None

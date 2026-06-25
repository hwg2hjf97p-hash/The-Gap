"""
Supabase client — insert analysis results and retrieve by session ID.

Table DDL (run once in Supabase SQL editor):

  CREATE TABLE results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    data_source TEXT NOT NULL,
    data_period_days INTEGER,
    insights JSONB NOT NULL,
    share_url TEXT
  );
"""

from __future__ import annotations

import os
import logging
from typing import Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

# ── Lazy import so tests can run without supabase-py installed ──────────────
try:
    from supabase import create_client, Client as SupabaseClient  # type: ignore
    _SUPABASE_AVAILABLE = True
except ImportError:
    _SUPABASE_AVAILABLE = False
    SupabaseClient = None  # type: ignore


def _get_client() -> Optional["SupabaseClient"]:
    if not _SUPABASE_AVAILABLE:
        logger.warning("supabase-py not installed — DB operations skipped")
        return None

    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")

    if not url or not key:
        logger.warning("SUPABASE_URL / SUPABASE_SERVICE_KEY not set — DB operations skipped")
        return None

    try:
        return create_client(url, key)
    except Exception as exc:
        logger.warning("Supabase client init failed (%s) — DB operations skipped", exc)
        return None


def save_results(
    *,
    data_source: str,
    data_period_days: Optional[int],
    insights: list[dict],
    session_id: Optional[str] = None,
) -> str:
    """
    Persist analysis results to Supabase.
    Returns the session_id (UUID string).
    If Supabase is unavailable the results are still returned — just not stored.
    """
    session_id = session_id or str(uuid4())
    share_url = f"https://causalme.com/results/{session_id}"

    client = _get_client()
    if client is None:
        # Graceful degradation — app still works, just no persistence
        logger.warning("Supabase unavailable — results not persisted (session: %s)", session_id)
        return session_id

    try:
        client.table("results").insert(
            {
                "id": session_id,
                "data_source": data_source,
                "data_period_days": data_period_days,
                "insights": insights,
                "share_url": share_url,
            }
        ).execute()
        logger.info("Results saved to Supabase (session: %s)", session_id)
    except Exception as exc:
        logger.error("Supabase insert failed: %s", exc)
        # Don't raise — return session_id anyway so user still gets results

    return session_id


def get_results(session_id: str) -> Optional[dict]:
    """
    Retrieve a previously saved analysis by session_id.
    Returns None if not found or DB is unavailable.
    """
    client = _get_client()
    if client is None:
        return None

    try:
        response = (
            client.table("results")
            .select("*")
            .eq("id", session_id)
            .single()
            .execute()
        )
        return response.data
    except Exception as exc:
        logger.error("Supabase fetch failed for %s: %s", session_id, exc)
        return None

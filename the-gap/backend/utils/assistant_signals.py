"""
Turns what someone asks Gappy into another "sighting" for the causal
engine — the same idea as Quick Entry (utils/journal_extract.py extracts
structured signals from journal notes), just applied to assistant
questions instead. Asking "should I skip caffeine, I'm wired tonight"
reveals the same kind of signal a journal entry would.

Deliberately reuses the exact extraction prompt/model from
utils/journal_extract.py rather than a second one, and deliberately keeps
its own cache table (assistant_extractions) separate from
journal_extractions — so the Journal tab's "what Gappy extracted" sanity
check stays about journal entries only, with no assistant-derived
surprises in it.

Table DDL (run once in Supabase SQL editor):
  CREATE TABLE IF NOT EXISTS assistant_questions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    question_text TEXT NOT NULL,
    local_date DATE,
    created_at TIMESTAMPTZ DEFAULT NOW()
  );
  CREATE INDEX IF NOT EXISTS idx_assistant_questions_user_date
    ON assistant_questions (user_id, local_date);

  CREATE TABLE IF NOT EXISTS assistant_extractions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    entry_date DATE NOT NULL,
    question_count INTEGER NOT NULL DEFAULT 0,
    mood_score NUMERIC,
    stress_event INTEGER,
    travel_event INTEGER,
    illness_event INTEGER,
    conflict_event INTEGER,
    big_win_event INTEGER,
    summary TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, entry_date)
  );
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import httpx
import pandas as pd

from utils.journal_extract import extract_daily_signals

logger = logging.getLogger(__name__)


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


async def log_assistant_question(user_id: str, question: str, local_date: str | None) -> None:
    """Best-effort — a logging failure should never break the assistant's answer."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                _sb_url("assistant_questions"),
                headers={**_sb_headers(), "Prefer": "return=minimal"},
                json={"user_id": user_id, "question_text": question, "local_date": local_date},
            )
    except Exception as exc:
        logger.warning("Logging assistant question failed for %s: %s", user_id[:8], exc)


async def _get_cached_extractions(user_id: str, since_date: str) -> dict[str, dict]:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                _sb_url("assistant_extractions"),
                headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "entry_date": f"gte.{since_date}", "select": "*"},
            )
            resp.raise_for_status()
            return {r["entry_date"]: r for r in (resp.json() or [])}
    except Exception as exc:
        logger.warning("Fetching cached assistant extractions failed (will re-extract): %s", exc)
        return {}


async def _save_extraction(user_id: str, entry_date: str, question_count: int, signals: dict) -> None:
    payload = {
        "user_id": user_id,
        "entry_date": entry_date,
        "question_count": question_count,
        "mood_score": signals.get("mood_score"),
        "stress_event": signals.get("stress_event"),
        "travel_event": signals.get("travel_event"),
        "illness_event": signals.get("illness_event"),
        "conflict_event": signals.get("conflict_event"),
        "big_win_event": signals.get("big_win_event"),
        "summary": signals.get("summary", ""),
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _sb_url("assistant_extractions"),
                headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                params={"on_conflict": "user_id,entry_date"},
                json=payload,
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("Saving assistant extraction failed (will re-extract next sync): %s", exc)


async def get_assistant_signal_dataframe(user_id: str, days: int = 180) -> pd.DataFrame:
    """
    Same shape and column names as routers/journal.py's get_journal_dataframe
    (mood_score, stress_event, travel_event, illness_event, conflict_event,
    big_win_event) so daily_sync.py can fold it into the exact same existing
    hypotheses via combine_first — filling gaps a journal entry didn't
    already cover for that day, never overriding one that did.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    since_date = since[:10]
    today_str = datetime.now(timezone.utc).date().isoformat()

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                _sb_url("assistant_questions"),
                headers=_sb_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "created_at": f"gte.{since}",
                    "select": "question_text,created_at,local_date",
                    "order": "created_at.asc",
                },
            )
            resp.raise_for_status()
            rows = resp.json() or []
    except Exception as exc:
        logger.error("Assistant signal dataframe fetch failed: %s", exc)
        return pd.DataFrame()

    if not rows:
        return pd.DataFrame()

    by_date: dict[str, list[str]] = {}
    for r in rows:
        d = r.get("local_date") or r["created_at"][:10]
        by_date.setdefault(d, []).append(r["question_text"])

    cached = await _get_cached_extractions(user_id, since_date)

    records = {}
    for d, questions in by_date.items():
        needs_extraction = d == today_str or d not in cached
        if needs_extraction:
            signals = await extract_daily_signals(questions)
            if signals is not None:
                await _save_extraction(user_id, d, len(questions), signals)
                records[d] = {k: v for k, v in signals.items() if k != "summary"}
        else:
            c = cached[d]
            records[d] = {
                "mood_score": c.get("mood_score"),
                "stress_event": c.get("stress_event"),
                "travel_event": c.get("travel_event"),
                "illness_event": c.get("illness_event"),
                "conflict_event": c.get("conflict_event"),
                "big_win_event": c.get("big_win_event"),
            }

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame.from_dict(records, orient="index")
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    return df

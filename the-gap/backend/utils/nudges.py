"""
Proactive nudges — Gappy reaching out first instead of only answering when
asked. When today's (or last night's) data shows a binary treatment the
user already has a confirmed causal pattern for (e.g. they logged alcohol
last night and there's a confirmed alcohol -> HRV finding), push a heads-up
predicting how the outcome should move, grounded in their own numbers.

At most one nudge per user per calendar day (see proactive_nudges table)
so this stays a single clear signal rather than a stream of alerts.

Table DDL (run once in Supabase SQL editor):
  CREATE TABLE IF NOT EXISTS proactive_nudges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    nudge_date DATE NOT NULL,
    hypothesis_id TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, nudge_date)
  );
"""

from __future__ import annotations

import logging
import os
from datetime import date

import httpx
import pandas as pd

from causal.hypotheses import HYPOTHESES
from utils.push import send_push

logger = logging.getLogger(__name__)

_HYPOTHESES_BY_ID = {h.id: h for h in HYPOTHESES}


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


async def _already_nudged_today(user_id: str, today: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _sb_url("proactive_nudges"),
                headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "nudge_date": f"eq.{today}", "select": "id", "limit": "1"},
            )
            resp.raise_for_status()
            return bool(resp.json())
    except Exception as exc:
        logger.warning("Nudge dedupe check failed for %s (skipping nudge to be safe): %s", user_id[:8], exc)
        return True


async def _record_nudge(user_id: str, today: str, hypothesis_id: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                _sb_url("proactive_nudges"),
                headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                params={"on_conflict": "user_id,nudge_date"},
                json=[{"user_id": user_id, "nudge_date": today, "hypothesis_id": hypothesis_id}],
            )
    except Exception as exc:
        logger.warning("Recording nudge failed for %s: %s", user_id[:8], exc)


# Confidence order for picking the single strongest match, matching
# causal/engine.py's own strong -> moderate -> weak sort.
_CONFIDENCE_RANK = {"strong": 0, "moderate": 1, "weak": 2}


async def check_proactive_nudge(user_id: str, df: pd.DataFrame, insights: list[dict], active_hypothesis_ids: set[str]) -> None:
    """Best-effort — never raises. Called once per sync, after insights are
    computed, alongside the existing discovery-diff push logic."""
    if df is None or df.empty:
        return

    today = date.today().isoformat()
    try:
        if await _already_nudged_today(user_id, today):
            return

        latest_row = df.iloc[-1]
        candidates = []
        for insight in insights:
            hypothesis_id = insight.get("hypothesis_id", "")
            if hypothesis_id in active_hypothesis_ids:
                continue  # already being tried — no need to also nudge about it
            hyp = _HYPOTHESES_BY_ID.get(hypothesis_id)
            if hyp is None or not hyp.binary_treatment:
                continue
            if hyp.treatment_col not in latest_row.index:
                continue
            value = latest_row[hyp.treatment_col]
            if pd.isna(value) or not bool(value):
                continue
            candidates.append(insight)

        if not candidates:
            return

        candidates.sort(key=lambda i: _CONFIDENCE_RANK.get(i.get("confidence", "weak"), 2))
        best = candidates[0]

        # metric_direction on the Insight is "good vs bad", not "up vs down" —
        # the actual sign of metric_delta gives the up/down word instead.
        went_up = str(best.get("metric_delta", "")).startswith("+")
        direction = "go up" if went_up else "go down"

        await send_push(
            user_id,
            title="Heads up",
            body=(
                f"{best.get('treatment_label', 'This')} today — based on your data, "
                f"expect {best.get('outcome_label', 'this')} to {direction} by about "
                f"{best.get('metric_delta', '')}{best.get('metric_unit', '')}."
            ),
            data={"kind": "proactive_nudge", "hypothesis_id": best.get("hypothesis_id")},
        )
        await _record_nudge(user_id, today, best.get("hypothesis_id", ""))
    except Exception as exc:
        logger.warning("Proactive nudge check failed for %s: %s", user_id[:8], exc)

"""
Assistant — "Ask anything" about your own data.

Deliberately grounded: the system prompt is given the user's actual latest
insights + snapshot as context and told explicitly not to invent findings
that aren't in that data. This is a Q&A layer over real results, not a
general-purpose chatbot.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional

from auth import get_current_user_id
from db.supabase_client import get_latest_results
from utils.assistant_signals import log_assistant_question

from utils.consent import ai_allowed  # noqa: E402

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/assistant", tags=["assistant"])

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-6"  # this task needs real reasoning over data, unlike journal extraction

SYSTEM_PROMPT = """You are the in-app assistant for The Gap, a personal causal-analytics app. \
You answer questions about a specific user's own health/lifestyle data.

You will be given that user's most recent verified insights and a data snapshot. \
Answer ONLY using what's in that context. If the data doesn't support an answer \
(e.g. they ask about something not covered by their insights), say so plainly — \
don't invent a finding that isn't there. Don't give generic health advice not \
tied to their actual data; if you have nothing data-backed to say, say that \
directly and suggest what would need to be logged/connected to find out.

Keep answers short — 2-4 sentences, conversational, no headers or bullet lists. \
Reference specific numbers from their data when you have them."""


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    local_date: Optional[str] = None


def _build_context(results_row: dict | None) -> str:
    if not results_row:
        return "This user has no analysis results yet — no data sources connected, or not enough days of data yet."

    all_insights = results_row.get("insights") or []
    insights = [i for i in all_insights if i.get("confidence") != "weak"]
    early = [i for i in all_insights if i.get("confidence") == "weak"]
    snapshot = results_row.get("snapshot") or {}

    lines = []
    if insights:
        lines.append("Verified causal insights:")
        for i in insights:
            lines.append(
                f"- {i.get('headline', i.get('title', ''))}: {i.get('body', '')} "
                f"(confidence: {i.get('confidence_label', 'unknown')})"
            )
    else:
        lines.append("No verified causal insights yet — not enough data for statistical confidence.")
    if early:
        # Listed separately and labelled, so the assistant can mention them as
        # hints worth watching without ever stating them as established fact.
        lines.append("\nEarly signals (NOT verified — faint hints that may be chance; never state these as fact):")
        for i in early:
            lines.append(f"- {i.get('headline', i.get('title', ''))}")

    latest = snapshot.get("latest") or []
    if latest:
        lines.append("\nMost recent readings:")
        for m in latest:
            lines.append(f"- {m.get('label')}: {m.get('value')}{m.get('unit', '')} (trend: {m.get('trend')})")

    raw_signals = snapshot.get("raw_signals") or []
    if raw_signals:
        lines.append("\nRaw (not-yet-causally-tested) patterns being watched:")
        for s in raw_signals:
            lines.append(f"- {s.get('description')}: r={s.get('r')} (n={s.get('n')} days)")

    return "\n".join(lines)


MAX_QUESTIONS_PER_DAY = 40


async def _questions_in_last_day(user_id: str) -> int:
    """How many questions this person has asked in the last 24 hours. If the
    count can't be read, returns 0: the limit protects spend, and shouldn't be
    able to take the assistant down for everyone."""
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{base}/rest/v1/assistant_questions",
                headers={"apikey": key, "Authorization": f"Bearer {key}", "Prefer": "count=exact"},
                params={"user_id": f"eq.{user_id}", "created_at": f"gte.{since}", "select": "id", "limit": "1"},
            )
            resp.raise_for_status()
            return int(resp.headers.get("content-range", "0/0").split("/")[-1] or 0)
    except Exception as exc:
        logger.warning("Assistant usage count failed: %s", exc)
        return 0


@router.post("/ask")
async def ask(body: AskRequest, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="Assistant isn't configured yet.")

    if not await ai_allowed(user_id):
        raise HTTPException(status_code=403, detail="AI features are switched off. You can turn them on in Settings.")

    if await _questions_in_last_day(user_id) >= MAX_QUESTIONS_PER_DAY:
        raise HTTPException(status_code=429, detail="You've reached today's question limit for Gappy. Try again tomorrow.")

    results_row = get_latest_results(user_id)
    context = _build_context(results_row)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                ANTHROPIC_API_URL,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": MODEL,
                    "max_tokens": 300,
                    "system": SYSTEM_PROMPT,
                    "messages": [
                        {
                            "role": "user",
                            "content": f"User's data:\n{context}\n\nQuestion: {body.question}",
                        }
                    ],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            answer = "".join(
                block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
            ).strip()
    except Exception as exc:
        logger.error("Assistant request failed: %s", exc)
        raise HTTPException(status_code=502, detail="Couldn't reach the assistant. Try again.")

    # Best-effort — what someone asks can itself be a signal (see
    # utils/assistant_signals.py), but logging it should never be able to
    # fail the response the user is actually waiting on.
    try:
        await log_assistant_question(user_id, body.question, body.local_date)
    except Exception as exc:
        logger.warning("Logging assistant question failed: %s", exc)

    return JSONResponse(content={"answer": answer})

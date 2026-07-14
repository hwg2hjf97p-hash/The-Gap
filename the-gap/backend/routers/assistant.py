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

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from db.supabase_client import get_latest_results

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
    user_id: str
    question: str = Field(..., min_length=1, max_length=500)


def _build_context(results_row: dict | None) -> str:
    if not results_row:
        return "This user has no analysis results yet — no data sources connected, or not enough days of data yet."

    insights = results_row.get("insights") or []
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


@router.post("/ask")
async def ask(body: AskRequest) -> JSONResponse:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="Assistant isn't configured yet.")

    results_row = get_latest_results(body.user_id)
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

    return JSONResponse(content={"answer": answer})

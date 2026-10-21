"""
Assistant — "Ask anything" about your own data.

Deliberately grounded: the system prompt is given the user's actual latest
insights + snapshot as context and told explicitly not to invent findings
that aren't in that data. This is a Q&A layer over real results, not a
general-purpose chatbot.
"""

from __future__ import annotations

import asyncio
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
from utils.entitlement import require_subscription  # noqa: E402
from routers.subscriptions import is_on_trial  # noqa: E402

from utils import ai_budget
from utils import life_events
from utils.ai_budget import note_usage

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
Reference specific numbers from their data when you have them.

Big changes the person told us about (a lost job, a move, a loss, a new baby and so on) may be listed with dates. You may point out that a reading shifted around one of them, as something that happened alongside it and never as its cause, and you can say that big changes often take a toll on sleep and recovery. Be gentle, brief and never clinical about sensitive ones (a loss, a job ending, a breakup). Never give advice about grief, mood or mental health beyond saying that talking to someone they trust or a doctor can help. Never raise a life event unprompted if the question isn't related to how they've been.

Supplements (magnesium, melatonin, ashwagandha, creatine, fish oil and the like): you may say what the person's own logged days show, and you may explain in general terms what published research on one has looked at, always as information. Never recommend, suggest or tell anyone to take, start, stop or change a supplement or medicine. Never give a dose, a brand or a timing. Never say a supplement will improve or fix anything, and never tie a supplement to a result as if it were the cause. If asked "should I take X" or "what should I take for Y", say you can't advise on that, describe what their own data does or doesn't show, mention the research cards in the app, and say a doctor or pharmacist is the right person to ask, especially with medicines, pregnancy or a health condition.

Body measurements (weight, body fat) are sensitive. If asked, report them neutrally. Never set a target, never say a number is too high or too low, and never suggest losing weight, cutting calories or eating less. If someone asks about losing weight or body fat, say what their own data shows and suggest talking to a doctor or dietitian."""


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
# During the free month the assistant is the one feature that costs real money per use, so it is kept modest.
TRIAL_QUESTIONS_PER_DAY = 10


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
    await require_subscription(user_id)

    on_trial = await is_on_trial(user_id)
    limit = TRIAL_QUESTIONS_PER_DAY if on_trial else MAX_QUESTIONS_PER_DAY
    if await _questions_in_last_day(user_id) >= limit:
        detail = (
            f"You've used your {limit} questions for Gappy today. During your free month it's {limit} a day. Try again tomorrow."
            if on_trial
            else "You've reached today's question limit for Gappy. Try again tomorrow."
        )
        raise HTTPException(status_code=429, detail=detail)

    meter = await ai_budget.begin(user_id, "assistant")
    if meter.blocked:
        await ai_budget.finish(user_id, meter)
        raise HTTPException(status_code=429, detail=ai_budget.blocked_message(meter.status))

    results_row = await asyncio.to_thread(get_latest_results, user_id)
    context = _build_context(results_row)
    # Big changes the person told us about: the type and date only (never their note).
    events_text = await life_events.for_assistant(user_id)
    if events_text:
        context += "\n\nBig changes the person told us about (type and date only):\n" + events_text

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
            note_usage(MODEL, data.get("usage"))
            answer = "".join(
                block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
            ).strip()
    except Exception as exc:
        logger.error("Assistant request failed: %s", exc)
        raise HTTPException(status_code=502, detail="Couldn't reach the assistant. Try again.")
    finally:
        await ai_budget.finish(user_id, meter)

    # Best-effort — what someone asks can itself be a signal (see
    # utils/assistant_signals.py), but logging it should never be able to
    # fail the response the user is actually waiting on.
    try:
        await log_assistant_question(user_id, body.question, body.local_date)
    except Exception as exc:
        logger.warning("Logging assistant question failed: %s", exc)

    return JSONResponse(content={"answer": answer})

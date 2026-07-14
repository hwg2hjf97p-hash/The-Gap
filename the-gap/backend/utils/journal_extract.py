"""
Turns a day's worth of raw Quick Entry text into structured daily signals
that the causal engine can test against HRV, sleep, recovery, etc.

Deliberately calls the Anthropic API directly via httpx rather than adding
the full SDK as a dependency — mirrors how the rest of this backend talks
to Supabase directly for the same reason (fewer moving parts to break).
"""

from __future__ import annotations

import json
import logging
import os

import httpx

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-6"

EXTRACTION_SYSTEM_PROMPT = """You extract structured daily signals from a user's short, informal journal notes for a health-analytics app. You will receive several short notes a person jotted down over one day.

Respond with ONLY a JSON object, no other text, no markdown fences. Exact shape:
{
  "mood_score": <float from -1.0 (very bad day) to 1.0 (very good day), 0.0 if unclear>,
  "stress_event": <0 or 1 — did something notably stressful happen>,
  "travel_event": <0 or 1 — did they travel or have a disrupted routine/timezone change>,
  "illness_event": <0 or 1 — any mention of feeling sick, unwell, symptoms>,
  "conflict_event": <0 or 1 — any interpersonal conflict, argument, tension mentioned>,
  "big_win_event": <0 or 1 — notable good news, achievement, celebration>,
  "summary": "<one short plain-English sentence summarizing the day's notes, under 20 words>"
}

Be conservative: only set a flag to 1 if the notes clearly support it. If notes are sparse or ambiguous, prefer 0 and mood_score near 0.0. Never invent details not present in the notes."""


async def extract_daily_signals(entries: list[str]) -> dict | None:
    """
    entries: list of raw quick-entry text strings from a single day.
    Returns the structured signal dict, or None if extraction fails
    (callers should treat None as "no journal signal for this day",
    not as an error that should break the rest of the sync).
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key or not entries:
        return None

    joined = "\n".join(f"- {e.strip()}" for e in entries if e.strip())
    if not joined:
        return None

    try:
        async with httpx.AsyncClient(timeout=20) as client:
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
                    "system": EXTRACTION_SYSTEM_PROMPT,
                    "messages": [
                        {"role": "user", "content": f"Today's notes:\n{joined}"}
                    ],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = "".join(
                block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
            ).strip()
            # Defensive: strip accidental markdown fences even though the prompt forbids them
            text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            parsed = json.loads(text)

            return {
                "mood_score": float(parsed.get("mood_score", 0.0)),
                "stress_event": int(bool(parsed.get("stress_event", 0))),
                "travel_event": int(bool(parsed.get("travel_event", 0))),
                "illness_event": int(bool(parsed.get("illness_event", 0))),
                "conflict_event": int(bool(parsed.get("conflict_event", 0))),
                "big_win_event": int(bool(parsed.get("big_win_event", 0))),
                "summary": str(parsed.get("summary", ""))[:200],
            }
    except Exception as exc:
        logger.warning("Journal extraction failed (continuing without it): %s", exc)
        return None

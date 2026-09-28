"""
Generates a deeper, personalized "how do I improve this" plan for a
CONFIRMED insight — distinct from utils/hypothesis_explanation.py, which
explains an *unconfirmed* hypothesis's possible mechanisms. This is for
something already proven true about the user, expanding on the one-line
`actionable_tip` (causal/interpreter.py) that ships with every insight.

Most insights already have a good hardcoded actionable_tip from
interpreter.py's per-hypothesis copy. This exists mainly to give
user-proposed experiments (routers/experiments.py, hypothesis_id starting
"custom_") something better than interpreter.py's generic fallback tip —
but it's offered for every insight as an optional "go deeper" step.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You write a short, practical improvement plan for a wellness app called The Gap, for a cause-and-effect relationship ALREADY CONFIRMED in someone's own data using double machine learning (not a hypothesis, not a correlation — a verified finding for this specific person).

Use ONLY the facts given — never invent a number, a study, or a mechanism not implied by the facts. Never give medical advice or diagnose.

Write 3-4 short sentences, plain conversational language:
1. Acknowledge the confirmed finding in one line.
2. Give 2-3 concrete, specific, actionable steps someone could actually try this week to act on it — not generic wellness advice, but the specific implication of THIS relationship (e.g. if alcohol lowers their HRV, the action is about drinking nights, not generic "sleep more").
3. One honest closing line: this is what works for their own body based on their own data — not a universal rule, and it's fine to keep tracking to see how consistent it stays.

Respond with ONLY the plan text, no preamble, no markdown headers, no quotation marks."""


async def generate_improvement_plan(
    treatment_label: str,
    outcome_label: str,
    headline: str,
    existing_tip: str,
    metric_direction: str,
) -> str | None:
    facts = (
        f"Confirmed finding: {headline}\n"
        f"Treatment: {treatment_label}\n"
        f"Outcome: {outcome_label}\n"
        f"Direction: {metric_direction}\n"
        f"Existing one-line tip already shown: {existing_tip}"
    )

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
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
                    "max_tokens": 320,
                    "system": SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": facts}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = "".join(
                block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
            ).strip()
            return text or None
    except Exception as exc:
        logger.warning("Improvement plan generation failed (continuing without it): %s", exc)
        return None

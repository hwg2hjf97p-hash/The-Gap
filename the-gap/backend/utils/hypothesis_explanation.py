"""
Generates an honest, plain-language explanation of an in-progress
hypothesis for the "Running on you" cards — what's being tested, and a
few real, scientifically-grounded possible mechanisms for *why* this
relationship might exist. Explicitly NOT "guess which one is right" —
framed as genuine, testable uncertainty, since that's the actual honest
state of an unconfirmed hypothesis and it's the more credible thing to
show anyone evaluating the app's rigor.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You write a short, honest explanation for a wellness app called The Gap, which tests real cause-and-effect relationships in someone's own data using double machine learning.

You will be given real facts and a "kind" — either "hypothesis" (a formal cause-and-effect relationship currently being tested with enough data required before it can resolve) or "raw_signal" (a raw statistical correlation the app has noticed early, well before it has enough data to formally test it as a hypothesis — explicitly NOT evidence of causation yet, just a pattern worth watching).

Use ONLY the facts given — never invent a number, a study, a percentage, or claim anything is confirmed.

Write 3-5 short sentences, plain conversational language:
1. Restate in plain English what's being observed or tested.
2. Give 2-3 real, genuinely different, scientifically plausible reasons this relationship COULD exist — general physiological or behavioral mechanisms, not anything specific to this individual (since that hasn't been determined). Don't rank one as more likely than another.
3. End clearly stating this isn't confirmed. For "hypothesis", mention the current progress (day X of Y) as why it's unresolved. For "raw_signal", be extra explicit that a correlation is not the same as a cause — plenty of real correlations turn out to have no causal relationship at all once properly tested with enough data, and that's exactly why the app doesn't call it an insight yet.

Never claim the causal engine has already found evidence for any mechanism. Never diagnose or give medical advice. Respond with ONLY the explanation text, no preamble, no markdown, no quotation marks."""


async def generate_hypothesis_explanation(
    treatment_label: str,
    outcome_label: str,
    category: str,
    current_days: int,
    required_days: int,
) -> str | None:
    facts = (
        f"kind: hypothesis\n"
        f"Treatment being tested: {treatment_label}\n"
        f"Outcome being tested: {outcome_label}\n"
        f"Category: {category}\n"
        f"Progress: day {current_days} of {required_days} needed before this can be tested"
    )
    return await _call_anthropic(facts)


async def generate_raw_signal_explanation(
    description: str,
    r: float,
    direction: str,
    n: int,
) -> str | None:
    facts = (
        f"kind: raw_signal\n"
        f"Pattern being watched: {description}\n"
        f"Correlation strength so far: {abs(r):.2f} ({direction})\n"
        f"Days of data behind this so far: {n}\n"
        f"Note: this has NOT yet reached the ~30 days needed to formally test it as a hypothesis."
    )
    return await _call_anthropic(facts)


async def _call_anthropic(facts: str) -> str | None:
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
                    "max_tokens": 280,
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
        logger.warning("Hypothesis explanation generation failed (continuing without it): %s", exc)
        return None

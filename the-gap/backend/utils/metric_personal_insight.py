"""
Generates a short, personalized explanation of a user's latest reading
for one metric (e.g. "your HRV of 42ms..."), grounded in real numbers —
not the model inventing anything. Same direct-httpx-to-Anthropic pattern
as utils/journal_extract.py, for the same reason (one fewer dependency).

Cost control lives in routers/metric_insight.py, not here: a 1-hour
per-(user, metric) cache, and a daily cap on new generations per user.
This module only does the actual generation when the caller has already
decided a fresh one is warranted.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
# Haiku, not Sonnet — same reasoning as journal_extract.py: this is short
# grounded phrasing of facts we already computed, not open-ended reasoning.
MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You write a short, personal explanation of one health metric reading for a wellness app called The Gap. The app uses a causal inference engine (not just correlation) on the user's own data.

You will be given real facts about the reading, and optionally some profile context (age, weight, height). Use ONLY these facts — never invent a number, a study, a percentage, or a hypothesis that wasn't given to you.

Write 2-4 short sentences, plain conversational language, second person ("your reading of..."). Structure:
1. State their actual reading and how it compares to the population range given (if any).
2. If profile context (age/weight/height) was given, you may naturally note how someone with that profile might typically compare on this metric — phrased as a general, honestly-caveated comparison (e.g. "for someone your age/build, this is..."), NEVER as a precise statistical claim specific to them, since this is general context, not something the causal engine calculated for their exact profile.
3. If relevant hypotheses were given, mention that this metric is one the causal engine is actively testing against — name the specific hypothesis(es) by their given label. If NO hypotheses were given, say honestly that this metric isn't yet linked to a specific tested hypothesis, without making one up.
4. Keep it grounded and factual, not alarmist — this is informational, not medical advice. Never diagnose or tell them to see a doctor unless the facts given explicitly warrant a gentle "worth mentioning to a doctor if it persists" (only if genuinely relevant, and phrased gently).

Respond with ONLY the explanation text, no preamble, no markdown, no quotation marks around it."""


async def generate_personal_insight(
    metric_label: str,
    reading_value: str,
    unit: str,
    comparison_text: str,
    relevant_hypotheses: list[str],
    profile: dict | None = None,
) -> str | None:
    """
    relevant_hypotheses: list of human-readable hypothesis labels already
    known to involve this metric (e.g. ["Sleep duration -> Next-day HRV"]).
    Empty list is valid and expected for metrics not yet wired into any
    hypothesis (e.g. sleep_score at the time this was built) — the prompt
    is instructed to be honest about that rather than invent one.

    profile: optional {"weight_kg", "height_cm", "age"} — used purely as
    context for a general, honestly-caveated comparison in the writing,
    never as something the causal engine tested. A single person's
    weight/height/age don't vary day to day, so there's no real
    statistical relationship to detect for them specifically — seeing
    real variation in a large population is what would let a model learn
    "does this effect get stronger with X", and this app only ever
    analyzes one person's own days.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return None

    facts = (
        f"Metric: {metric_label}\n"
        f"Latest reading: {reading_value} {unit}\n"
        f"Population comparison: {comparison_text}\n"
        f"Hypotheses this metric feeds into: "
        + (", ".join(relevant_hypotheses) if relevant_hypotheses else "none yet")
    )
    if profile and any(profile.get(k) for k in ("age", "weight_kg", "height_cm")):
        profile_bits = []
        if profile.get("age"):
            profile_bits.append(f"age {profile['age']}")
        if profile.get("weight_kg"):
            profile_bits.append(f"weight {profile['weight_kg']}kg")
        if profile.get("height_cm"):
            profile_bits.append(f"height {profile['height_cm']}cm")
        facts += f"\nUser profile (optional context, not a calculated finding): {', '.join(profile_bits)}"

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
                    "max_tokens": 220,
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
        logger.warning("Metric insight generation failed (continuing without it): %s", exc)
        return None

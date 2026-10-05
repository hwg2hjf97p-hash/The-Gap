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

import json
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


STORY_SYSTEM_PROMPT = """You write the "what this means for you" card for a wellness app called The Gap. Someone's own data has revealed a cause-and-effect pattern about their body. Write it for a smart person with no health or statistics background.

Rules:
- Use ONLY the facts given. Never invent a number, a study, or a mechanism that isn't implied by the facts.
- Plain, warm, everyday words. Never write "causal", "statistically", "confounder" or similar. If you mention HRV or resting heart rate, say in a few words what it is the first time (e.g. "HRV, a measure of how recovered your body is").
- Never diagnose and never give medical advice. If the pattern could relate to illness, injury or a medical condition, use watch_out to say, gently, to check with a doctor if it persists.
- Non-judgmental, even when the finding is unfavourable. Speak to "you".
- Short. No filler.

Respond with ONLY a JSON object, no markdown fences, with exactly these keys:
{
  "headline": "<one friendly sentence, max 20 words, stating the pattern in everyday language>",
  "what_it_means": "<2-3 sentences, max 60 words: what is going on and why it matters for how they feel>",
  "what_to_try": ["<2-3 concrete things to try this week, each under 18 words, specific to THIS pattern>"],
  "things_that_might_help": [{"name": "<a generic kind of everyday product or resource, NO brand names, e.g. blackout curtains>", "why": "<under 15 words>"}],
  "watch_out": "<one sentence, or an empty string>"
}

things_that_might_help: 0 to 3 items, and ONLY if genuinely relevant to this exact pattern (an empty list is fine). Never include medicines or supplements of any kind."""

STORY_VERSION = 2


def _clean_str(value, limit: int) -> str:
    return str(value).strip()[:limit] if isinstance(value, (str, int, float)) else ""


def parse_story(raw: str | None) -> dict | None:
    """Parse and validate stored/generated story JSON; None if it isn't one."""
    if not raw:
        return None
    text = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(text)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    headline = _clean_str(data.get("headline"), 200)
    meaning = _clean_str(data.get("what_it_means"), 600)
    if not headline or not meaning:
        return None

    try_items = [_clean_str(t, 200) for t in (data.get("what_to_try") or []) if _clean_str(t, 200)][:3]
    help_items = []
    for item in (data.get("things_that_might_help") or [])[:3]:
        if isinstance(item, dict) and _clean_str(item.get("name"), 80):
            help_items.append({"name": _clean_str(item.get("name"), 80), "why": _clean_str(item.get("why"), 160)})

    return {
        "v": STORY_VERSION,
        "headline": headline,
        "what_it_means": meaning,
        "what_to_try": try_items,
        "things_that_might_help": help_items,
        "watch_out": _clean_str(data.get("watch_out"), 300),
    }


def flatten_story(story: dict) -> str:
    """Plain-text version for older app builds that only know plan_text."""
    parts = [story["what_it_means"]]
    parts += [f"- {t}" for t in story.get("what_to_try", [])]
    if story.get("watch_out"):
        parts.append(story["watch_out"])
    return "\n".join(parts)


async def generate_insight_story(
    treatment_label: str,
    outcome_label: str,
    headline: str,
    existing_tip: str,
    metric_direction: str,
    metric_delta: str = "",
    metric_unit: str = "",
    confidence_label: str = "",
    n_observations: int | None = None,
) -> dict | None:
    size = f"{metric_delta} {metric_unit}".strip() or "unknown"
    verdict = "good" if metric_direction == "positive" else "unfavourable"
    days = n_observations if n_observations is not None else "unknown"
    facts = "\n".join([
        f"Finding: {headline}",
        f"What changed (the cause): {treatment_label}",
        f"What it affects (the result): {outcome_label}",
        f"Size of the effect: {size}",
        f"Is this good or bad for them: {verdict}",
        f"How sure we are: {confidence_label}",
        f"Days of their data it's based on: {days}",
        f"One-line tip already shown: {existing_tip}",
    ])

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return None

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
                    "max_tokens": 700,
                    "system": STORY_SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": facts}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = "".join(
                block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
            ).strip()
            return parse_story(text)
    except Exception as exc:
        logger.warning("Insight story generation failed (continuing without it): %s", exc)
        return None


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

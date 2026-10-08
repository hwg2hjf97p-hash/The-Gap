"""
The one personal sentence at the top of a "Check this out" card, built from a
person's goal: what they're aiming for and where they are now.

Claude Haiku writes it, and only it. It never sees a name, email or account id,
only the metric, the direction and two numbers. It can't touch the research
finding below it, which comes from the approved library word for word. If the
person has switched AI features off, the AI is unavailable, or its sentence
breaks any rule below, a plain template sentence is used instead.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from typing import Optional

import httpx

from utils.consent import ai_allowed
from utils.evidence_checks import numbers_in
from utils.goal_catalog import GoalMetric
from utils.goals import fmt

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"
CACHE_VERSION = "v1"
MAX_WORDS = 32

SYSTEM_PROMPT = """You write one short, friendly sentence for a health app, saying what a person is aiming for and where they are now.

Use ONLY the facts you are given. Use the numbers exactly as written and add no others. Write exactly one sentence of at most 28 words. Do not give advice, suggestions or instructions. Do not mention research, studies, evidence or science. Do not use exclamation marks. You may say "you" and "your". Return only the sentence."""

# Anything that turns the sentence into advice, a claim about research, or a promise.
FORBIDDEN = re.compile(
    r"\b(should|must|ought|need to|needs to|have to|try|recommend\w*|advise\w*|suggest\w*|"
    r"research|stud(?:y|ies)|evidence|science|scientific|proven?|prove[sd]?|cure[sd]?|prevent\w*|treat\w*|guarantee\w*)\b",
    re.IGNORECASE,
)


def _unit(metric: GoalMetric) -> str:
    return metric.unit if metric.unit.startswith("/") else f" {metric.unit}"


def facts_for(metric: GoalMetric, direction: str, current: Optional[float], target: Optional[float]) -> dict:
    return {
        "label": metric.label,
        "direction": direction,
        "current": None if current is None else fmt(current, metric.decimals),
        "target": None if target is None else fmt(target, metric.decimals),
        "unit": _unit(metric),
    }


def template_intro(facts: dict) -> str:
    """The sentence used when the AI isn't used or isn't trusted."""
    label = facts["label"].lower()
    unit, target, current = facts["unit"], facts["target"], facts["current"]
    if facts["direction"] == "maintain":
        aim = f"You're aiming to hold your {label} around {target}{unit}"
    elif facts["direction"] == "decrease":
        aim = f"You're aiming to bring your {label} down to {target}{unit}"
    else:
        aim = f"You're aiming to bring your {label} up to {target}{unit}"
    if current is not None:
        return f"{aim}, and your 7-day average is {current}{unit}."
    return f"{aim}."


def intro_is_valid(text: str, facts: dict) -> bool:
    """True only when the sentence stays inside the facts it was given and avoids advice and research claims."""
    text = (text or "").strip()
    if not text or "\n" in text or len(text.split()) > MAX_WORDS or "!" in text:
        return False
    if len(re.findall(r"[.?](?:\s|$)", text)) > 1:
        return False
    if FORBIDDEN.search(text):
        return False
    allowed = numbers_in(" ".join(str(facts.get(k) or "") for k in ("current", "target"))) | {"7"}
    return numbers_in(text) <= allowed


def cache_key(facts: dict) -> str:
    raw = "|".join([CACHE_VERSION, facts["label"], facts["direction"], str(facts["current"]), str(facts["target"]), facts["unit"]])
    return hashlib.sha256(raw.encode()).hexdigest()[:40]


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


async def _cache_get(key: str) -> Optional[str]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(_sb_url("intro_cache"), headers=_sb_headers(), params={"cache_key": f"eq.{key}", "select": "intro_text", "limit": "1"})
            resp.raise_for_status()
            rows = resp.json() or []
            return rows[0]["intro_text"] if rows else None
    except Exception as exc:
        logger.info("Intro cache read failed: %s", exc)
        return None


async def _cache_put(key: str, text: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                _sb_url("intro_cache"), headers=_sb_headers("resolution=merge-duplicates,return=minimal"), params={"on_conflict": "cache_key"}, json={"cache_key": key, "intro_text": text}
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.info("Intro cache write failed: %s", exc)


async def _call_haiku(facts: dict) -> Optional[str]:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return None
    lines = [f"Metric: {facts['label']}", f"Direction: {facts['direction']}"]
    if facts["current"] is not None:
        lines.append(f"Current 7-day average: {facts['current']}{facts['unit']}")
    lines.append(f"Target: {facts['target']}{facts['unit']}")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                ANTHROPIC_API_URL,
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": MODEL, "max_tokens": 120, "system": SYSTEM_PROMPT, "messages": [{"role": "user", "content": "\n".join(lines)}]},
            )
            resp.raise_for_status()
            return "".join(b.get("text", "") for b in resp.json().get("content", []) if b.get("type") == "text").strip()
    except Exception as exc:
        logger.warning("Intro sentence generation failed (using the plain sentence): %s", exc)
        return None


async def make_intro(user_id: str, metric: GoalMetric, direction: str, current: Optional[float], target: Optional[float]) -> str:
    """The sentence for a card: a cached or fresh AI sentence when allowed and valid, otherwise the template."""
    facts = facts_for(metric, direction, current, target)
    fallback = template_intro(facts)
    if target is None or not await ai_allowed(user_id):
        return fallback
    key = cache_key(facts)
    cached = await _cache_get(key)
    if cached and intro_is_valid(cached, facts):
        return cached
    drafted = await _call_haiku(facts)
    if drafted and intro_is_valid(drafted, facts):
        await _cache_put(key, drafted)
        return drafted
    return fallback

"""
A monthly AI allowance per person.

The daily limits on each AI feature stop a burst, but not a steady month of
heavy use: someone using every limit, every day, would cost more in AI than
they pay. This keeps a running total of what each person's AI use costs this
month (worked out from the token counts the AI service reports back) and stops
the costly features when the allowance is used up. It resets on the 1st (UTC).

What "used up" means, by feature:
  - Gappy (the assistant) answers with a friendly "used this month's allowance"
    message (HTTP 429).
  - Everything else (explanations, plans, insights, recipe ideas, the daily
    plan wording) quietly shows its usual written fallback instead of AI text.

The allowance depends on the person's plan (US$ of AI use a month; tune with
environment variables, no code change):
  AI_BUDGET_TRIAL_USD  during the free month        (default 1.00)
  AI_BUDGET_PLUS_USD   a paying subscriber           (default 2.50)
  AI_BUDGET_PRO_USD    a higher "Pro" plan, if sold  (default 7.50)
  AI_BUDGET_ENFORCE    "false" counts usage without stopping anything
  AI_PRO_PRODUCT_MARKER  text found in the product id of Pro products (default ".pro")

It never takes a feature down by mistake: if the usage can't be read (database
hiccup, table not created yet) the person is let through, and if it can't be
recorded that is only logged.

Table and function DDL (run once in the Supabase SQL editor; also in phase17.sql):
  CREATE TABLE IF NOT EXISTS ai_usage_month (
    user_id TEXT NOT NULL, month TEXT NOT NULL, feature TEXT NOT NULL,
    micro_usd BIGINT NOT NULL DEFAULT 0,      -- millionths of a US dollar
    calls INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, month, feature)
  );
  ALTER TABLE ai_usage_month ENABLE ROW LEVEL SECURITY;
  -- plus the add_ai_usage(...) function, see phase17.sql
"""

from __future__ import annotations

import contextvars
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# US$ per million tokens: (input, output). A model not listed here is counted at
# the dearest rate, so the allowance errs on the safe side.
PRICES: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
}
DEFAULT_PRICE = (3.0, 15.0)

DEFAULT_BUDGET_USD = {"trial": 1.0, "plus": 2.5, "pro": 7.5}
BUDGET_ENV = {"trial": "AI_BUDGET_TRIAL_USD", "plus": "AI_BUDGET_PLUS_USD", "pro": "AI_BUDGET_PRO_USD"}


# ── Pure rules (no network) ──────────────────────────────────────────────────

def cost_micro(model: str, usage: Optional[dict]) -> int:
    """The cost of one AI call in millionths of a US dollar. Price is US$ per
    million tokens, so tokens x price is already in millionths of a dollar."""
    if not isinstance(usage, dict):
        return 0
    pin, pout = PRICES.get(model, DEFAULT_PRICE)
    tokens_in = int(usage.get("input_tokens") or 0)
    tokens_out = int(usage.get("output_tokens") or 0)
    return max(0, round(tokens_in * pin + tokens_out * pout))


def month_key(now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


def resets_on(now: Optional[datetime] = None) -> str:
    """The date the allowance starts again: the 1st of next month (UTC)."""
    now = now or datetime.now(timezone.utc)
    year, month = (now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1)
    return f"{year:04d}-{month:02d}-01"


def budget_micro(tier: str) -> int:
    default = DEFAULT_BUDGET_USD.get(tier, DEFAULT_BUDGET_USD["plus"])
    raw = os.getenv(BUDGET_ENV.get(tier, BUDGET_ENV["plus"]), "").strip()
    try:
        usd = float(raw) if raw else default
    except ValueError:
        usd = default
    if usd <= 0:
        usd = default
    return round(usd * 1_000_000)


def enforcing() -> bool:
    return os.getenv("AI_BUDGET_ENFORCE", "true").strip().lower() not in ("0", "false", "no", "off")


def tier_from_row(row: Optional[dict], now: Optional[datetime] = None) -> str:
    """"trial" in the free month, "pro" for a Pro product, otherwise "plus".
    No subscription row (testers, free access) counts as "plus"."""
    now = now or datetime.now(timezone.utc)
    if not row or not row.get("is_active"):
        return "plus"
    expires = row.get("expires_at")
    if expires:
        try:
            if datetime.fromisoformat(str(expires).replace("Z", "+00:00")) < now:
                return "plus"
        except ValueError:
            pass
    if str(row.get("period_type") or "").upper() == "TRIAL":
        return "trial"
    marker = os.getenv("AI_PRO_PRODUCT_MARKER", ".pro").strip().lower() or ".pro"
    if marker in str(row.get("product_id") or "").lower():
        return "pro"
    return "plus"


def summarize(used_micro: int, tier: str, now: Optional[datetime] = None) -> dict:
    budget = budget_micro(tier)
    pct = 100 if used_micro >= budget else int(used_micro * 100 / budget)
    return {"tier": tier, "used_pct": min(100, pct), "exhausted": used_micro >= budget, "resets_on": resets_on(now)}


def blocked_message(status: dict) -> str:
    when = status.get("resets_on", "the 1st")
    if status.get("tier") == "trial":
        return f"You've used the AI allowance for your free month. It starts again on {when}, and the rest of The Gap keeps working."
    return f"You've used this month's AI allowance. It starts again on {when}, and the rest of The Gap keeps working."


# ── Reading and recording usage ──────────────────────────────────────────────

def _sb_url(path: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{path}"


def _sb_headers() -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


async def _subscription_row(client: httpx.AsyncClient, user_id: str) -> Optional[dict]:
    resp = await client.get(
        _sb_url("user_subscriptions"), headers=_sb_headers(),
        params={"user_id": f"eq.{user_id}", "select": "is_active,expires_at,period_type,product_id", "limit": 1},
    )
    resp.raise_for_status()
    rows = resp.json() or []
    return rows[0] if rows else None


async def _used_micro(client: httpx.AsyncClient, user_id: str, month: str) -> int:
    resp = await client.get(
        _sb_url("ai_usage_month"), headers=_sb_headers(),
        params={"user_id": f"eq.{user_id}", "month": f"eq.{month}", "select": "micro_usd"},
    )
    resp.raise_for_status()
    return sum(int(r.get("micro_usd") or 0) for r in (resp.json() or []))


async def status(user_id: str) -> dict:
    """This person's allowance right now. If it can't be worked out, they are not blocked."""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            row = await _subscription_row(client, user_id)
            tier = tier_from_row(row)
            used = await _used_micro(client, user_id, month_key())
        return summarize(used, tier)
    except Exception as exc:
        logger.warning("AI allowance check failed for %s (letting it through): %s", user_id[:8], exc)
        return {"tier": "plus", "used_pct": 0, "exhausted": False, "resets_on": resets_on(), "unknown": True}


async def _record(user_id: str, feature: str, micro: int, calls: int) -> None:
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.post(
                _sb_url("rpc/add_ai_usage"), headers=_sb_headers(),
                json={"p_user": user_id, "p_month": month_key(), "p_feature": feature, "p_micro": int(micro), "p_calls": int(calls)},
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("AI usage not recorded for %s (is phase17.sql run?): %s", user_id[:8], exc)


# ── Metering a request ───────────────────────────────────────────────────────

@dataclass
class Meter:
    feature: str
    blocked: bool = False
    status: dict = field(default_factory=dict)
    micro: int = 0
    calls: int = 0
    _token: Optional[contextvars.Token] = None


_current: contextvars.ContextVar[Optional[Meter]] = contextvars.ContextVar("ai_meter", default=None)


def note_usage(model: str, usage: Optional[dict]) -> None:
    """Called where an AI response is read. Counts toward the request being
    metered; does nothing for AI calls made outside one (background jobs)."""
    meter = _current.get()
    if meter is None:
        return
    micro = cost_micro(model, usage)
    if micro:
        meter.micro += micro
        meter.calls += 1


async def begin(user_id: str, feature: str) -> Meter:
    """Checks the allowance and starts counting. Check meter.blocked before calling the AI."""
    meter = Meter(feature=feature)
    meter.status = await status(user_id)
    meter.blocked = enforcing() and bool(meter.status.get("exhausted"))
    meter._token = _current.set(meter)
    return meter


async def finish(user_id: str, meter: Meter) -> None:
    """Stops counting and adds what was used to this month's total."""
    if meter._token is not None:
        try:
            _current.reset(meter._token)
        except ValueError:
            pass  # finished from a different context: nothing leaks, each request has its own
        meter._token = None
    if meter.micro > 0:
        await _record(user_id, meter.feature, meter.micro, meter.calls)
        meter.micro = 0


@asynccontextmanager
async def metered(user_id: str, feature: str):
    """
        async with metered(user_id, "feature") as m:
            text = None if m.blocked else await generate(...)
    """
    meter = await begin(user_id, feature)
    try:
        yield meter
    finally:
        await finish(user_id, meter)

"""
Static profile info (weight, height, age) — used purely as context for
the personalized metric-insight text (see utils/metric_personal_insight.py),
NOT as causal hypothesis inputs. A single person's weight/height/age don't
vary day to day in this app's data, so there's no "before vs after" for
the causal engine to test — see the conversation that led to this file
for the fuller reasoning. This exists so Claude can write something like
"for someone your age and build, a recovery score in this range after
12,000 steps is fairly typical" — an informed comparison, not a
statistical finding.

Table DDL (run once in Supabase SQL editor):
  CREATE TABLE IF NOT EXISTS user_profile (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL UNIQUE,
    weight_kg NUMERIC,
    height_cm NUMERIC,
    age INTEGER,
    updated_at TIMESTAMPTZ DEFAULT NOW()
  );
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


async def save_user_profile(user_id: str, weight_kg: float | None, height_cm: float | None, age: int | None) -> bool:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _sb_url("user_profile"),
                headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                params={"on_conflict": "user_id"},
                json=[{
                    "user_id": user_id,
                    "weight_kg": weight_kg,
                    "height_cm": height_cm,
                    "age": age,
                }],
            )
            resp.raise_for_status()
            return True
    except Exception as exc:
        logger.warning("Saving user profile failed: %s", exc)
        return False


async def get_user_profile(user_id: str) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                _sb_url("user_profile"),
                headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "select": "weight_kg,height_cm,age", "limit": 1},
            )
            resp.raise_for_status()
            rows = resp.json() or []
            return rows[0] if rows else None
    except Exception as exc:
        logger.warning("Fetching user profile failed: %s", exc)
        return None

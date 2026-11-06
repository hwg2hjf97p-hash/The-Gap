"""
What a person told the setup: their sex (optional), what they want out of The Gap, and their "prime suspect" (see mobile
lib/setupFlow.ts and new_onboarding_design.md).

Kept in its own small table (phase31.sql). Their first name is never sent: it stays on the phone. These answers are only stored for now;
nothing else reads them yet. Every field is optional, and anything the app sends that isn't one of the known choices is dropped rather
than refused, so adding a choice in the app never makes a save fail.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

SEX = ("female", "male", "other", "none")
WANTS = ("sleep", "energy", "train", "eat", "stress", "muscle", "curious")
SUSPECTS = ("coffee", "late_nights", "screens", "stress", "skipping_workouts", "alcohol", "sugar", "water", "no_idea")


def clean_answers(raw: Any) -> dict:
    """The answers as they will be stored: only known choices, no repeats, in the order the app lists them."""
    raw = raw if isinstance(raw, dict) else {}
    sex = raw.get("sex") if raw.get("sex") in SEX else None
    suspect = raw.get("suspect") if raw.get("suspect") in SUSPECTS else None
    given = raw.get("wants") if isinstance(raw.get("wants"), list) else []
    wants = [w for w in WANTS if w in given]
    return {"sex": sex, "wants": wants, "suspect": suspect}


def _sb_url(table: str) -> str:
    return f"{os.getenv('SUPABASE_URL', '').strip().rstrip('/')}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        headers["Prefer"] = prefer
    return headers


async def save_answers(user_id: str, answers: dict) -> bool:
    """Store (replace) this person's answers. False if the table isn't there yet (phase31.sql not run) or the save failed."""
    row = {"user_id": user_id, **answers, "updated_at": datetime.now(timezone.utc).isoformat()}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                _sb_url("onboarding_answers"),
                headers=_sb_headers("resolution=merge-duplicates,return=minimal"),
                params={"on_conflict": "user_id"},
                json=row,
            )
            resp.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("Saving onboarding answers failed (is phase31.sql run?): %s", exc)
        return False


async def load_answers(user_id: str) -> Optional[dict]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(_sb_url("onboarding_answers"), headers=_sb_headers(), params={"user_id": f"eq.{user_id}", "select": "sex,wants,suspect", "limit": "1"})
            resp.raise_for_status()
            rows = resp.json() or []
        return clean_answers(rows[0]) if rows else None
    except Exception as exc:
        logger.warning("Reading onboarding answers failed: %s", exc)
        return None

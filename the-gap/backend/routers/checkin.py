"""
Manual daily check-in router for The Gap.
Captures lifestyle variables that wearables don't track:
  - alcohol (yes/no)
  - afternoon caffeine after 2pm (yes/no)
  - stress score (1-10)

Stored in Supabase daily_checkins table.
Merged into health data during analysis to unlock lifestyle hypotheses.

Table DDL:
  CREATE TABLE IF NOT EXISTS daily_checkins (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    date DATE NOT NULL,
    alcohol BOOLEAN DEFAULT false,
    afternoon_caffeine BOOLEAN DEFAULT false,
    stress_score INTEGER CHECK (stress_score BETWEEN 1 AND 10),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, date)
  );
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/checkin", tags=["checkin"])


# ── Supabase REST helpers ─────────────────────────────────────────────────────

def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


# ── Request / Response models ─────────────────────────────────────────────────

class CheckInRequest(BaseModel):
    user_id: str
    date: str = Field(default_factory=lambda: date.today().isoformat())
    alcohol: bool = False
    afternoon_caffeine: bool = False
    stress_score: Optional[int] = Field(None, ge=1, le=10)
    notes: Optional[str] = None

    @validator("date")
    def validate_date(cls, v):
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("date must be YYYY-MM-DD format")
        return v


class CheckInResponse(BaseModel):
    success: bool
    date: str
    streak: int = 0


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/")
async def submit_checkin(body: CheckInRequest) -> JSONResponse:
    """Submit or update a daily check-in."""
    payload = {
        "user_id": body.user_id,
        "date": body.date,
        "alcohol": body.alcohol,
        "afternoon_caffeine": body.afternoon_caffeine,
        "stress_score": body.stress_score,
        "notes": body.notes,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _sb_url("daily_checkins"),
                headers=_sb_headers(prefer="resolution=merge-duplicates,return=minimal"),
                json=payload,
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.error("Check-in save failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save check-in.")

    streak = await _get_streak(body.user_id)

    return JSONResponse(content={
        "success": True,
        "date": body.date,
        "streak": streak,
    })


@router.get("/{user_id}/recent")
async def get_recent_checkins(user_id: str, days: int = 30) -> JSONResponse:
    """Get recent check-ins for a user — used to pre-fill today's form."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _sb_url("daily_checkins"),
                headers=_sb_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "date": f"gte.{since}",
                    "select": "date,alcohol,afternoon_caffeine,stress_score,notes",
                    "order": "date.desc",
                },
            )
            resp.raise_for_status()
            return JSONResponse(content={"checkins": resp.json() or []})
    except Exception as exc:
        logger.error("Check-in fetch failed: %s", exc)
        return JSONResponse(content={"checkins": []})


@router.get("/{user_id}/today")
async def get_today_checkin(user_id: str) -> JSONResponse:
    """Get today's check-in if it exists."""
    today = date.today().isoformat()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _sb_url("daily_checkins"),
                headers=_sb_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "date": f"eq.{today}",
                    "select": "*",
                    "limit": "1",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return JSONResponse(content={"checkin": data[0] if data else None})
    except Exception as exc:
        logger.error("Today check-in fetch failed: %s", exc)
        return JSONResponse(content={"checkin": None})


async def _get_streak(user_id: str) -> int:
    """Calculate current consecutive check-in streak."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _sb_url("daily_checkins"),
                headers=_sb_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "select": "date",
                    "order": "date.desc",
                    "limit": "90",
                },
            )
            resp.raise_for_status()
            rows = resp.json() or []

        dates = sorted(
            [datetime.strptime(r["date"], "%Y-%m-%d").date() for r in rows],
            reverse=True,
        )
        if not dates:
            return 1

        streak = 1
        today = date.today()
        expected = today if dates[0] == today else today - timedelta(days=1)

        for d in dates:
            if d == expected:
                streak += 1
                expected = expected - timedelta(days=1)
            else:
                break

        return max(streak - 1, 1)
    except Exception:
        return 1


def get_checkin_dataframe(user_id: str, days: int = 90):
    """
    Fetch check-in data as a DataFrame for merging into health analysis.
    Returns DataFrame with columns: alcohol_flag, afternoon_caffeine,
    stress_score, high_stress_flag indexed by date.
    """
    import pandas as pd

    since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    try:
        resp = httpx.get(
            _sb_url("daily_checkins"),
            headers=_sb_headers(),
            params={
                "user_id": f"eq.{user_id}",
                "date": f"gte.{since}",
                "select": "date,alcohol,afternoon_caffeine,stress_score",
            },
            timeout=10,
        )
        resp.raise_for_status()
        rows = resp.json() or []
        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()

        # Rename to The Gap column names
        df = df.rename(columns={
            "alcohol": "alcohol_flag",
            "afternoon_caffeine": "afternoon_caffeine",
        })
        df["alcohol_flag"] = df["alcohol_flag"].astype(int)
        df["afternoon_caffeine"] = df["afternoon_caffeine"].astype(int)

        if "stress_score" in df.columns:
            df["stress_score"] = pd.to_numeric(df["stress_score"], errors="coerce")
            df["high_stress_flag"] = (df["stress_score"] >= 7).astype(int)

        return df
    except Exception as exc:
        logger.error("Check-in DataFrame fetch failed: %s", exc)
        return pd.DataFrame()

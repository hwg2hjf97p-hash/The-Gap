"""
Manual daily check-in router for The Gap.
Captures lifestyle variables that wearables don't track:
  - alcohol (yes/no, plus number of drinks and time of day)
  - afternoon caffeine after 2pm (yes/no)
  - stress score (1-10)
  - energy drinks, cigarettes, gambling, other substances (private), work,
    arguments, travel — each an amount and/or a time of day / duration

Stored in Supabase daily_checkins table, one row per (user, date). Saving a
date that already has a row overwrites it — that is how editing yesterday's
check-in works. Merged into health data during analysis to unlock
lifestyle hypotheses.

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
  -- The extra categories (alcohol_drinks, energy_drinks, ...) are added by
  -- checkin_phase1.sql. Until that has been run the router keeps working:
  -- it falls back to saving only the original columns.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator

from auth import get_current_user_id

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

TIME_OF_DAY = {"morning", "afternoon", "evening", "late"}
WORK_FINISH = {"before_5pm", "5_8pm", "8_10pm", "after_10pm"}
TRAVEL_MODES = {"car", "plane", "train_bus", "other"}
SCREEN_LAST_USE = {"before_9pm", "9_11pm", "11pm_1am", "after_1am"}

# Columns added by checkin_phase1.sql — everything beyond the original four.
EXTENDED_FIELDS = (
    "alcohol_drinks", "alcohol_time", "energy_drinks", "energy_drink_time",
    "cigarettes", "gambling_minutes", "gambling_time", "substance_use",
    "substance_time", "work_hours", "work_finish", "argument_count",
    "argument_intensity", "travel_hours", "travel_mode", "screen_hours", "screen_last_use",
)


def _one_of(allowed: set[str], value):
    return value if value in allowed else None


class CheckInRequest(BaseModel):
    date: str = Field(default_factory=lambda: date.today().isoformat())
    alcohol: bool = False
    afternoon_caffeine: bool = False
    stress_score: Optional[int] = Field(None, ge=1, le=10)
    notes: Optional[str] = None

    # None means "not asked / not answered", which is different from 0
    # ("none") — the engine only treats an explicit 0 as a real zero.
    alcohol_drinks: Optional[int] = Field(None, ge=0, le=40)
    alcohol_time: Optional[str] = None
    energy_drinks: Optional[int] = Field(None, ge=0, le=20)
    energy_drink_time: Optional[str] = None
    cigarettes: Optional[int] = Field(None, ge=0, le=100)
    gambling_minutes: Optional[int] = Field(None, ge=0, le=1440)
    gambling_time: Optional[str] = None
    substance_use: Optional[bool] = None
    substance_time: Optional[str] = None
    work_hours: Optional[float] = Field(None, ge=0, le=24)
    work_finish: Optional[str] = None
    argument_count: Optional[int] = Field(None, ge=0, le=20)
    argument_intensity: Optional[int] = Field(None, ge=1, le=3)
    travel_hours: Optional[float] = Field(None, ge=0, le=48)
    travel_mode: Optional[str] = None
    screen_hours: Optional[float] = Field(None, ge=0, le=24)
    screen_last_use: Optional[str] = None

    @validator("date")
    def validate_date(cls, v):
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("date must be YYYY-MM-DD format")
        return v

    @validator("alcohol_time", "energy_drink_time", "gambling_time", "substance_time")
    def validate_time_of_day(cls, v):
        return _one_of(TIME_OF_DAY, v)

    @validator("work_finish")
    def validate_work_finish(cls, v):
        return _one_of(WORK_FINISH, v)

    @validator("travel_mode")
    def validate_travel_mode(cls, v):
        return _one_of(TRAVEL_MODES, v)

    @validator("screen_last_use")
    def validate_screen_last_use(cls, v):
        return _one_of(SCREEN_LAST_USE, v)


class CheckInResponse(BaseModel):
    success: bool
    date: str
    streak: int = 0


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/")
async def submit_checkin(body: CheckInRequest, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    """Submit or update a daily check-in. Saving a date that already has one
    replaces it (same row), so correcting yesterday never creates a duplicate."""
    alcohol = body.alcohol
    if body.alcohol_drinks is not None:
        # The drink count is the source of truth when it's given.
        alcohol = body.alcohol_drinks > 0

    base_payload = {
        "user_id": user_id,
        "date": body.date,
        "alcohol": alcohol,
        "afternoon_caffeine": body.afternoon_caffeine,
        "stress_score": body.stress_score,
        "notes": body.notes,
    }
    # Every extended field is sent, null included, so clearing a value on an
    # edit actually clears it rather than leaving the old number behind.
    extended = {f: getattr(body, f) for f in EXTENDED_FIELDS}

    # Without on_conflict, PostgREST upserts on the primary key (id), which a
    # fresh row never collides with — a second save for the same day then hit
    # the UNIQUE(user_id, date) constraint and failed. Naming the real key
    # makes an edit replace the existing row.
    params = {"on_conflict": "user_id,date"}
    headers = _sb_headers(prefer="resolution=merge-duplicates,return=minimal")

    extended_saved = True
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            payload = {**base_payload, **extended}
            resp = None
            # If a column hasn't been added to the table yet (its SQL file not run), leave out just
            # that column and save the rest, rather than losing every newer field.
            for _ in range(len(EXTENDED_FIELDS) + 1):
                resp = await client.post(_sb_url("daily_checkins"), headers=headers, params=params, json=payload)
                if resp.status_code == 400 and "PGRST204" in resp.text:
                    missing = re.search(r"'([a-z_0-9]+)' column", resp.text)
                    name = missing.group(1) if missing else None
                    if name and name in payload and name in EXTENDED_FIELDS:
                        logger.warning("daily_checkins has no %s column yet — saving without it. Run the latest SQL file.", name)
                        payload.pop(name)
                        extended_saved = False
                        continue
                    # Can't tell which one: fall back to the original fields only.
                    logger.warning("daily_checkins is missing columns — saving original fields only.")
                    extended_saved = False
                    payload = dict(base_payload)
                    continue
                break
            assert resp is not None
            resp.raise_for_status()
    except Exception as exc:
        logger.error("Check-in save failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save check-in.")

    streak = await _get_streak(user_id, body.date)

    return JSONResponse(content={
        "success": True,
        "date": body.date,
        "streak": streak,
        "extended_saved": extended_saved,
    })


@router.delete("/{date}")
async def delete_checkin(date: str, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    """Delete a single day's check-in (e.g. logged by mistake)."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.delete(
                _sb_url("daily_checkins"),
                headers={**_sb_headers(), "Prefer": "return=minimal"},
                params={"user_id": f"eq.{user_id}", "date": f"eq.{date}"},
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.error("Check-in delete failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not delete check-in.")

    return JSONResponse(content={"success": True})


@router.get("/recent")
async def get_recent_checkins(user_id: str = Depends(get_current_user_id), days: int = 30) -> JSONResponse:
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
                    "select": "*",
                    "order": "date.desc",
                },
            )
            resp.raise_for_status()
            return JSONResponse(content={"checkins": resp.json() or []})
    except Exception as exc:
        logger.error("Check-in fetch failed: %s", exc)
        return JSONResponse(content={"checkins": []})


@router.get("/today")
async def get_today_checkin(user_id: str = Depends(get_current_user_id), local_date: Optional[str] = None) -> JSONResponse:
    """Get the check-in for local_date (the device's own calendar date — today
    by default, or yesterday when editing it), if one exists."""
    # date.today() is the server's own clock, not the user's — prefer the
    # client-supplied local date; fall back to server date only for an
    # un-updated app version.
    today = local_date or date.today().isoformat()
    try:
        datetime.strptime(today, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="local_date must be YYYY-MM-DD.")
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


async def _get_streak(user_id: str, local_date: Optional[str] = None) -> int:
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
        # Prefer the client-supplied local date instead of the server clock,
        # same fix as journal.py's streak logic.
        today = datetime.strptime(local_date, "%Y-%m-%d").date() if local_date else date.today()
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


def get_checkin_dataframe(user_id: str, days: int = 180):
    """
    Fetch check-in data as a DataFrame for merging into health analysis,
    indexed by date. Columns (those with no data are simply absent/NaN, and
    a day nobody answered is NaN, never 0):

      alcohol_flag, alcohol_drinks, afternoon_caffeine, stress_score,
      high_stress_flag, energy_drinks, energy_drink_late_flag, cigarettes,
      gambling_minutes, gambling_flag, substance_flag, work_hours,
      work_late_flag, argument_flag, travel_hours, travel_flag, screen_hours,
      late_screen_flag
    """
    import numpy as np
    import pandas as pd

    since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    try:
        resp = httpx.get(
            _sb_url("daily_checkins"),
            headers=_sb_headers(),
            params={
                "user_id": f"eq.{user_id}",
                "date": f"gte.{since}",
                "select": "*",
            },
            timeout=10,
        )
        resp.raise_for_status()
        rows = resp.json() or []
        if not rows:
            return pd.DataFrame()

        raw = pd.DataFrame(rows)
        raw["date"] = pd.to_datetime(raw["date"])
        raw = raw.set_index("date").sort_index()

        def num(name):
            if name in raw.columns:
                return pd.to_numeric(raw[name], errors="coerce")
            return pd.Series(np.nan, index=raw.index)

        def text(name):
            if name in raw.columns:
                return raw[name].astype("object")
            return pd.Series(None, index=raw.index, dtype="object")

        def flag(condition, answered):
            """1.0 / 0.0 where the question was answered, NaN where it wasn't."""
            return condition.astype(float).where(answered)

        out = pd.DataFrame(index=raw.index)

        # Original fields. Alcohol is a yes/no that a drink count refines:
        # any drinks at all means yes.
        drinks = num("alcohol_drinks")
        alcohol_bool = raw["alcohol"].fillna(False).astype(bool) if "alcohol" in raw.columns else pd.Series(False, index=raw.index)
        out["alcohol_flag"] = (alcohol_bool | (drinks.fillna(0) > 0)).astype(int)
        # Older rows have no count: a "no" is a known zero, a "yes" is unknown.
        out["alcohol_drinks"] = drinks.where(drinks.notna(), np.where(alcohol_bool, np.nan, 0.0))
        out["afternoon_caffeine"] = (
            raw["afternoon_caffeine"].fillna(False).astype(int) if "afternoon_caffeine" in raw.columns else 0
        )
        stress = num("stress_score")
        out["stress_score"] = stress
        out["high_stress_flag"] = (stress >= 7).astype(int).where(stress.notna()) if stress.notna().any() else np.nan

        energy = num("energy_drinks")
        out["energy_drinks"] = energy
        out["energy_drink_late_flag"] = flag(
            (energy > 0) & text("energy_drink_time").isin(["evening", "late"]), energy.notna()
        )

        out["cigarettes"] = num("cigarettes")

        gambling = num("gambling_minutes")
        out["gambling_minutes"] = gambling
        out["gambling_flag"] = flag(gambling > 0, gambling.notna())

        substance = raw["substance_use"] if "substance_use" in raw.columns else pd.Series(np.nan, index=raw.index)
        substance_num = pd.to_numeric(substance.map(lambda v: np.nan if v is None or (isinstance(v, float) and np.isnan(v)) else float(bool(v))), errors="coerce")
        out["substance_flag"] = substance_num

        work = num("work_hours")
        out["work_hours"] = work
        out["work_late_flag"] = flag(
            (work > 0) & text("work_finish").isin(["8_10pm", "after_10pm"]), work.notna()
        )

        arguments = num("argument_count")
        out["argument_flag"] = flag(arguments > 0, arguments.notna())

        travel = num("travel_hours")
        out["travel_hours"] = travel
        out["travel_flag"] = flag(travel > 0, travel.notna())

        screen = num("screen_hours")
        out["screen_hours"] = screen
        out["late_screen_flag"] = flag((screen > 0) & text("screen_last_use").isin(["11pm_1am", "after_1am"]), screen.notna())

        # Drop columns nobody has ever answered, so the engine's
        # "missing column" skip applies instead of an all-NaN column.
        out = out.dropna(axis=1, how="all")
        return out
    except Exception as exc:
        logger.error("Check-in DataFrame fetch failed: %s", exc)
        return pd.DataFrame()

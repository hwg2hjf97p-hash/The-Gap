"""
Apple Health ingestion — the one genuinely different data path in this app.

Every other provider (Whoop, Oura, Withings, Polar) is fetched server-side
via OAuth. Apple Health has no server API at all — HealthKit only exists
on-device. So instead of fetching, the native app reads HealthKit locally
and POSTs the aggregated daily data here, where it's merged into the exact
same pipeline (check-ins, journal signals, causal engine, snapshot,
experiments) every other provider already uses.

Deliberately duplicates a small amount of the merge/engine logic from
sync/daily_sync.py's _sync_user rather than refactoring that function to
be shared — this session has already had one real regression from a
rushed shared-code edit, and this endpoint is simple enough on its own
that the duplication is a reasonable, lower-risk tradeoff.
"""

from __future__ import annotations

import logging

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from db.supabase_client import save_results
from utils.data_cleaning import clean_dataframe
from utils.snapshot import build_snapshot
from causal.engine import run_all_hypotheses, get_experiments_in_progress
from routers.checkin import get_checkin_dataframe
from routers.journal import get_journal_dataframe

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/apple-health", tags=["apple-health"])


class AppleHealthSyncRequest(BaseModel):
    user_id: str
    daily_rows: dict[str, dict[str, float]]  # {"2026-07-14": {"hrv": 45.2, "steps": 8000, ...}}


@router.post("/sync")
async def sync_apple_health(body: AppleHealthSyncRequest) -> JSONResponse:
    if not body.daily_rows:
        return JSONResponse(content={"status": "no_data", "days": 0})

    health_df = pd.DataFrame.from_dict(body.daily_rows, orient="index")
    health_df.index = pd.to_datetime(health_df.index)
    health_df = health_df.sort_index()

    # Same merge steps as the OAuth sync path (daily_sync.py's _sync_user)
    try:
        checkin_df = get_checkin_dataframe(body.user_id)
        if checkin_df is not None and not checkin_df.empty:
            checkin_df.index = pd.to_datetime(checkin_df.index)
            health_df = health_df.join(checkin_df, how="left")
    except Exception as exc:
        logger.warning("Check-in merge failed (continuing without it): %s", exc)

    try:
        journal_df = await get_journal_dataframe(body.user_id)
        if journal_df is not None and not journal_df.empty:
            journal_df.index = pd.to_datetime(journal_df.index)
            health_df = health_df.join(journal_df, how="left")
    except Exception as exc:
        logger.warning("Journal merge failed (continuing without it): %s", exc)

    try:
        df = clean_dataframe(health_df)
        insights = run_all_hypotheses(df)
        insights_dicts = [i.to_dict() for i in insights]
        snapshot = build_snapshot(df)
        experiments = get_experiments_in_progress(df)

        session_id = save_results(
            user_id=body.user_id,
            data_source="apple_health",
            data_period_days=len(df),
            insights=insights_dicts,
            snapshot=snapshot,
            experiments=experiments,
        )
        logger.info(
            "APPLE_HEALTH_SYNC_DONE user=%s days=%d insights=%d",
            body.user_id[:8], len(df), len(insights_dicts),
        )
    except Exception as exc:
        logger.error("Apple Health engine run failed: %s", exc)
        raise HTTPException(status_code=500, detail="Analysis failed. Please try again.")

    return JSONResponse(content={
        "status": "ok",
        "session_id": session_id,
        "days": len(df),
        "insights": len(insights_dicts),
    })

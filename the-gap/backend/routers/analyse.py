"""
POST /analyse — main analysis endpoint.
POST /analyse/calendar — optional Google Calendar enrichment endpoint.

Flow:
  1. Receive multipart file + data_source field
  2. Optionally receive a second calendar file
  3. Validate upload
  4. Parse into daily DataFrame
  5. Merge calendar data if provided
  6. Run causal engine (22 hypotheses)
  7. Save results to Supabase
  8. Return structured JSON response
"""

from __future__ import annotations

import logging
import time
from typing import Annotated, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from utils.validation import validate_upload
from parsers.apple_health import parse_apple_health
from parsers.whoop import parse_whoop
from parsers.oura import parse_oura
from parsers.google_calendar import parse_google_calendar, merge_calendar_into_health
from utils.data_cleaning import clean_dataframe
from causal.engine import run_all_hypotheses
from db.supabase_client import save_results
from models.insight import Insight

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/analyse")
async def analyse(
    file: Annotated[UploadFile, File(description="Apple Health .xml/.zip, Whoop .csv, or Oura .csv export")],
    data_source: Annotated[str, Form(description="'apple_health', 'whoop', or 'oura'")],
    calendar_file: Annotated[Optional[UploadFile], File(description="Optional Google Calendar .ics export")] = None,
) -> JSONResponse:
    """
    Upload health data and receive causal insights.

    Accepts:
      - Apple Health XML or ZIP export
      - Whoop CSV export
      - Oura CSV or JSON export
      - Optional: Google Calendar .ics for work/life hypotheses

    Returns JSON:
    {
      "session_id": "<uuid>",
      "share_url": "https://causalme.com/results/<uuid>",
      "data_summary": { "days": 123, "source": "apple_health", "has_calendar": false },
      "insights": [ { ... }, ... ]
    }
    """
    t0 = time.perf_counter()

    # ── 1. Read file bytes ─────────────────────────────────────────────────
    try:
        file_bytes = await file.read()
    except Exception as exc:
        logger.error("Failed to read upload: %s", exc)
        raise HTTPException(status_code=400, detail="Could not read uploaded file.")

    filename = file.filename or "upload"

    # ── 2. Validate ────────────────────────────────────────────────────────
    validation = validate_upload(
        file_bytes=file_bytes,
        filename=filename,
        data_source=data_source,
    )
    if not validation.is_valid:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": validation.error_code,
                "message": validation.message,
            },
        )

    # ── 3. Parse health data ───────────────────────────────────────────────
    try:
        if data_source == "apple_health":
            df = parse_apple_health(file_bytes)
        elif data_source == "whoop":
            df = parse_whoop(file_bytes)
        elif data_source == "oura":
            df = parse_oura(file_bytes)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported data_source: {data_source}")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Parse error for %s: %s", data_source, exc)
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "PARSE_FAILED",
                "message": (
                    "We couldn't read your health export. "
                    "Make sure you're uploading the right file format."
                ),
            },
        )

    # ── 4. Parse and merge calendar data (optional) ────────────────────────
    has_calendar = False
    if calendar_file is not None:
        try:
            cal_bytes = await calendar_file.read()
            calendar_df = parse_google_calendar(cal_bytes)
            df = merge_calendar_into_health(df, calendar_df)
            has_calendar = True
            logger.info("Calendar data merged — %d calendar days", len(calendar_df))
        except Exception as exc:
            logger.warning("Calendar parse failed (continuing without it): %s", exc)
            # Non-fatal — continue without calendar data

    # ── 5. Clean ───────────────────────────────────────────────────────────
    try:
        df = clean_dataframe(df)
    except Exception as exc:
        logger.exception("Data cleaning failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "CLEAN_FAILED",
                "message": f"Data cleaning error: {type(exc).__name__}: {exc}",
            },
        )

    data_period_days = len(df)
    logger.info("Parsed %d days from %s in %.1fs", data_period_days, data_source, time.perf_counter() - t0)

    if data_period_days < 30:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "INSUFFICIENT_DATA",
                "message": (
                    f"We need at least 30 days of data — your export has {data_period_days} days. "
                    "Try exporting a longer period."
                ),
            },
        )

    # ── 6. Causal engine ───────────────────────────────────────────────────
    try:
        insights: list[Insight] = run_all_hypotheses(df)
    except Exception as exc:
        logger.exception("Causal engine failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "ENGINE_ERROR",
                "message": "Something went wrong running your analysis. Please try again.",
            },
        )

    if not insights:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "NO_INSIGHTS",
                "message": (
                    "We couldn't find any significant patterns in your data yet. "
                    "This usually means you need more varied data — try again after 60+ days of tracking."
                ),
            },
        )

    # ── 7. Serialise insights ──────────────────────────────────────────────
    insights_dicts = [i.to_dict() for i in insights]

    # ── 8. Persist ────────────────────────────────────────────────────────
    try:
        session_id = save_results(
            data_source=data_source,
            data_period_days=data_period_days,
            insights=insights_dicts,
        )
    except Exception as exc:
        logger.error("save_results failed: %s", exc)
        from uuid import uuid4
        session_id = str(uuid4())

    share_url = f"https://causalme.com/results/{session_id}"

    elapsed = time.perf_counter() - t0
    logger.info(
        "Analysis complete — %d insights in %.1fs (session: %s)",
        len(insights_dicts),
        elapsed,
        session_id,
    )

    return JSONResponse(
        content={
            "session_id": session_id,
            "share_url": share_url,
            "data_summary": {
                "days": data_period_days,
                "source": data_source,
                "has_calendar": has_calendar,
            },
            "insights": insights_dicts,
        }
    )


@router.get("/results/{session_id}")
async def get_results(session_id: str) -> JSONResponse:
    """Retrieve previously computed results by session_id."""
    from db.supabase_client import get_results as db_get

    row = db_get(session_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "NOT_FOUND",
                "message": "Results not found. They may have expired.",
            },
        )
    return JSONResponse(content=row)

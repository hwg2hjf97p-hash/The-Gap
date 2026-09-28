"""
User-proposed experiments — lets someone pick a treatment + outcome from
metrics they already track (rather than only waiting for the engine to
surface one of the fixed HYPOTHESES) and have the exact same causal engine
test it for them.

Deliberately NOT a free-text "type any hypothesis" feature: the engine can
only test real DataFrame columns, so the picker is constrained to columns
that already appear somewhere in causal/hypotheses.py's HYPOTHESES list —
this guarantees every combination the user can pick is one the engine can
actually run, with sensible covariates inherited from a real existing
hypothesis that already uses the same outcome column.

Table DDL (run once in Supabase SQL editor):
  CREATE TABLE IF NOT EXISTS user_hypotheses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    treatment_col TEXT NOT NULL,
    outcome_col TEXT NOT NULL,
    treatment_label TEXT NOT NULL,
    outcome_label TEXT NOT NULL,
    binary_treatment BOOLEAN NOT NULL DEFAULT false,
    category TEXT NOT NULL DEFAULT 'custom',
    created_at TIMESTAMPTZ DEFAULT NOW()
  );
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth import get_current_user_id
from causal.hypotheses import HYPOTHESES, Hypothesis

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/experiments", tags=["experiments"])

DEFAULT_MIN_ROWS = 30
DEFAULT_MIN_TREATED_DAYS = 8


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


def _build_catalog() -> tuple[dict[str, tuple[str, bool]], dict[str, str]]:
    """
    Derive the pickable treatment/outcome catalogs straight from the real
    HYPOTHESES list, so a new combination this endpoint accepts is always
    one the engine has already proven it can run.
    Returns (treatment_catalog: col -> (label, is_binary), outcome_catalog: col -> label).
    """
    treatments: dict[str, tuple[str, bool]] = {}
    outcomes: dict[str, str] = {}
    for hyp in HYPOTHESES:
        if hyp.treatment_col not in treatments:
            treatments[hyp.treatment_col] = (hyp.treatment_label, hyp.binary_treatment)
        if hyp.outcome_col not in outcomes:
            outcomes[hyp.outcome_col] = hyp.outcome_label
    return treatments, outcomes


def _default_covariates(outcome_col: str, treatment_col: str) -> list[str]:
    """Reuse covariates from a real hypothesis that already tests this same
    outcome, rather than guessing a new set — same instinct as the rest of
    this engine's design (min_effect thresholds, sufficiency checks, etc.
    are all keyed by real, already-tuned examples)."""
    for hyp in HYPOTHESES:
        if hyp.outcome_col == outcome_col:
            return [c for c in hyp.covariate_cols if c != treatment_col]
    return ["day_of_week"]


@router.get("/available-metrics")
async def available_metrics():
    """Everything the picker can offer — every combination is guaranteed runnable."""
    treatments, outcomes = _build_catalog()
    return JSONResponse(content={
        "treatments": [
            {"col": col, "label": label, "binary": is_binary}
            for col, (label, is_binary) in sorted(treatments.items())
        ],
        "outcomes": [
            {"col": col, "label": label}
            for col, label in sorted(outcomes.items())
        ],
    })


class CreateExperimentRequest(BaseModel):
    treatment_col: str
    outcome_col: str


@router.post("")
async def create_experiment(body: CreateExperimentRequest, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    treatments, outcomes = _build_catalog()

    if body.treatment_col not in treatments:
        raise HTTPException(status_code=400, detail=f"'{body.treatment_col}' isn't a trackable metric.")
    if body.outcome_col not in outcomes:
        raise HTTPException(status_code=400, detail=f"'{body.outcome_col}' isn't a trackable metric.")
    if body.treatment_col == body.outcome_col:
        raise HTTPException(status_code=400, detail="Treatment and outcome can't be the same metric.")

    treatment_label, is_binary = treatments[body.treatment_col]
    outcome_label = outcomes[body.outcome_col]

    payload = {
        "user_id": user_id,
        "treatment_col": body.treatment_col,
        "outcome_col": body.outcome_col,
        "treatment_label": treatment_label,
        "outcome_label": outcome_label,
        "binary_treatment": is_binary,
        "category": "custom",
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _sb_url("user_hypotheses"),
                headers=_sb_headers(prefer="return=representation"),
                json=payload,
            )
            resp.raise_for_status()
            row = resp.json()[0]
    except Exception as exc:
        logger.error("Creating experiment failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Couldn't save that experiment — please try again.")

    return JSONResponse(content={"experiment": row})


@router.get("")
async def list_experiments(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _sb_url("user_hypotheses"),
                headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "select": "*", "order": "created_at.desc"},
            )
            resp.raise_for_status()
            return JSONResponse(content={"experiments": resp.json() or []})
    except Exception as exc:
        logger.error("Listing experiments failed for %s: %s", user_id[:8], exc)
        return JSONResponse(content={"experiments": []})


@router.delete("/{experiment_id}")
async def delete_experiment(experiment_id: str, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.delete(
                _sb_url("user_hypotheses"),
                headers={**_sb_headers(), "Prefer": "return=minimal"},
                params={"id": f"eq.{experiment_id}", "user_id": f"eq.{user_id}"},
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.error("Deleting experiment %s failed: %s", experiment_id, exc)
        raise HTTPException(status_code=500, detail="Couldn't delete that experiment — please try again.")
    return JSONResponse(content={"deleted": True})


async def get_user_hypotheses(user_id: str) -> list[Hypothesis]:
    """
    Fetch this user's custom hypotheses as real Hypothesis objects, ready to
    merge into HYPOTHESES for a sync run. Used by sync/daily_sync.py.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _sb_url("user_hypotheses"),
                headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "select": "*"},
            )
            resp.raise_for_status()
            rows = resp.json() or []
    except Exception as exc:
        logger.warning("Fetching user hypotheses failed for %s (continuing without them): %s", user_id[:8], exc)
        return []

    result = []
    for row in rows:
        covariates = _default_covariates(row["outcome_col"], row["treatment_col"])
        result.append(Hypothesis(
            id=f"custom_{row['id']}",
            treatment_col=row["treatment_col"],
            outcome_col=row["outcome_col"],
            treatment_label=row["treatment_label"],
            outcome_label=row["outcome_label"],
            covariate_cols=covariates,
            binary_treatment=row["binary_treatment"],
            min_rows=DEFAULT_MIN_ROWS,
            min_treated_days=DEFAULT_MIN_TREATED_DAYS if row["binary_treatment"] else 0,
            category=row.get("category", "custom"),
        ))
    return result

"""
Insight data model — the output of a single causal hypothesis test.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Literal


class ConfidenceLevel(str, Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"


@dataclass
class Insight:
    # ── Identity ──────────────────────────────────────────────────────────
    hypothesis_id: str
    title: str                          # short card heading
    headline: str                       # one-sentence finding
    body: str                           # 2-sentence explanation

    # ── Metric display ────────────────────────────────────────────────────
    metric_delta: str                   # e.g. "+4.2"
    metric_unit: str                    # e.g. "ms HRV"
    metric_direction: Literal["positive", "negative"]

    # ── Labels ────────────────────────────────────────────────────────────
    treatment_label: str                # e.g. "Daily Steps"
    outcome_label: str                  # e.g. "Next-Morning HRV"

    # ── Confidence ────────────────────────────────────────────────────────
    confidence: ConfidenceLevel
    confidence_label: str               # e.g. "Strong Evidence"
    confidence_description: str         # tooltip copy

    # ── Raw stats ─────────────────────────────────────────────────────────
    ate: float                          # average treatment effect
    ci_low: float
    ci_high: float
    n_observations: int
    p_value: Optional[float] = None

    # ── UX copy ───────────────────────────────────────────────────────────
    actionable_tip: str = ""
    share_text: str = ""

    # ── Raw column names ─────────────────────────────────────────────────
    # Lets the client map a finding back to a chartable metric (see
    # utils/snapshot.py's METRIC_DISPLAY / metric_history table) without
    # hardcoding a duplicate copy of every hypothesis's outcome mapping.
    treatment_col: str = ""
    outcome_col: str = ""

    # Sensitive findings (see PRIVATE_HYPOTHESIS_IDS in causal/hypotheses.py):
    # the app keeps these off lock-screen pushes, share cards and the PDF
    # report. Still shown to the user inside the app.
    is_private: bool = False

    # For findings about an amount (steps, screen time, calendar events): what
    # the effect comes to between this person's lighter days and heavier days,
    # in plain words (see causal/engine.py). Empty for yes/no findings.
    contrast_text: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        # Convert ConfidenceLevel enum to string for JSON serialisation
        d["confidence"] = self.confidence.value
        return d


# ── Pydantic response models (for FastAPI docs / OpenAPI) ─────────────────

from pydantic import BaseModel
from typing import List


class InsightOut(BaseModel):
    contrast_text: str = ""
    hypothesis_id: str
    title: str
    headline: str
    body: str
    metric_delta: str
    metric_unit: str
    metric_direction: Literal["positive", "negative"]
    treatment_label: str
    outcome_label: str
    confidence: str
    confidence_label: str
    confidence_description: str
    ate: float
    ci_low: float
    ci_high: float
    n_observations: int
    p_value: Optional[float] = None
    actionable_tip: str = ""
    share_text: str = ""
    treatment_col: str = ""
    outcome_col: str = ""


class DataSummaryOut(BaseModel):
    source: str
    days: int


class AnalysisResponse(BaseModel):
    session_id: str
    share_url: str
    data_summary: DataSummaryOut
    insights: List[InsightOut]


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    support: str = "hello@causalme.com"

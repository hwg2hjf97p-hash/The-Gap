"""
The 7 causal hypotheses for The Gap MVP.
Each Hypothesis defines treatment, outcome, covariates, and minimum data requirements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Hypothesis:
    id: str
    treatment_col: str
    outcome_col: str
    treatment_label: str
    outcome_label: str
    min_rows: int = 30
    covariate_cols: list[str] = field(default_factory=list)
    binary_treatment: bool = False
    min_treated_days: int = 0       # only checked when binary_treatment=True


HYPOTHESES: list[Hypothesis] = [

    # 1. Daily steps → Next-day HRV
    Hypothesis(
        id="steps_hrv",
        treatment_col="steps",
        outcome_col="hrv_next",
        covariate_cols=["hrv_lag1", "sleep_total_min", "resting_hr", "day_of_week"],
        min_rows=30,
        treatment_label="Daily steps (per 2,000)",
        outcome_label="Next-day HRV (ms)",
    ),

    # 2. Sleep timing consistency → Deep sleep
    Hypothesis(
        id="sleep_consistency_deep",
        treatment_col="sleep_deviation",
        outcome_col="sleep_deep_min",
        covariate_cols=["sleep_total_min", "day_of_week", "is_weekend", "hrv_lag1"],
        min_rows=45,
        treatment_label="Bedtime deviation (min from your norm)",
        outcome_label="Deep sleep (minutes)",
    ),

    # 3. Sleep duration → Next-day resting heart rate
    Hypothesis(
        id="sleep_duration_rhr",
        treatment_col="sleep_total_min",
        outcome_col="resting_hr_next",
        covariate_cols=["resting_hr", "day_of_week", "hrv_lag1"],
        min_rows=30,
        treatment_label="Total sleep (hours)",
        outcome_label="Next-day resting heart rate (bpm)",
    ),

    # 4. Mindfulness minutes → Next-day HRV
    Hypothesis(
        id="mindfulness_hrv",
        treatment_col="mindful_minutes",
        outcome_col="hrv_next",
        covariate_cols=["hrv_lag1", "sleep_total_min", "steps", "day_of_week"],
        min_rows=30,
        binary_treatment=False,
        min_treated_days=15,
        treatment_label="Mindfulness minutes",
        outcome_label="Next-day HRV (ms)",
    ),

    # 5. Alcohol flag → Next-day HRV  (binary treatment)
    Hypothesis(
        id="alcohol_hrv",
        treatment_col="alcohol_flag",
        outcome_col="hrv_next",
        covariate_cols=["hrv_lag1", "sleep_total_min", "day_of_week", "is_weekend"],
        min_rows=30,
        binary_treatment=True,
        min_treated_days=10,
        treatment_label="Alcohol (yes/no)",
        outcome_label="Next-day HRV (ms)",
    ),

    # 6. Active calories → Total sleep
    Hypothesis(
        id="active_energy_sleep",
        treatment_col="active_energy",
        outcome_col="sleep_total_min",
        covariate_cols=["sleep_lag1", "day_of_week", "resting_hr"],
        min_rows=30,
        treatment_label="Active calories burned",
        outcome_label="Total sleep (minutes)",
    ),

    # 7. Morning HRV → Same-night deep sleep
    Hypothesis(
        id="hrv_sleep_quality",
        treatment_col="hrv",
        outcome_col="sleep_deep_min",
        covariate_cols=["sleep_lag1", "steps", "day_of_week", "resting_hr"],
        min_rows=30,
        treatment_label="Morning HRV (ms)",
        outcome_label="That night's deep sleep (minutes)",
    ),
]

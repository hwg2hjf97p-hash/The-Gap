"""
The Gap — 22 causal hypotheses across health, lifestyle, and work/life patterns.
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
    category: str = "health"        # health | work | lifestyle | recovery


HYPOTHESES: list[Hypothesis] = [

    # ── RECOVERY & HRV ──────────────────────────────────────────────────────

    # 1. Daily steps → Next-day HRV
    Hypothesis(
        id="steps_hrv",
        treatment_col="steps",
        outcome_col="hrv_next",
        covariate_cols=["hrv_lag1", "sleep_total_min", "resting_hr", "day_of_week"],
        min_rows=30,
        treatment_label="Daily steps (per 2,000)",
        outcome_label="Next-day HRV (ms)",
        category="health",
    ),

    # 2. Alcohol flag → Next-day HRV  (binary treatment)
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
        category="lifestyle",
    ),

    # 3. Mindfulness minutes → Next-day HRV
    Hypothesis(
        id="mindfulness_hrv",
        treatment_col="mindful_minutes",
        outcome_col="hrv_next",
        covariate_cols=["hrv_lag1", "sleep_total_min", "steps", "day_of_week"],
        min_rows=30,
        treatment_label="Mindfulness minutes",
        outcome_label="Next-day HRV (ms)",
        category="lifestyle",
    ),

    # 4. Morning HRV → Same-night deep sleep
    Hypothesis(
        id="hrv_sleep_quality",
        treatment_col="hrv",
        outcome_col="sleep_deep_min",
        covariate_cols=["sleep_lag1", "steps", "day_of_week", "resting_hr"],
        min_rows=30,
        treatment_label="Morning HRV (ms)",
        outcome_label="That night's deep sleep (minutes)",
        category="recovery",
    ),

    # ── SLEEP ───────────────────────────────────────────────────────────────

    # 5. Sleep timing consistency → Deep sleep
    Hypothesis(
        id="sleep_consistency_deep",
        treatment_col="sleep_deviation",
        outcome_col="sleep_deep_min",
        covariate_cols=["sleep_total_min", "day_of_week", "is_weekend", "hrv_lag1"],
        min_rows=45,
        treatment_label="Bedtime deviation (min from your norm)",
        outcome_label="Deep sleep (minutes)",
        category="health",
    ),

    # 6. Sleep duration → Next-day resting heart rate
    Hypothesis(
        id="sleep_duration_rhr",
        treatment_col="sleep_total_min",
        outcome_col="resting_hr_next",
        covariate_cols=["resting_hr", "day_of_week", "hrv_lag1"],
        min_rows=30,
        treatment_label="Total sleep (hours)",
        outcome_label="Next-day resting heart rate (bpm)",
        category="health",
    ),

    # 7. Active calories → Total sleep
    Hypothesis(
        id="active_energy_sleep",
        treatment_col="active_energy",
        outcome_col="sleep_total_min",
        covariate_cols=["sleep_lag1", "day_of_week", "resting_hr"],
        min_rows=30,
        treatment_label="Active calories burned",
        outcome_label="Total sleep (minutes)",
        category="health",
    ),

    # 8. Weekend flag → Sleep quality (binary)
    Hypothesis(
        id="weekend_sleep",
        treatment_col="is_weekend",
        outcome_col="sleep_deep_min",
        covariate_cols=["sleep_total_min", "hrv_lag1", "alcohol_flag"],
        min_rows=30,
        binary_treatment=True,
        min_treated_days=8,
        treatment_label="Weekend (yes/no)",
        outcome_label="Deep sleep (minutes)",
        category="lifestyle",
    ),

    # 9. Sleep debt → Next-day resting HR
    Hypothesis(
        id="sleep_debt_rhr",
        treatment_col="sleep_debt_min",
        outcome_col="resting_hr_next",
        covariate_cols=["resting_hr", "steps", "day_of_week"],
        min_rows=30,
        treatment_label="Accumulated sleep debt (min)",
        outcome_label="Next-day resting heart rate (bpm)",
        category="recovery",
    ),

    # ── WORK / CALENDAR ─────────────────────────────────────────────────────

    # 10. Meeting load → Next-day HRV
    Hypothesis(
        id="meeting_load_hrv",
        treatment_col="meeting_hours",
        outcome_col="hrv_next",
        covariate_cols=["hrv_lag1", "sleep_total_min", "day_of_week", "is_weekend"],
        min_rows=30,
        treatment_label="Hours in meetings",
        outcome_label="Next-day HRV (ms)",
        category="work",
    ),

    # 11. Late meetings (after 6 pm) → Sleep quality (binary)
    Hypothesis(
        id="late_meetings_sleep",
        treatment_col="has_late_meeting",
        outcome_col="sleep_deep_min",
        covariate_cols=["sleep_lag1", "sleep_total_min", "day_of_week"],
        min_rows=30,
        binary_treatment=True,
        min_treated_days=8,
        treatment_label="Late meeting after 6 pm (yes/no)",
        outcome_label="Deep sleep (minutes)",
        category="work",
    ),

    # 12. Busy work day → Next-day resting HR
    Hypothesis(
        id="busy_day_rhr",
        treatment_col="meeting_hours",
        outcome_col="resting_hr_next",
        covariate_cols=["resting_hr", "sleep_total_min", "day_of_week"],
        min_rows=30,
        treatment_label="Hours in meetings",
        outcome_label="Next-day resting heart rate (bpm)",
        category="work",
    ),

    # 13. Meeting-free days → HRV
    Hypothesis(
        id="meeting_free_hrv",
        treatment_col="is_meeting_free",
        outcome_col="hrv_next",
        covariate_cols=["hrv_lag1", "sleep_total_min", "day_of_week"],
        min_rows=30,
        binary_treatment=True,
        min_treated_days=8,
        treatment_label="Meeting-free day (yes/no)",
        outcome_label="Next-day HRV (ms)",
        category="work",
    ),

    # 14. Calendar event density → Sleep duration
    Hypothesis(
        id="event_density_sleep",
        treatment_col="calendar_events",
        outcome_col="sleep_total_min",
        covariate_cols=["sleep_lag1", "day_of_week", "is_weekend"],
        min_rows=30,
        treatment_label="Calendar events per day",
        outcome_label="Total sleep (minutes)",
        category="work",
    ),

    # ── LIFESTYLE ───────────────────────────────────────────────────────────

    # 15. Caffeine timing (afternoon flag) → Sleep quality (binary)
    Hypothesis(
        id="caffeine_sleep",
        treatment_col="afternoon_caffeine",
        outcome_col="sleep_deep_min",
        covariate_cols=["sleep_lag1", "sleep_total_min", "day_of_week"],
        min_rows=30,
        binary_treatment=True,
        min_treated_days=8,
        treatment_label="Afternoon caffeine after 2 pm (yes/no)",
        outcome_label="Deep sleep (minutes)",
        category="lifestyle",
    ),

    # 16. Alcohol → Next-day resting HR (binary)
    Hypothesis(
        id="alcohol_rhr",
        treatment_col="alcohol_flag",
        outcome_col="resting_hr_next",
        covariate_cols=["resting_hr", "sleep_total_min", "day_of_week"],
        min_rows=30,
        binary_treatment=True,
        min_treated_days=10,
        treatment_label="Alcohol (yes/no)",
        outcome_label="Next-day resting heart rate (bpm)",
        category="lifestyle",
    ),

    # 17. Stress score → Next-day HRV
    Hypothesis(
        id="stress_hrv",
        treatment_col="stress_score",
        outcome_col="hrv_next",
        covariate_cols=["hrv_lag1", "sleep_total_min", "steps", "day_of_week"],
        min_rows=30,
        treatment_label="Daily stress score (0–10)",
        outcome_label="Next-day HRV (ms)",
        category="lifestyle",
    ),

    # 18. High stress day → Sleep duration (binary)
    Hypothesis(
        id="high_stress_sleep",
        treatment_col="high_stress_flag",
        outcome_col="sleep_total_min",
        covariate_cols=["sleep_lag1", "day_of_week", "is_weekend"],
        min_rows=30,
        binary_treatment=True,
        min_treated_days=8,
        treatment_label="High stress day (yes/no)",
        outcome_label="Total sleep (minutes)",
        category="lifestyle",
    ),

    # ── ACTIVITY & FITNESS ──────────────────────────────────────────────────

    # 19. Steps → Next-day resting HR
    Hypothesis(
        id="steps_rhr",
        treatment_col="steps",
        outcome_col="resting_hr_next",
        covariate_cols=["resting_hr", "hrv_lag1", "sleep_total_min", "day_of_week"],
        min_rows=30,
        treatment_label="Daily steps (per 2,000)",
        outcome_label="Next-day resting heart rate (bpm)",
        category="health",
    ),

    # 20. Active calories → Next-day HRV
    Hypothesis(
        id="active_energy_hrv",
        treatment_col="active_energy",
        outcome_col="hrv_next",
        covariate_cols=["hrv_lag1", "sleep_total_min", "resting_hr", "day_of_week"],
        min_rows=30,
        treatment_label="Active calories burned",
        outcome_label="Next-day HRV (ms)",
        category="health",
    ),

    # 21. VO2 max trend → Resting HR
    Hypothesis(
        id="vo2max_rhr",
        treatment_col="vo2max",
        outcome_col="resting_hr",
        covariate_cols=["steps", "sleep_total_min", "day_of_week"],
        min_rows=30,
        treatment_label="VO2 max (estimated)",
        outcome_label="Resting heart rate (bpm)",
        category="health",
    ),

    # 22. Recovery score → Next-day steps (Whoop-specific)
    Hypothesis(
        id="recovery_activity",
        treatment_col="recovery_score",
        outcome_col="steps",
        covariate_cols=["hrv_lag1", "sleep_total_min", "day_of_week"],
        min_rows=30,
        treatment_label="Daily recovery score (%)",
        outcome_label="Steps taken that day",
        category="recovery",
    ),

    # 22b. Sleep performance (% of sleep need met) → Same-day recovery score.
    # sleep_score is real data (Whoop's sleep_performance_percentage, Oura's
    # sleep score, or Polar's sleep_score) — populated the whole time, just
    # never tested against anything. Distinct from sleep_total_min: this
    # measures how much of the calculated sleep *need* was met, not raw
    # duration, so it can genuinely differ from the sleep-duration hypotheses
    # above even on the same night. Same-day (not next-day) is the correct
    # pairing here — Whoop calculates each morning's recovery score directly
    # from that same night's sleep, so they already describe the same period.
    Hypothesis(
        id="sleep_performance_recovery",
        treatment_col="sleep_score",
        outcome_col="recovery_score",
        covariate_cols=["hrv_lag1", "sleep_total_min", "day_of_week"],
        min_rows=30,
        treatment_label="Sleep performance (% of sleep need met)",
        outcome_label="Same-day recovery score (%)",
        category="recovery",
    ),

    # ── STRAVA / TRAINING ────────────────────────────────────────────────────

    # 23. Training load → Next-day HRV
    Hypothesis(
        id="training_load_hrv",
        treatment_col="training_load",
        outcome_col="hrv_next",
        covariate_cols=["hrv_lag1", "sleep_total_min", "day_of_week", "is_weekend"],
        min_rows=30,
        treatment_label="Daily training load",
        outcome_label="Next-day HRV (ms)",
        category="health",
    ),

    # 24. Hard training day → Next-day HRV (binary)
    Hypothesis(
        id="hard_day_hrv",
        treatment_col="is_hard_day",
        outcome_col="hrv_next",
        covariate_cols=["hrv_lag1", "sleep_total_min", "day_of_week"],
        min_rows=30,
        binary_treatment=True,
        min_treated_days=8,
        treatment_label="Hard training day (yes/no)",
        outcome_label="Next-day HRV (ms)",
        category="health",
    ),

    # 25. Training load → Sleep duration
    Hypothesis(
        id="training_load_sleep",
        treatment_col="training_load",
        outcome_col="sleep_total_min",
        covariate_cols=["sleep_lag1", "day_of_week", "is_weekend"],
        min_rows=30,
        treatment_label="Daily training load",
        outcome_label="Total sleep (minutes)",
        category="health",
    ),

    # 26. 7-day training load → Resting HR
    Hypothesis(
        id="weekly_load_rhr",
        treatment_col="training_load_7d",
        outcome_col="resting_hr",
        covariate_cols=["sleep_total_min", "hrv_lag1", "day_of_week"],
        min_rows=30,
        treatment_label="7-day cumulative training load",
        outcome_label="Resting heart rate (bpm)",
        category="health",
    ),

    # ── MANUAL CHECK-IN ───────────────────────────────────────────────────

    # 27. Daily stress score → Next-day HRV (already exists as stress_hrv)
    # 28. Afternoon caffeine → Deep sleep (already exists as caffeine_sleep)
    # 29. Alcohol flag → HRV (already exists as alcohol_hrv)
    # These reuse existing hypotheses when check-in data is merged in

    # ── QUICK ENTRY (JOURNAL) ────────────────────────────────────────────
    # Derived from short, informal notes via LLM extraction — see
    # utils/journal_extract.py. min_treated_days set lower than the
    # check-in hypotheses (10) since this is a newer, lower-volume input
    # channel; worth revisiting upward once entries are more common.

    # 30. Stress-event day → Next-day HRV
    Hypothesis(
        id="journal_stress_hrv",
        treatment_col="stress_event",
        outcome_col="hrv_next",
        covariate_cols=["hrv_lag1", "sleep_total_min", "day_of_week"],
        min_rows=30,
        binary_treatment=True,
        min_treated_days=5,
        treatment_label="Day with a journaled stress event",
        outcome_label="Next-day HRV (ms)",
        category="lifestyle",
    ),

    # 31. Conflict-event day → Same-night sleep duration
    Hypothesis(
        id="journal_conflict_sleep",
        treatment_col="conflict_event",
        outcome_col="sleep_total_min",
        covariate_cols=["hrv_lag1", "day_of_week", "is_weekend"],
        min_rows=30,
        binary_treatment=True,
        min_treated_days=5,
        treatment_label="Day with a journaled conflict/argument",
        outcome_label="Sleep duration that night (min)",
        category="lifestyle",
    ),

    # These four were already being extracted from every journal entry by
    # utils/journal_extract.py the whole time, but never wired into a
    # hypothesis — so they were computed daily and then silently unused.

    # 32. Mood score → Next-day HRV (continuous treatment, not binary)
    Hypothesis(
        id="journal_mood_hrv",
        treatment_col="mood_score",
        outcome_col="hrv_next",
        covariate_cols=["hrv_lag1", "sleep_total_min", "day_of_week"],
        min_rows=30,
        treatment_label="Day's mood score (-1 bad to +1 good)",
        outcome_label="Next-day HRV (ms)",
        category="lifestyle",
    ),

    # 33. Travel/disrupted-routine day → Same-night sleep duration
    Hypothesis(
        id="journal_travel_sleep",
        treatment_col="travel_event",
        outcome_col="sleep_total_min",
        covariate_cols=["hrv_lag1", "day_of_week", "is_weekend"],
        min_rows=30,
        binary_treatment=True,
        min_treated_days=5,
        treatment_label="Day with travel or a disrupted routine",
        outcome_label="Sleep duration that night (min)",
        category="lifestyle",
    ),

    # 34. Illness day → Next-day resting heart rate
    Hypothesis(
        id="journal_illness_rhr",
        treatment_col="illness_event",
        outcome_col="resting_hr_next",
        covariate_cols=["resting_hr", "hrv_lag1", "day_of_week"],
        min_rows=30,
        binary_treatment=True,
        min_treated_days=5,
        treatment_label="Day with a journaled illness/feeling unwell",
        outcome_label="Next-day resting heart rate (bpm)",
        category="health",
    ),

    # 35. Big-win day → Next-day HRV
    Hypothesis(
        id="journal_bigwin_hrv",
        treatment_col="big_win_event",
        outcome_col="hrv_next",
        covariate_cols=["hrv_lag1", "sleep_total_min", "day_of_week"],
        min_rows=30,
        binary_treatment=True,
        min_treated_days=5,
        treatment_label="Day with a journaled win/good news",
        outcome_label="Next-day HRV (ms)",
        category="lifestyle",
    ),

    # ── ENVIRONMENT (weather & commute) ─────────────────────────────────────

    # 32. Rainy day → Daily steps
    Hypothesis(
        id="rain_steps",
        treatment_col="is_rainy",
        outcome_col="steps",
        covariate_cols=["day_of_week", "is_weekend"],
        min_rows=30,
        binary_treatment=True,
        min_treated_days=5,
        treatment_label="Rainy day (>1mm rainfall)",
        outcome_label="Daily steps",
        category="environment",
    ),

    # 33. Average temperature → Sleep duration
    Hypothesis(
        id="temp_sleep",
        treatment_col="temp_c",
        outcome_col="sleep_total_min",
        covariate_cols=["day_of_week", "is_weekend"],
        min_rows=30,
        treatment_label="Average temperature (°C)",
        outcome_label="Sleep duration (min)",
        category="environment",
    ),

    # 34. Commute time → Next-day HRV
    Hypothesis(
        id="commute_hrv",
        treatment_col="commute_minutes",
        outcome_col="hrv_next",
        covariate_cols=["hrv_lag1", "day_of_week"],
        min_rows=30,
        treatment_label="Commute time (minutes, with traffic)",
        outcome_label="Next-day HRV (ms)",
        category="environment",
    ),
]

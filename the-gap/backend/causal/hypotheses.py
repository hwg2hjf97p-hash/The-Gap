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
    # REAL BUG FIXED HERE: LinearDML returns the effect of a ONE-raw-unit
    # change in the treatment. For treatments measured in tiny units
    # (single steps, single kcal, single minutes) that effect is
    # microscopic — e.g. ~0.0004 ms of HRV per step — so engine.py's
    # "trivially small effect" noise floor (0.8 ms for hrv_next) discarded
    # these hypotheses every time, no matter how real the relationship, and
    # headlines promising "each extra 2,000 steps" were never reachable.
    # treatment_scale re-expresses the effect per this many raw units
    # (2000 for steps, 100 for kcal, ...) before the noise-floor check and
    # the headline. Binary treatments leave this at 1.0.
    treatment_scale: float = 1.0


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
        treatment_scale=2000.0,
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
        treatment_label="Mindfulness (per 10 minutes)",
        outcome_label="Next-day HRV (ms)",
        category="lifestyle",
        treatment_scale=10.0,
    ),

    # 4. Morning HRV → Same-night deep sleep
    Hypothesis(
        id="hrv_sleep_quality",
        treatment_col="hrv",
        outcome_col="sleep_deep_min",
        covariate_cols=["sleep_lag1", "steps", "day_of_week", "resting_hr"],
        min_rows=30,
        treatment_label="Morning HRV (per 10 ms)",
        outcome_label="That night's deep sleep (minutes)",
        category="recovery",
        treatment_scale=10.0,
    ),

    # ── SLEEP ───────────────────────────────────────────────────────────────

    # 5. Sleep duration consistency → Deep sleep
    # REAL BUG FIXED HERE: this hypothesis was labeled "Bedtime deviation"
    # but sleep_deviation (utils/data_cleaning.py) is actually a *duration*
    # consistency proxy (abs distance from your average total sleep time),
    # not a bedtime-timing signal — the label overclaimed what was
    # actually measured. Also removed sleep_total_min from covariates: since
    # sleep_deviation is mechanically derived FROM sleep_total_min, controlling
    # for it here is a "bad control" that partials out much of the very
    # variation this hypothesis is trying to test.
    Hypothesis(
        id="sleep_consistency_deep",
        treatment_col="sleep_deviation",
        outcome_col="sleep_deep_min",
        covariate_cols=["day_of_week", "is_weekend", "hrv_lag1"],
        min_rows=45,
        treatment_label="Sleep duration deviation (per 30 min from your norm)",
        outcome_label="Deep sleep (minutes)",
        category="health",
        treatment_scale=30.0,
    ),

    # 6. Sleep duration → Next-day resting heart rate
    Hypothesis(
        id="sleep_duration_rhr",
        treatment_col="sleep_total_min",
        outcome_col="resting_hr_next",
        covariate_cols=["resting_hr", "day_of_week", "hrv_lag1"],
        min_rows=30,
        treatment_label="Total sleep (per hour)",
        outcome_label="Next-day resting heart rate (bpm)",
        category="health",
        treatment_scale=60.0,
    ),

    # 7. Active calories → Total sleep
    Hypothesis(
        id="active_energy_sleep",
        treatment_col="active_energy",
        outcome_col="sleep_total_min",
        covariate_cols=["sleep_lag1", "day_of_week", "resting_hr"],
        min_rows=30,
        treatment_label="Active calories burned (per 100)",
        outcome_label="Total sleep (minutes)",
        category="health",
        treatment_scale=100.0,
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
        treatment_label="Accumulated sleep debt (per hour)",
        outcome_label="Next-day resting heart rate (bpm)",
        category="recovery",
        treatment_scale=60.0,
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
        treatment_scale=2000.0,
    ),

    # 20. Active calories → Next-day HRV
    Hypothesis(
        id="active_energy_hrv",
        treatment_col="active_energy",
        outcome_col="hrv_next",
        covariate_cols=["hrv_lag1", "sleep_total_min", "resting_hr", "day_of_week"],
        min_rows=30,
        treatment_label="Active calories burned (per 100)",
        outcome_label="Next-day HRV (ms)",
        category="health",
        treatment_scale=100.0,
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
        treatment_label="Daily recovery score (per 10%)",
        outcome_label="Steps taken that day",
        category="recovery",
        treatment_scale=10.0,
    ),

    # 22b. REMOVED: sleep_score → recovery_score ("sleep performance vs
    # same-day recovery score") used to be here. Pulled after a reliability
    # audit found it's not a real causal test at all — Whoop's own
    # documented recovery-score formula computes recovery_score *directly
    # from* HRV, resting HR, and sleep performance, i.e. sleep_score is a
    # mechanical input to the outcome, not an independent cause of it. Any
    # "effect" this ever found would be definitional/formulaic, not
    # causal — exactly the kind of finding that would quietly undermine
    # trust in every other genuinely-tested hypothesis in this list.

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
        treatment_label="Commute time (per 10 minutes, with traffic)",
        outcome_label="Next-day HRV (ms)",
        category="environment",
        treatment_scale=10.0,
    ),

    # ── WORKOUTS (planned/logged in-app, see routers/workouts.py) ───────────
    # workout_completed_flag is 1 on any day with a workout marked done —
    # distinct from a wearable's own auto-detected exercise, since this
    # specifically captures intent-to-outcome: did the workout someone
    # said they'd do actually happen.

    # 35. Workout completed → Next-day HRV
    Hypothesis(
        id="workout_hrv",
        treatment_col="workout_completed_flag",
        outcome_col="hrv_next",
        covariate_cols=["hrv_lag1", "sleep_total_min", "day_of_week"],
        min_rows=30,
        binary_treatment=True,
        min_treated_days=8,
        treatment_label="Workout completed (yes/no)",
        outcome_label="Next-day HRV (ms)",
        category="lifestyle",
    ),

    # 36. Workout completed → Next-day resting heart rate
    Hypothesis(
        id="workout_rhr",
        treatment_col="workout_completed_flag",
        outcome_col="resting_hr_next",
        covariate_cols=["sleep_total_min", "day_of_week"],
        min_rows=30,
        binary_treatment=True,
        min_treated_days=8,
        treatment_label="Workout completed (yes/no)",
        outcome_label="Next-day resting heart rate (bpm)",
        category="lifestyle",
    ),

    # 37. Workout completed → Same-night sleep duration
    Hypothesis(
        id="workout_sleep",
        treatment_col="workout_completed_flag",
        outcome_col="sleep_total_min",
        covariate_cols=["day_of_week", "is_weekend"],
        min_rows=30,
        binary_treatment=True,
        min_treated_days=8,
        treatment_label="Workout completed (yes/no)",
        outcome_label="Sleep duration that night (min)",
        category="lifestyle",
    ),

    # 41. Workout volume → Next-day HRV. Only workout days carry a value
    # (see get_workout_dataframe), so this compares heavier and lighter
    # sessions against each other rather than against rest days.
    Hypothesis(
        id="workout_volume_hrv",
        treatment_col="workout_volume_kg",
        outcome_col="hrv_next",
        covariate_cols=["hrv_lag1", "sleep_total_min", "day_of_week"],
        min_rows=24,
        treatment_label="Workout volume (per 1,000 kg lifted)",
        outcome_label="Next-day HRV (ms)",
        category="lifestyle",
        treatment_scale=1000.0,
    ),

    # 42. Leg day vs other workouts → Next-day HRV
    Hypothesis(
        id="leg_day_hrv",
        treatment_col="leg_day_flag",
        outcome_col="hrv_next",
        covariate_cols=["hrv_lag1", "sleep_total_min", "day_of_week"],
        min_rows=24,
        binary_treatment=True,
        min_treated_days=6,
        treatment_label="Leg day (yes/no)",
        outcome_label="Next-day HRV (ms)",
        category="lifestyle",
    ),

    # ── NUTRITION (logged in-app, see routers/nutrition.py) ─────────────────
    # Only days that look fully logged feed these columns (see
    # get_nutrition_dataframe), so a day where someone logged just a coffee
    # isn't read as "ate almost nothing".

    # 38. Water intake → Next-day HRV
    Hypothesis(
        id="water_hrv",
        treatment_col="water_ml",
        outcome_col="hrv_next",
        covariate_cols=["hrv_lag1", "sleep_total_min", "day_of_week"],
        min_rows=30,
        treatment_label="Water intake (per 500 ml)",
        outcome_label="Next-day HRV (ms)",
        category="lifestyle",
        treatment_scale=500.0,
    ),

    # 39. Protein intake → Next-day HRV (total calories held fixed, so this
    # is about protein specifically rather than eating more in general)
    Hypothesis(
        id="protein_hrv",
        treatment_col="protein_g",
        outcome_col="hrv_next",
        covariate_cols=["hrv_lag1", "sleep_total_min", "dietary_energy", "day_of_week"],
        min_rows=30,
        treatment_label="Protein intake (per 25 g)",
        outcome_label="Next-day HRV (ms)",
        category="lifestyle",
        treatment_scale=25.0,
    ),

    # 40. Time of last meal → Deep sleep that night
    Hypothesis(
        id="late_meal_deep_sleep",
        treatment_col="last_meal_hour",
        outcome_col="sleep_deep_min",
        covariate_cols=["day_of_week", "is_weekend"],
        min_rows=30,
        treatment_label="Time of last meal (per hour later)",
        outcome_label="Deep sleep that night (minutes)",
        category="lifestyle",
    ),
    # ── CHECK-IN CATEGORIES (alcohol amount, energy drinks, cigarettes,
    # gambling, other substances, work, travel). Every treatment here is an
    # explicit check-in answer, so a day nobody answered is NaN (skipped),
    # never counted as a zero.

    # 41. Number of alcoholic drinks → Next-day HRV (dose, not just yes/no)
    Hypothesis(
        id="alcohol_drinks_hrv",
        treatment_col="alcohol_drinks",
        outcome_col="hrv_next",
        covariate_cols=["hrv_lag1", "sleep_total_min", "day_of_week", "is_weekend"],
        min_rows=30,
        treatment_label="Alcoholic drinks (per drink)",
        outcome_label="Next-day HRV (ms)",
        category="lifestyle",
    ),

    # 42. Energy drinks → Sleep that night
    Hypothesis(
        id="energy_drinks_sleep",
        treatment_col="energy_drinks",
        outcome_col="sleep_total_min",
        covariate_cols=["sleep_lag1", "day_of_week", "is_weekend"],
        min_rows=30,
        treatment_label="Energy drinks (per drink)",
        outcome_label="Sleep duration that night (min)",
        category="lifestyle",
    ),

    # 43. Energy drink in the evening/late → Deep sleep that night
    Hypothesis(
        id="late_energy_drink_deep_sleep",
        treatment_col="energy_drink_late_flag",
        outcome_col="sleep_deep_min",
        covariate_cols=["sleep_lag1", "sleep_total_min", "day_of_week"],
        min_rows=30,
        binary_treatment=True,
        min_treated_days=8,
        treatment_label="Energy drink in the evening or later (yes/no)",
        outcome_label="Deep sleep that night (minutes)",
        category="lifestyle",
    ),

    # 44-45. Cigarettes → Next-day HRV / resting heart rate
    Hypothesis(
        id="cigarettes_hrv",
        treatment_col="cigarettes",
        outcome_col="hrv_next",
        covariate_cols=["hrv_lag1", "sleep_total_min", "day_of_week"],
        min_rows=30,
        treatment_label="Cigarettes (per 5)",
        outcome_label="Next-day HRV (ms)",
        category="health",
        treatment_scale=5.0,
    ),
    Hypothesis(
        id="cigarettes_rhr",
        treatment_col="cigarettes",
        outcome_col="resting_hr_next",
        covariate_cols=["resting_hr", "sleep_total_min", "day_of_week"],
        min_rows=30,
        treatment_label="Cigarettes (per 5)",
        outcome_label="Next-day resting heart rate (bpm)",
        category="health",
        treatment_scale=5.0,
    ),

    # 46-47. Gambling day → Sleep that night / Next-day HRV (private)
    Hypothesis(
        id="gambling_sleep",
        treatment_col="gambling_flag",
        outcome_col="sleep_total_min",
        covariate_cols=["sleep_lag1", "day_of_week", "is_weekend"],
        min_rows=30,
        binary_treatment=True,
        min_treated_days=6,
        treatment_label="Day you gambled (yes/no)",
        outcome_label="Sleep duration that night (min)",
        category="lifestyle",
    ),
    Hypothesis(
        id="gambling_hrv",
        treatment_col="gambling_flag",
        outcome_col="hrv_next",
        covariate_cols=["hrv_lag1", "sleep_total_min", "day_of_week"],
        min_rows=30,
        binary_treatment=True,
        min_treated_days=6,
        treatment_label="Day you gambled (yes/no)",
        outcome_label="Next-day HRV (ms)",
        category="lifestyle",
    ),

    # 48-49. Other substances → Next-day HRV / Deep sleep (private)
    Hypothesis(
        id="substance_hrv",
        treatment_col="substance_flag",
        outcome_col="hrv_next",
        covariate_cols=["hrv_lag1", "sleep_total_min", "day_of_week"],
        min_rows=30,
        binary_treatment=True,
        min_treated_days=6,
        treatment_label="Day you used other substances (yes/no)",
        outcome_label="Next-day HRV (ms)",
        category="lifestyle",
    ),
    Hypothesis(
        id="substance_deep_sleep",
        treatment_col="substance_flag",
        outcome_col="sleep_deep_min",
        covariate_cols=["sleep_lag1", "sleep_total_min", "day_of_week"],
        min_rows=30,
        binary_treatment=True,
        min_treated_days=6,
        treatment_label="Day you used other substances (yes/no)",
        outcome_label="Deep sleep that night (minutes)",
        category="lifestyle",
    ),

    # 50-52. Work → HRV / Sleep
    Hypothesis(
        id="work_hours_hrv",
        treatment_col="work_hours",
        outcome_col="hrv_next",
        covariate_cols=["hrv_lag1", "sleep_total_min", "day_of_week", "is_weekend"],
        min_rows=30,
        treatment_label="Hours worked (per hour)",
        outcome_label="Next-day HRV (ms)",
        category="work",
    ),
    Hypothesis(
        id="work_hours_sleep",
        treatment_col="work_hours",
        outcome_col="sleep_total_min",
        covariate_cols=["sleep_lag1", "day_of_week", "is_weekend"],
        min_rows=30,
        treatment_label="Hours worked (per hour)",
        outcome_label="Sleep duration that night (min)",
        category="work",
    ),
    Hypothesis(
        id="late_work_sleep",
        treatment_col="work_late_flag",
        outcome_col="sleep_total_min",
        covariate_cols=["sleep_lag1", "day_of_week", "is_weekend"],
        min_rows=30,
        binary_treatment=True,
        min_treated_days=8,
        treatment_label="Working until 8 pm or later (yes/no)",
        outcome_label="Sleep duration that night (min)",
        category="work",
    ),

    # 53-54. Travel time → Sleep that night / Next-day HRV
    Hypothesis(
        id="travel_hours_sleep",
        treatment_col="travel_hours",
        outcome_col="sleep_total_min",
        covariate_cols=["sleep_lag1", "day_of_week", "is_weekend"],
        min_rows=30,
        treatment_label="Time spent travelling (per hour)",
        outcome_label="Sleep duration that night (min)",
        category="lifestyle",
    ),
    Hypothesis(
        id="travel_hours_hrv",
        treatment_col="travel_hours",
        outcome_col="hrv_next",
        covariate_cols=["hrv_lag1", "sleep_total_min", "day_of_week"],
        min_rows=30,
        treatment_label="Time spent travelling (per hour)",
        outcome_label="Next-day HRV (ms)",
        category="lifestyle",
    ),
    # ── SCREEN TIME (check-in) and WHOOP STRAIN ─────────────────────────────

    # 55-58. Screen time and late-night phone use → sleep / next-day HRV
    Hypothesis(
        id="screen_hours_sleep",
        treatment_col="screen_hours",
        outcome_col="sleep_total_min",
        covariate_cols=["sleep_lag1", "day_of_week", "is_weekend"],
        min_rows=30,
        treatment_label="Screen time (per hour)",
        outcome_label="Sleep duration that night (min)",
        category="lifestyle",
    ),
    Hypothesis(
        id="screen_hours_hrv",
        treatment_col="screen_hours",
        outcome_col="hrv_next",
        covariate_cols=["hrv_lag1", "sleep_total_min", "day_of_week"],
        min_rows=30,
        treatment_label="Screen time (per hour)",
        outcome_label="Next-day HRV (ms)",
        category="lifestyle",
    ),
    Hypothesis(
        id="late_screen_sleep",
        treatment_col="late_screen_flag",
        outcome_col="sleep_total_min",
        covariate_cols=["sleep_lag1", "day_of_week", "is_weekend"],
        min_rows=30,
        binary_treatment=True,
        min_treated_days=8,
        treatment_label="On your phone after 11 pm (yes/no)",
        outcome_label="Sleep duration that night (min)",
        category="lifestyle",
    ),
    Hypothesis(
        id="late_screen_deep_sleep",
        treatment_col="late_screen_flag",
        outcome_col="sleep_deep_min",
        covariate_cols=["sleep_lag1", "sleep_total_min", "day_of_week"],
        min_rows=30,
        binary_treatment=True,
        min_treated_days=8,
        treatment_label="On your phone after 11 pm (yes/no)",
        outcome_label="Deep sleep that night (minutes)",
        category="lifestyle",
    ),

    # 59-61. Whoop strain (how hard the day was) → recovery that follows
    Hypothesis(
        id="strain_hrv",
        treatment_col="strain",
        outcome_col="hrv_next",
        covariate_cols=["hrv_lag1", "sleep_total_min", "day_of_week"],
        min_rows=30,
        treatment_label="Whoop strain (per 3 points)",
        outcome_label="Next-day HRV (ms)",
        category="health",
        treatment_scale=3.0,
    ),
    Hypothesis(
        id="strain_rhr",
        treatment_col="strain",
        outcome_col="resting_hr_next",
        covariate_cols=["resting_hr", "sleep_total_min", "day_of_week"],
        min_rows=30,
        treatment_label="Whoop strain (per 3 points)",
        outcome_label="Next-day resting heart rate (bpm)",
        category="health",
        treatment_scale=3.0,
    ),
    Hypothesis(
        id="strain_sleep",
        treatment_col="strain",
        outcome_col="sleep_total_min",
        covariate_cols=["sleep_lag1", "day_of_week", "is_weekend"],
        min_rows=30,
        treatment_label="Whoop strain (per 3 points)",
        outcome_label="Sleep duration that night (min)",
        category="health",
        treatment_scale=3.0,
    ),

]

# Sensitive findings. They still appear inside the app for the person who
# logged them, but never on a lock-screen push (nudges), a share card, the
# PDF report, or "today's one thing" on Home.
PRIVATE_HYPOTHESIS_IDS = {"substance_hrv", "substance_deep_sleep", "gambling_sleep", "gambling_hrv"}


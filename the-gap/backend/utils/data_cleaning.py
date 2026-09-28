import pandas as pd
import numpy as np


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply standard cleaning to a daily health DataFrame:
    - Reindex to a continuous daily calendar (see REAL BUG note below)
    - Remove statistical outliers (3 sigma)
    - Add engineered features needed for causal hypotheses
    - Forward-fill sparse metrics (HRV, VO2max)
    """
    if df.empty:
        return df

    df = df.copy()

    # REAL BUG FIXED HERE: every "_lag1"/"_next" column below is built with
    # pandas .shift(), which shifts by ROW POSITION, not by calendar day.
    # If a day has zero data from every connected source (device not worn,
    # no journal entry, nothing synced) it was previously just a *missing
    # row* rather than a present-but-NaN one — so .shift(-1) on the row
    # before a gap silently pulled the value from 2+ calendar days later,
    # mislabeled as "tomorrow". This is exactly the class of misalignment
    # this app has already fixed for timezones/dates elsewhere, just at
    # the row level instead of the per-entry level. Reindexing to a
    # genuine continuous daily range up front means a gap day becomes an
    # explicit all-NaN row, so every shift() below now correctly measures
    # "the actual adjacent calendar day" — NaN when that day is truly
    # unknown, instead of a real-looking value from the wrong day.
    if isinstance(df.index, pd.DatetimeIndex) and len(df.index) > 1:
        full_range = pd.date_range(start=df.index.min(), end=df.index.max(), freq="D")
        df = df.reindex(full_range)

    # Binary/flag columns (0 or 1 only) used as treatments or covariates
    # across the causal hypotheses. These must NEVER go through 3-sigma
    # outlier removal below.
    #
    # REAL BUG FIXED HERE: for a rare binary event (say only ~5% of days
    # are "1"), the mean is close to 0 and the standard deviation is small,
    # so "mean + 3*std" can land below 1 — meaning the 3-sigma filter
    # actually treated the real "1" values as outliers and wiped them to
    # NaN. This directly undermined exactly the sparse binary hypotheses
    # this app depends on most (alcohol, late meetings, hard training
    # days, rain, journaled stress/conflict events) — it could zero out
    # the very treated days those hypotheses are trying to measure, and/or
    # make them look like they never had enough treated days to run at all.
    BINARY_COLS = {
        "alcohol_flag", "is_weekend", "has_late_meeting", "is_meeting_free",
        "afternoon_caffeine", "high_stress_flag", "stress_event",
        "conflict_event", "is_rainy", "is_hard_day",
    }

    # Remove outliers per column (3 standard deviations) — skip binary/flag columns
    numeric_cols = [c for c in df.select_dtypes(include=[np.number]).columns if c not in BINARY_COLS]
    for col in numeric_cols:
        mean = df[col].mean()
        std = df[col].std()
        if std > 0:
            df[col] = df[col].where(
                (df[col] >= mean - 3 * std) & (df[col] <= mean + 3 * std)
            )

    # --- Engineered features ---

    # Day of week (0=Monday, 6=Sunday) — important confounder
    if "day_of_week" not in df.columns:
        if "date" in df.columns:
            df["day_of_week"] = pd.to_datetime(df["date"]).dt.dayofweek
        elif hasattr(df.index, "dayofweek"):
            df["day_of_week"] = df.index.dayofweek
        else:
            df["day_of_week"] = 0  # fallback

    # Weekend flag
    if "is_weekend" not in df.columns:
        df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)

    # REAL BUG FIXED HERE: these lag/next columns used to be computed
    # *after* the forward-fill below, so resting_hr_next silently inherited
    # a stale, forward-filled value instead of a genuine next-day reading
    # (or a correct NaN) whenever that day's real measurement was missing.
    # Computing them here, from the raw pre-ffill values, means a gap day
    # honestly produces NaN rather than a fabricated "next day" value.

    # Lagged HRV (prior day)
    if "hrv" in df.columns:
        df["hrv_lag1"] = df["hrv"].shift(1)

    # Lagged sleep
    if "sleep_total_min" in df.columns:
        df["sleep_lag1"] = df["sleep_total_min"].shift(1)
        # Sleep debt: rolling 7-day average minus 480 minutes (8 hours)
        df["sleep_debt_min"] = (df["sleep_total_min"].rolling(7, min_periods=3).mean() - 480).fillna(0)

    # Bedtime deviation: how many minutes later/earlier than personal mean bedtime.
    # Only computed as a duration-based proxy when a real bedtime-derived
    # value isn't already present — some parsers (e.g. Oura, see
    # parsers/oura.py) compute a genuine bedtime-timing signal directly;
    # this used to silently overwrite that better value every time.
    if "sleep_deviation" not in df.columns and "sleep_total_min" in df.columns:
        personal_mean_sleep = df["sleep_total_min"].mean()
        df["sleep_deviation"] = (df["sleep_total_min"] - personal_mean_sleep).abs()

    # Next-day metrics (shifted back one day, used as outcomes)
    if "hrv" in df.columns:
        df["hrv_next"] = df["hrv"].shift(-1)
    if "resting_hr" in df.columns:
        df["resting_hr_next"] = df["resting_hr"].shift(-1)

    # Forward fill sparse metrics (max 3 days) — deliberately AFTER the
    # lag/next columns above are computed, so those still reflect genuine
    # measurements rather than carried-forward stand-ins.
    sparse_cols = [c for c in ["vo2max", "resting_hr"] if c in df.columns]
    if sparse_cols:
        df[sparse_cols] = df[sparse_cols].ffill(limit=3)

    return df


def validate_minimum_data(df: pd.DataFrame) -> tuple[bool, int, int]:
    """
    Check if the dataframe has enough data to run at least one hypothesis.
    Returns (has_enough, days_available, days_needed).
    """
    if df.empty:
        return False, 0, 30

    # Count days with at least one non-NaN health metric (excluding engineered cols)
    health_cols = [c for c in df.columns if c not in ("day_of_week", "is_weekend")]
    days_with_data = df[health_cols].dropna(how="all").shape[0]

    return days_with_data >= 30, days_with_data, 30

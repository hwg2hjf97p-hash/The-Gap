import pandas as pd
import numpy as np


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply standard cleaning to a daily health DataFrame:
    - Remove statistical outliers (3 sigma)
    - Add engineered features needed for causal hypotheses
    - Forward-fill sparse metrics (HRV, VO2max)
    """
    if df.empty:
        return df

    df = df.copy()

    # Remove outliers per column (3 standard deviations)
    for col in df.select_dtypes(include=[np.number]).columns:
        mean = df[col].mean()
        std = df[col].std()
        if std > 0:
            df[col] = df[col].where(
                (df[col] >= mean - 3 * std) & (df[col] <= mean + 3 * std)
            )

    # Forward fill sparse metrics (max 3 days)
    sparse_cols = [c for c in ["vo2max", "resting_hr"] if c in df.columns]
    if sparse_cols:
        df[sparse_cols] = df[sparse_cols].ffill(limit=3)

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

    # Lagged HRV (prior day)
    if "hrv" in df.columns:
        df["hrv_lag1"] = df["hrv"].shift(1)

    # Lagged sleep
    if "sleep_total_min" in df.columns:
        df["sleep_lag1"] = df["sleep_total_min"].shift(1)
        # Sleep debt: rolling 7-day average minus 480 minutes (8 hours)
        df["sleep_debt_min"] = (df["sleep_total_min"].rolling(7, min_periods=3).mean() - 480).fillna(0)

    # Bedtime deviation: how many minutes later/earlier than personal mean bedtime
    # Proxy: we infer bedtime from sleep start (not directly available in aggregated data)
    # Use sleep_total_min variance as a proxy for consistency
    if "sleep_total_min" in df.columns:
        personal_mean_sleep = df["sleep_total_min"].mean()
        df["sleep_deviation"] = (df["sleep_total_min"] - personal_mean_sleep).abs()

    # Next-day metrics (shifted back one day, used as outcomes)
    if "hrv" in df.columns:
        df["hrv_next"] = df["hrv"].shift(-1)
    if "resting_hr" in df.columns:
        df["resting_hr_next"] = df["resting_hr"].shift(-1)

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

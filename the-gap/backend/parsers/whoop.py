"""
Whoop CSV parser.
Handles both:
  1. Single combined CSV (test data / simplified export)
  2. Multi-file Whoop export ZIP (physiological, sleeps, workouts, journal)
"""

from __future__ import annotations

import io
import zipfile
import logging

import pandas as pd

logger = logging.getLogger(__name__)

COLUMN_MAP = {
    "hrv last night (ms)":      "hrv",
    "hrv_rmssd_milli":          "hrv",
    "resting heart rate (bpm)": "resting_hr",
    "resting_heart_rate_bpm":   "resting_hr",
    "recovery score %":         "recovery_score",
    "recovery_score":           "recovery_score",
    "sleep duration":           "sleep_total_min",
    "sleep_duration_minutes":   "sleep_total_min",
    "time in deep":             "sleep_deep_min",
    "deep_sleep_minutes":       "sleep_deep_min",
    "sleep consistency %":      "sleep_consistency",
    "strain":                   "active_energy",
    "strain_score":             "active_energy",
    "active calories":          "active_energy_kcal",
    "active_calories":          "active_energy_kcal",
    "alcohol":                  "alcohol_flag",
    "alcohol_flag":             "alcohol_flag",
    "day_of_week":              "day_of_week",
    "is_weekend":               "is_weekend",
}


def parse_whoop(file_bytes: bytes) -> pd.DataFrame:
    if file_bytes[:2] == b'PK':
        return _parse_zip(file_bytes)
    else:
        return _parse_single_csv(file_bytes)


def _parse_single_csv(file_bytes: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(file_bytes))
    df.columns = [c.lower().strip() for c in df.columns]
    df = df.rename(columns=COLUMN_MAP)

    if "date" not in df.columns:
        raise ValueError("CSV must have a 'date' column")

    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()

    for col in ["sleep_total_min", "sleep_deep_min"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "day_of_week" not in df.columns:
        df["day_of_week"] = df.index.dayofweek
    if "is_weekend" not in df.columns:
        df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)

    if "hrv" in df.columns:
        df["hrv_next"] = df["hrv"].shift(-1)
        df["hrv_lag1"] = df["hrv"].shift(1)
    if "resting_hr" in df.columns:
        df["resting_hr_next"] = df["resting_hr"].shift(-1)
    if "sleep_total_min" in df.columns:
        df["sleep_lag1"] = df["sleep_total_min"].shift(1)
        mean_bedtime = df["sleep_total_min"].mean()
        df["sleep_deviation"] = (df["sleep_total_min"] - mean_bedtime).abs()

    if "active_energy" in df.columns and "steps" not in df.columns:
        df["steps"] = df["active_energy"] * 950

    return df.reset_index()


def _parse_zip(file_bytes: bytes) -> pd.DataFrame:
    frames = {}
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
        for name in zf.namelist():
            if not name.endswith(".csv"):
                continue
            key = name.lower().split("/")[-1].replace(".csv", "")
            try:
                df = pd.read_csv(zf.open(name))
                df.columns = [c.lower().strip() for c in df.columns]
                df = df.rename(columns=COLUMN_MAP)
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"])
                    frames[key] = df
            except Exception as e:
                logger.warning("Could not parse %s: %s", name, e)

    if not frames:
        raise ValueError("No valid CSV files found in Whoop ZIP")

    merged = None
    for key, df in frames.items():
        df = df.set_index("date")
        merged = df if merged is None else merged.join(df, how="outer", rsuffix=f"_{key}")

    merged = merged.sort_index()

    if "hrv" in merged.columns:
        merged["hrv_next"] = merged["hrv"].shift(-1)
        merged["hrv_lag1"] = merged["hrv"].shift(1)
    if "resting_hr" in merged.columns:
        merged["resting_hr_next"] = merged["resting_hr"].shift(-1)
    if "sleep_total_min" in merged.columns:
        merged["sleep_lag1"] = merged["sleep_total_min"].shift(1)
        merged["sleep_deviation"] = (merged["sleep_total_min"] - merged["sleep_total_min"].mean()).abs()
    if "day_of_week" not in merged.columns:
        merged["day_of_week"] = merged.index.dayofweek
    if "is_weekend" not in merged.columns:
        merged["is_weekend"] = (merged["day_of_week"] >= 5).astype(int)
    if "active_energy" in merged.columns and "steps" not in merged.columns:
        merged["steps"] = merged["active_energy"] * 950

    return merged.reset_index()
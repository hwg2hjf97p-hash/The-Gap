"""
Oura Ring parser for The Gap.
Accepts a CSV export from the Oura app or a JSON export from the Oura API.

Column mappings (Oura CSV export):
  date, readiness_score, hrv_balance, resting_heart_rate, total_sleep_duration,
  deep_sleep_duration, sleep_score, activity_score, steps, active_calories,
  inactivity_alerts, bedtime_start, bedtime_end, temperature_deviation
"""

from __future__ import annotations

import io
import json
import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ── Column name aliases ──────────────────────────────────────────────────────
# Map Oura export column names → The Gap internal column names

OURA_CSV_MAP = {
    # HRV
    "hrv_balance":                  "hrv",
    "average_hrv":                  "hrv",
    "hrv_average":                  "hrv",

    # Resting HR
    "resting_heart_rate":           "resting_hr",
    "lowest_resting_heart_rate":    "resting_hr",

    # Sleep
    "total_sleep_duration":         "sleep_total_sec",  # seconds — converted below
    "deep_sleep_duration":          "sleep_deep_sec",
    "total_sleep":                  "sleep_total_sec",
    "deep_sleep":                   "sleep_deep_sec",
    "sleep_duration":               "sleep_total_sec",

    # Activity
    "steps":                        "steps",
    "active_calories":              "active_energy",
    "cal_active":                   "active_energy",
    "total_calories":               "active_energy",

    # Scores
    "readiness_score":              "recovery_score",
    "sleep_score":                  "sleep_score",
    "activity_score":               "activity_score",

    # Temperature (unique to Oura)
    "temperature_deviation":        "temp_deviation",
    "skin_temperature":             "temp_deviation",

    # Bedtime
    "bedtime_start":                "bedtime_start_raw",
    "bedtime_end":                  "bedtime_end_raw",
}


def parse_oura(file_bytes: bytes) -> pd.DataFrame:
    """
    Parse an Oura Ring export (CSV or JSON) into a standardised DataFrame.
    Returns a DataFrame with date index and The Gap column names.
    Raises ValueError if parsing fails.
    """
    text = file_bytes.decode("utf-8", errors="replace")

    # Try JSON first
    if text.lstrip().startswith("{") or text.lstrip().startswith("["):
        try:
            return _parse_oura_json(text)
        except Exception as exc:
            logger.warning("Oura JSON parse failed: %s — trying CSV", exc)

    # Try CSV
    return _parse_oura_csv(text)


def _parse_oura_csv(text: str) -> pd.DataFrame:
    """Parse Oura CSV export."""
    df = pd.read_csv(io.StringIO(text))
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # Rename to internal column names
    rename = {k: v for k, v in OURA_CSV_MAP.items() if k in df.columns}
    df = df.rename(columns=rename)

    # Parse date
    date_col = next(
        (c for c in ["date", "day", "summary_date"] if c in df.columns), None
    )
    if date_col is None:
        raise ValueError("No date column found in Oura CSV export.")

    df["date"] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=["date"])
    df = df.set_index("date").sort_index()

    return _normalise(df)


def _parse_oura_json(text: str) -> pd.DataFrame:
    """Parse Oura API JSON export (nested structure)."""
    data = json.loads(text)
    rows = []

    # Handle both list of days and nested dict with sleep/activity/readiness keys
    if isinstance(data, list):
        for item in data:
            row = _flatten_oura_json_item(item)
            if row:
                rows.append(row)
    elif isinstance(data, dict):
        # Try to merge sleep, readiness, and activity arrays
        sleep_items = {
            item.get("day") or item.get("date"): item
            for item in data.get("sleep", [])
        }
        readiness_items = {
            item.get("day") or item.get("date"): item
            for item in data.get("readiness", [])
        }
        activity_items = {
            item.get("day") or item.get("date"): item
            for item in data.get("activity", data.get("daily_activity", []))
        }

        all_dates = set(sleep_items) | set(readiness_items) | set(activity_items)
        for date in sorted(all_dates):
            row = {"date": date}
            for src in [sleep_items.get(date, {}), readiness_items.get(date, {}), activity_items.get(date, {})]:
                row.update(_flatten_oura_json_item(src))
            rows.append(row)

    if not rows:
        raise ValueError("No data rows found in Oura JSON export.")

    df = pd.DataFrame(rows)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    rename = {k: v for k, v in OURA_CSV_MAP.items() if k in df.columns}
    df = df.rename(columns=rename)

    df["date"] = pd.to_datetime(df.get("date", df.index), errors="coerce")
    df = df.dropna(subset=["date"])
    df = df.set_index("date").sort_index()

    return _normalise(df)


def _flatten_oura_json_item(item: dict) -> dict:
    """Flatten a single Oura JSON item to a flat row dict."""
    if not isinstance(item, dict):
        return {}
    row = {}
    for k, v in item.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            row[k] = v
        elif isinstance(v, dict):
            # Flatten one level
            for sub_k, sub_v in v.items():
                row[f"{k}_{sub_k}"] = sub_v
    return row


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    """Convert units and engineer features."""
    # Sleep: seconds → minutes
    if "sleep_total_sec" in df.columns:
        df["sleep_total_min"] = pd.to_numeric(df["sleep_total_sec"], errors="coerce") / 60
    if "sleep_deep_sec" in df.columns:
        df["sleep_deep_min"] = pd.to_numeric(df["sleep_deep_sec"], errors="coerce") / 60

    # Ensure numeric
    numeric_cols = ["hrv", "resting_hr", "steps", "active_energy", "recovery_score",
                    "sleep_total_min", "sleep_deep_min", "temp_deviation"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Alcohol flag — Oura doesn't track this, default 0
    if "alcohol_flag" not in df.columns:
        df["alcohol_flag"] = 0

    # Bedtime deviation from personal mean
    if "bedtime_start_raw" in df.columns:
        try:
            bedtime_ts = pd.to_datetime(df["bedtime_start_raw"], errors="coerce")
            bed_hour = bedtime_ts.dt.hour + bedtime_ts.dt.minute / 60
            df["sleep_deviation"] = (bed_hour - bed_hour.mean()).abs()
        except Exception:
            pass

    logger.info("Oura: parsed %d days, columns: %s", len(df), list(df.columns))
    return df

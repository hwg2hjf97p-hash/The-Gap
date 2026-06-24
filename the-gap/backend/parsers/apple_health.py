import pandas as pd
import numpy as np
from lxml import etree
import zipfile
import io
import os
from datetime import datetime, timedelta

# Record types we care about — everything else is discarded
RELEVANT_TYPES = {
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": "hrv",
    "HKQuantityTypeIdentifierStepCount": "steps",
    "HKQuantityTypeIdentifierActiveEnergyBurned": "active_energy",
    "HKQuantityTypeIdentifierRestingHeartRate": "resting_hr",
    "HKQuantityTypeIdentifierMindfulSession": "mindful_minutes",
    "HKQuantityTypeIdentifierDietaryEnergyConsumed": "dietary_energy",
    "HKQuantityTypeIdentifierVO2Max": "vo2max",
}

SLEEP_TYPE = "HKCategoryTypeIdentifierSleepAnalysis"

SLEEP_STAGE_MAP = {
    "HKCategoryValueSleepAnalysisAsleepREM": "rem",
    "HKCategoryValueSleepAnalysisAsleepDeep": "deep",
    "HKCategoryValueSleepAnalysisAsleepCore": "core",
    "HKCategoryValueSleepAnalysisAsleepUnspecified": "unspecified",
}


def parse_apple_health(file_bytes: bytes) -> pd.DataFrame:
    """
    Parse Apple Health XML export (raw .xml or .zip containing export.xml).
    Returns a cleaned daily DataFrame.
    """
    xml_bytes = _extract_xml(file_bytes)
    raw_records = _parse_xml(xml_bytes)
    daily_df = _aggregate_to_daily(raw_records)
    return daily_df


def _extract_xml(file_bytes: bytes) -> bytes:
    """Handle both raw .xml and .zip (Apple Health export format)."""
    # Try as zip first
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
            names = z.namelist()
            # Look for export.xml anywhere in the zip
            xml_name = next((n for n in names if n.endswith("export.xml")), None)
            if xml_name:
                return z.read(xml_name)
            raise ValueError("No export.xml found in zip file")
    except zipfile.BadZipFile:
        # Not a zip — treat as raw XML
        return file_bytes


def _parse_xml(xml_bytes: bytes) -> dict:
    """Stream-parse the XML to extract only relevant records."""
    records = {metric: [] for metric in RELEVANT_TYPES.values()}
    records["sleep"] = []

    context = etree.iterparse(io.BytesIO(xml_bytes), events=("start",), tag=("Record", "Workout"))

    for _, elem in context:
        record_type = elem.get("type", "")

        # Quantity records
        if record_type in RELEVANT_TYPES:
            metric = RELEVANT_TYPES[record_type]
            try:
                records[metric].append({
                    "date": _parse_date(elem.get("startDate", "")),
                    "value": float(elem.get("value", 0)),
                    "source": elem.get("sourceName", ""),
                })
            except (ValueError, TypeError):
                pass

        # Sleep records
        elif record_type == SLEEP_TYPE:
            stage_value = elem.get("value", "")
            stage = SLEEP_STAGE_MAP.get(stage_value)
            if stage:
                try:
                    start = _parse_datetime(elem.get("startDate", ""))
                    end = _parse_datetime(elem.get("endDate", ""))
                    duration_min = (end - start).total_seconds() / 60
                    if 0 < duration_min < 720:  # sanity check: max 12 hours
                        records["sleep"].append({
                            "date": start.date(),
                            "stage": stage,
                            "duration_min": duration_min,
                            "source": elem.get("sourceName", ""),
                        })
                except (ValueError, TypeError):
                    pass

        # Free element memory to handle large files
        elem.clear()

    return records


def _aggregate_to_daily(records: dict) -> pd.DataFrame:
    """Convert raw records into one row per day with aggregated metrics."""
    
    # --- Simple metrics: daily aggregation ---
    daily = {}

    for metric, rows in records.items():
        if metric == "sleep" or not rows:
            continue
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"]).dt.date

        if metric == "hrv":
            # Use morning HRV only (6am–10am)
            df_full = pd.DataFrame(rows)
            df_full["datetime"] = pd.to_datetime([r.get("date") for r in records[metric]])
            morning = df_full[df_full["datetime"].dt.hour.between(6, 10)]
            if not morning.empty:
                daily[metric] = morning.groupby(morning["datetime"].dt.date)["value"].mean()
            else:
                daily[metric] = df.groupby("date")["value"].mean()
        elif metric in ("steps", "active_energy", "mindful_minutes", "dietary_energy"):
            daily[metric] = df.groupby("date")["value"].sum()
        elif metric == "resting_hr":
            daily[metric] = df.groupby("date")["value"].mean()
        elif metric == "vo2max":
            daily[metric] = df.groupby("date")["value"].mean()

    # --- Sleep: deduplicate sources, compute per-stage minutes ---
    sleep_rows = records.get("sleep", [])
    if sleep_rows:
        sleep_df = pd.DataFrame(sleep_rows)
        sleep_df["date"] = pd.to_datetime(sleep_df["date"]).dt.date

        # Prefer Apple Watch source
        sources = sleep_df["source"].unique()
        watch_source = next((s for s in sources if "watch" in s.lower()), None)
        if watch_source:
            sleep_df = sleep_df[sleep_df["source"] == watch_source]

        sleep_pivot = sleep_df.groupby(["date", "stage"])["duration_min"].sum().unstack(fill_value=0)
        for stage in ["rem", "deep", "core", "unspecified"]:
            if stage in sleep_pivot.columns:
                daily[f"sleep_{stage}_min"] = sleep_pivot[stage]
        daily["sleep_total_min"] = sleep_df.groupby("date")["duration_min"].sum()

    # --- Build final DataFrame ---
    if not daily:
        return pd.DataFrame()

    result = pd.DataFrame(daily)
    result.index = pd.to_datetime(result.index)
    result = result.sort_index()

    # Fill gaps with NaN (not 0 — important for causal inference)
    if len(result) > 1:
        full_range = pd.date_range(result.index.min(), result.index.max(), freq="D")
        result = result.reindex(full_range)

    return result


def _parse_date(date_str: str):
    """Parse Apple Health date string to date object."""
    return datetime.strptime(date_str[:10], "%Y-%m-%d").date()


def _parse_datetime(date_str: str) -> datetime:
    """Parse Apple Health datetime string."""
    # Format: "2026-06-22 08:12:03 +1000"
    try:
        return datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return datetime.strptime(date_str[:10], "%Y-%m-%d")

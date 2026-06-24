import pandas as pd
import zipfile
import io


def parse_whoop(file_bytes: bytes) -> pd.DataFrame:
    """
    Parse Whoop data export zip.
    Returns a cleaned daily DataFrame with standardised column names.
    """
    csv_files = _extract_csvs(file_bytes)
    daily = _merge_whoop_data(csv_files)
    return daily


def _extract_csvs(file_bytes: bytes) -> dict:
    """Extract all CSVs from the Whoop zip export."""
    csvs = {}
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
            for name in z.namelist():
                if name.endswith(".csv"):
                    key = name.split("/")[-1].replace(".csv", "").lower()
                    csvs[key] = pd.read_csv(io.BytesIO(z.read(name)))
    except zipfile.BadZipFile:
        raise ValueError("Whoop export must be a zip file")
    return csvs


def _merge_whoop_data(csvs: dict) -> pd.DataFrame:
    """Merge Whoop CSVs into a single daily DataFrame with standardised column names."""
    frames = []

    # Physiological cycles (primary recovery metrics)
    if "physiological_cycles" in csvs:
        df = csvs["physiological_cycles"].copy()
        df.columns = [c.lower().strip() for c in df.columns]
        df = df.rename(columns={
            "cycle start time": "date",
            "recovery score %": "recovery_score",
            "hrv last night (ms)": "hrv",
            "resting heart rate (bpm)": "resting_hr",
            "respiratory rate (rpm)": "respiratory_rate",
        })
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.date
            df = df[["date"] + [c for c in ["hrv", "resting_hr", "recovery_score", "respiratory_rate"] if c in df.columns]]
            frames.append(df.set_index("date"))

    # Sleep data
    if "sleeps" in csvs:
        df = csvs["sleeps"].copy()
        df.columns = [c.lower().strip() for c in df.columns]
        df = df.rename(columns={
            "cycle start time": "date",
            "sleep duration": "sleep_total_min",
            "sleep performance %": "sleep_performance",
            "time in rem": "sleep_rem_min",
            "time in deep": "sleep_deep_min",
            "sleep consistency %": "sleep_consistency",
        })
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.date
            sleep_cols = [c for c in ["sleep_total_min", "sleep_rem_min", "sleep_deep_min", "sleep_performance", "sleep_consistency"] if c in df.columns]
            df = df[["date"] + sleep_cols]
            # Convert durations from hh:mm:ss to minutes if needed
            for col in ["sleep_total_min", "sleep_rem_min", "sleep_deep_min"]:
                if col in df.columns and df[col].dtype == object:
                    df[col] = df[col].apply(_duration_to_minutes)
            frames.append(df.set_index("date"))

    # Workouts
    if "workouts" in csvs:
        df = csvs["workouts"].copy()
        df.columns = [c.lower().strip() for c in df.columns]
        df = df.rename(columns={
            "cycle start time": "date",
            "duration (min)": "workout_duration_min",
            "strain": "workout_strain",
            "average heart rate (bpm)": "workout_avg_hr",
        })
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.date
            workout_cols = [c for c in ["workout_duration_min", "workout_strain", "workout_avg_hr"] if c in df.columns]
            if workout_cols:
                daily_workouts = df.groupby("date")[workout_cols].max()
                frames.append(daily_workouts)

    # Journal entries (alcohol, caffeine, stress flags)
    if "journal_entries" in csvs:
        df = csvs["journal_entries"].copy()
        df.columns = [c.lower().strip() for c in df.columns]
        if "answer text" in df.columns and "question text" in df.columns:
            # Pivot to wide format
            df["date"] = pd.to_datetime(df.get("cycle start time", df.iloc[:, 0])).dt.date
            alcohol_rows = df[df["question text"].str.contains("alcohol|drink", case=False, na=False)]
            if not alcohol_rows.empty:
                alcohol_flag = alcohol_rows.groupby("date")["answer text"].apply(
                    lambda x: int(any(str(v).lower() in ["yes", "true", "1"] for v in x))
                ).rename("alcohol_flag")
                frames.append(alcohol_flag.to_frame())

    if not frames:
        return pd.DataFrame()

    result = frames[0]
    for f in frames[1:]:
        result = result.join(f, how="outer")

    result.index = pd.to_datetime(result.index)
    result = result.sort_index()

    # Reindex to fill date gaps with NaN
    if len(result) > 1:
        full_range = pd.date_range(result.index.min(), result.index.max(), freq="D")
        result = result.reindex(full_range)

    return result


def _duration_to_minutes(val) -> float:
    """Convert hh:mm:ss string to float minutes."""
    if pd.isna(val):
        return float("nan")
    try:
        parts = str(val).split(":")
        if len(parts) == 3:
            return int(parts[0]) * 60 + int(parts[1]) + int(parts[2]) / 60
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        return float(val)
    except (ValueError, AttributeError):
        return float("nan")

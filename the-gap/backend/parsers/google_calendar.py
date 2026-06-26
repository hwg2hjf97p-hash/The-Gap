"""
Google Calendar parser for The Gap.
Accepts a Google Calendar JSON export (Takeout) or iCal (.ics) file.
Extracts daily event count, meeting hours, late meeting flag, and meeting-free days.
"""

from __future__ import annotations

import io
import json
import logging
import re
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ── iCal parser (no external deps) ──────────────────────────────────────────

def _parse_ical_datetime(value: str) -> Optional[datetime]:
    """Parse iCal DTSTART/DTEND value into a datetime."""
    value = value.strip()
    # All-day event: YYYYMMDD
    if len(value) == 8:
        try:
            return datetime.strptime(value, "%Y%m%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    # Datetime with Z suffix: YYYYMMDDTHHmmSSZ
    if value.endswith("Z"):
        try:
            return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    # Datetime without Z: YYYYMMDDTHHmmSS
    try:
        return datetime.strptime(value[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _events_from_ical(text: str) -> list[dict]:
    """Extract events from iCal text. Returns list of {start, end, summary}."""
    events = []
    in_event = False
    current: dict = {}

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if line == "BEGIN:VEVENT":
            in_event = True
            current = {}
            continue

        if line == "END:VEVENT":
            if in_event and "start" in current and "end" in current:
                events.append(current)
            in_event = False
            current = {}
            continue

        if not in_event:
            continue

        # Strip property params (e.g. DTSTART;TZID=Australia/Brisbane:20260101...)
        if line.startswith("DTSTART"):
            val = line.split(":", 1)[-1]
            dt = _parse_ical_datetime(val)
            if dt:
                current["start"] = dt

        elif line.startswith("DTEND"):
            val = line.split(":", 1)[-1]
            dt = _parse_ical_datetime(val)
            if dt:
                current["end"] = dt

        elif line.startswith("SUMMARY:"):
            current["summary"] = line[len("SUMMARY:"):].strip()

        elif line.startswith("STATUS:"):
            current["status"] = line[len("STATUS:"):].strip()

    return events


def _events_from_google_takeout_json(data: dict) -> list[dict]:
    """Parse Google Takeout calendar JSON format."""
    events = []
    items = data.get("items", [])
    for item in items:
        if item.get("status") == "cancelled":
            continue

        start_info = item.get("start", {})
        end_info = item.get("end", {})

        start_str = start_info.get("dateTime") or start_info.get("date")
        end_str = end_info.get("dateTime") or end_info.get("date")

        if not start_str or not end_str:
            continue

        try:
            start = pd.Timestamp(start_str).to_pydatetime()
            end = pd.Timestamp(end_str).to_pydatetime()
        except Exception:
            continue

        events.append({
            "start": start,
            "end": end,
            "summary": item.get("summary", ""),
        })

    return events


def _daily_features_from_events(events: list[dict], n_days: int = 180) -> pd.DataFrame:
    """
    Aggregate events into daily features:
      - calendar_events: total events that day
      - meeting_hours: hours in meetings (events > 15 min, skip all-day)
      - has_late_meeting: any event starting after 18:00
      - is_meeting_free: 1 if no meetings at all
    """
    if not events:
        return pd.DataFrame()

    # Date range
    all_starts = [e["start"] for e in events if isinstance(e["start"], datetime)]
    if not all_starts:
        return pd.DataFrame()

    max_date = max(all_starts).date()
    min_date = max_date - timedelta(days=n_days)
    date_range = pd.date_range(start=min_date, end=max_date, freq="D")
    rows = []

    for date in date_range:
        day = date.date()
        day_events = [
            e for e in events
            if isinstance(e["start"], datetime) and e["start"].date() == day
        ]

        # Skip all-day events (duration >= 20 hours)
        real_events = []
        for e in day_events:
            try:
                duration_h = (e["end"] - e["start"]).total_seconds() / 3600
                if duration_h < 20:  # not an all-day placeholder
                    real_events.append({**e, "duration_h": duration_h})
            except Exception:
                pass

        meeting_hours = sum(
            e["duration_h"] for e in real_events if e["duration_h"] >= 0.25
        )
        has_late = int(any(
            e["start"].hour >= 18 for e in real_events
        ))
        is_free = int(len(real_events) == 0)

        rows.append({
            "date": pd.Timestamp(day),
            "calendar_events": len(real_events),
            "meeting_hours": round(meeting_hours, 2),
            "has_late_meeting": has_late,
            "is_meeting_free": is_free,
        })

    df = pd.DataFrame(rows).set_index("date")
    return df


# ── Public API ───────────────────────────────────────────────────────────────

def parse_google_calendar(file_bytes: bytes) -> pd.DataFrame:
    """
    Parse a Google Calendar export:
      - .ics / .ical file
      - Google Takeout .zip containing .ics files
      - Google Calendar API JSON export

    Returns a DataFrame with daily calendar features indexed by date.
    Raises ValueError if the file cannot be parsed.
    """
    # Try ZIP (Google Takeout)
    if file_bytes[:2] == b"PK":
        try:
            return _parse_zip(file_bytes)
        except Exception as exc:
            logger.warning("ZIP parse failed: %s — trying raw iCal", exc)

    text = None
    try:
        text = file_bytes.decode("utf-8", errors="replace")
    except Exception:
        raise ValueError("Could not decode calendar file as text.")

    # Try JSON (Google Calendar API export)
    if text.lstrip().startswith("{"):
        try:
            data = json.loads(text)
            events = _events_from_google_takeout_json(data)
            if events:
                return _daily_features_from_events(events)
        except Exception:
            pass

    # Try iCal
    if "BEGIN:VCALENDAR" in text or "BEGIN:VEVENT" in text:
        events = _events_from_ical(text)
        if events:
            return _daily_features_from_events(events)

    raise ValueError(
        "Could not parse calendar file. "
        "Please export as .ics from Google Calendar Settings → Import & Export."
    )


def _parse_zip(file_bytes: bytes) -> pd.DataFrame:
    """Extract and parse all .ics files from a ZIP archive."""
    all_events = []
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
        ical_names = [n for n in zf.namelist() if n.lower().endswith(".ics")]
        if not ical_names:
            raise ValueError("No .ics files found in ZIP archive.")
        for name in ical_names:
            text = zf.read(name).decode("utf-8", errors="replace")
            all_events.extend(_events_from_ical(text))

    return _daily_features_from_events(all_events)


def merge_calendar_into_health(
    health_df: pd.DataFrame,
    calendar_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Left-join calendar features onto the main health dataframe.
    Both must be indexed by date (pd.Timestamp).
    Missing calendar days get 0 events (assumed no data = no meetings).
    """
    if calendar_df.empty:
        return health_df

    # Align index types
    health_df.index = pd.to_datetime(health_df.index)
    calendar_df.index = pd.to_datetime(calendar_df.index)

    merged = health_df.join(calendar_df, how="left")

    # Fill calendar cols with 0 where no calendar data exists
    cal_cols = ["calendar_events", "meeting_hours", "has_late_meeting", "is_meeting_free"]
    for col in cal_cols:
        if col in merged.columns:
            merged[col] = merged[col].fillna(0)

    return merged

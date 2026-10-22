"""
Undoing a quick log.

A sentence like "had a beer and a coffee" can add water, change check-in counts, add food, save a weight and keep a note all at
once. The server says exactly what it created (the `Undo` it returns with the log), and the app hands it back if the person taps
Undo. Nothing here trusts that blindly: ids are checked, every delete is scoped to the signed-in person in routers/log.py, and
only the few check-in fields a quick log can change are ever restored.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field

SAFE_ID = re.compile(r"^[0-9A-Za-z-]{8,64}$")

# The check-in fields a quick log can change, and what kind of value each holds. Nothing else is ever written back.
CHECKIN_UNDO_FIELDS: dict[str, type] = {
    "alcohol_drinks": int,
    "caffeine_drinks": int,
    "cigarettes": int,
    "energy_drinks": int,
    "alcohol": bool,
    "afternoon_caffeine": bool,
    "partial": bool,
    "alcohol_time": str,
    "energy_drink_time": str,
}


class Undo(BaseModel):
    """What one quick log created. Sent back to the app with the log, and sent here again to reverse it."""

    note_id: Optional[str] = Field(default=None, max_length=64)
    water_ids: list[str] = Field(default_factory=list, max_length=20)
    food_ids: list[str] = Field(default_factory=list, max_length=50)
    checkin_day: Optional[str] = Field(default=None, max_length=10)
    checkin_touched: bool = False
    # The check-in fields as they were before the log; None means there was no check-in for that day yet.
    checkin_before: Optional[dict] = None
    weight_day: Optional[str] = Field(default=None, max_length=10)
    weight_touched: bool = False
    weight_previous_kg: Optional[float] = None


def safe_ids(values) -> list[str]:
    """Only values that look like row ids, so nothing else can be slipped into a filter."""
    return [v for v in (values or []) if isinstance(v, str) and SAFE_ID.match(v)]


def snapshot_checkin(row: Optional[dict]) -> Optional[dict]:
    """The undoable fields of a check-in row as they are now. None when there is no row."""
    if not row:
        return None
    return {k: row.get(k) for k in CHECKIN_UNDO_FIELDS if k in row}


def restorable_fields(snapshot: Optional[dict]) -> dict:
    """The snapshot cleaned for writing back: only known fields, each as the right kind of value."""
    out: dict = {}
    for key, kind in CHECKIN_UNDO_FIELDS.items():
        if not snapshot or key not in snapshot:
            continue
        value = snapshot[key]
        if value is None:
            out[key] = None
        elif kind is bool:
            if isinstance(value, bool):
                out[key] = value
        elif kind is int:
            try:
                out[key] = max(0, int(value))
            except (TypeError, ValueError):
                continue
        elif kind is str:
            out[key] = str(value)[:60]
    return out

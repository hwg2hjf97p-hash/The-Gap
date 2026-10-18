"""
When in the day someone had alcohol. A day can have drinks at several times (1 pm, 5 pm and 8 pm), so the check-in's
alcohol_time holds one or more of morning, afternoon, evening and late, kept in the same text column as a comma
list in clock order ("afternoon,evening,late"). An older single value ("evening") is already a valid list of one.
"""

from __future__ import annotations

from typing import Optional

ORDER = ("morning", "afternoon", "evening", "late")


def clean(value) -> Optional[str]:
    """The known times in value (text like "evening" or "afternoon,evening", or a list), once each in clock order; None if none."""
    if value is None:
        return None
    parts = value if isinstance(value, (list, tuple, set)) else str(value).split(",")
    chosen = {str(p).strip().lower() for p in parts}
    kept = [t for t in ORDER if t in chosen]
    return ",".join(kept) if kept else None


def add(existing, bucket: str) -> Optional[str]:
    """The saved times with one more time of day included."""
    return clean([*(clean(existing) or "").split(","), bucket])

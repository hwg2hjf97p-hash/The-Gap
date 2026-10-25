"""
Sugar tracking: total sugars in a food, in grams.

Foods from the food databases already carry a sugar figure, so it is read and shown from the first day. Saving it with each logged
food needs a new column (phase27.sql), so writing it to the database is switched on with SUGAR_TRACKING=true on Render, once that
SQL has been run. Until then nothing here changes what is stored, and a food log works exactly as before.

A missing figure is never a zero. Plenty of foods (a takeaway, a recipe built by hand) have no sugar number, and saying "0 g" for
them would make a day look low in sugar when it is only unknown. A day only counts as having a sugar total when every food in it has one.
"""

from __future__ import annotations

import os
from typing import Optional

SUGAR = "sugar_g"


def tracking_on() -> bool:
    return os.getenv("SUGAR_TRACKING", "").strip().lower() in ("1", "true", "yes", "on")


def known(value) -> Optional[float]:
    """The sugar figure as a number, or None when there isn't one."""
    try:
        number = None if value is None else float(value)
    except (TypeError, ValueError):
        return None
    # An empty cell read into a table arrives as "not a number", which is just as unknown.
    return None if number is None or number != number else number


def add_scaled(row: dict, per: dict, factor: float) -> dict:
    """Adds `sugar_g` (the per-serving figure times `factor`) to a row about to be saved, when tracking is on and the figure is known."""
    value = known((per or {}).get(SUGAR))
    if tracking_on() and value is not None:
        row[SUGAR] = round(value * factor, 1)
    return row


def day_total(values: list) -> Optional[float]:
    """A day's sugar: the sum when every entry has a figure, otherwise None (unknown, not zero)."""
    figures = [known(v) for v in values]
    numbers = [v for v in figures if v is not None]
    if not figures or len(numbers) != len(figures):
        return None
    return round(sum(numbers), 1)

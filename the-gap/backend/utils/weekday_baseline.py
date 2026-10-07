"""
What's normal for THIS weekday, for this person.

Comparing today with "the last 7 days" or "the last 30 days" ignores that
people live different days differently: someone who sleeps in on Sundays and
has work on Mondays will always look like they "dropped" on a Monday. So a
reading is compared with the same weekday over the previous several weeks
whenever there are enough of them, and with the old overall comparison only
when there aren't.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Iterable, Optional

WEEKS_BACK = 8       # how far back to look for the same weekday
MIN_SAME_DAY = 4     # how many earlier same-weekday readings are needed to trust it


def weekday_baseline(points: Iterable[tuple[date, float]], target: date) -> Optional[dict]:
    """Typical value on `target`'s weekday, from the earlier readings on that
    weekday within the last WEEKS_BACK weeks. None if there are too few.

    points: (date, value) pairs. The target day itself and anything later are ignored.
    """
    same = [
        float(v)
        for d, v in points
        if d < target and d.weekday() == target.weekday() and (target - d).days <= WEEKS_BACK * 7
    ]
    if len(same) < MIN_SAME_DAY:
        return None
    mean = sum(same) / len(same)
    sd = math.sqrt(sum((v - mean) ** 2 for v in same) / (len(same) - 1)) if len(same) > 1 else 0.0
    return {"mean": mean, "sd": sd, "n": len(same), "weekday": target.strftime("%A")}

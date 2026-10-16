"""
Which findings moved most lately.

Each sync saves a fresh list of findings. Comparing today's list with the one from about a day earlier tells
the app which findings are new, got stronger or weaker, or shifted in size. The Insights tab leads with the few
that moved most. With no earlier list to compare against (a brand-new account), nothing has "moved" and the app
falls back to the strongest findings.

Adds two fields to each insight dict: movement (a number, 0 and up) and movement_label
("new", "stronger", "weaker", "shifted", "steady", or "" when there was nothing to compare with).
"""

from __future__ import annotations

import math
from typing import Optional

_TIER = {"strong": 2, "moderate": 1, "weak": 0}


def _tier(insight: dict) -> int:
    return _TIER.get(str(insight.get("confidence")), 0)


def _num(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number != number else number


def score(current: dict, previous: Optional[dict]) -> tuple[float, str]:
    """How much this finding moved since the earlier list. previous is None when it wasn't in that list."""
    if previous is None:
        return 100.0, "new"
    now_tier, then_tier = _tier(current), _tier(previous)
    if now_tier > then_tier:
        return 80.0 + 10.0 * (now_tier - then_tier), "new" if then_tier == 0 else "stronger"
    if now_tier < then_tier:
        return 40.0, "weaker"
    total = 0.0
    effect_now, effect_then = _num(current.get("ate")), _num(previous.get("ate"))
    if effect_now is not None and effect_then is not None:
        scale = max(abs(effect_then), 1e-9)
        total += min(abs(effect_now - effect_then) / scale, 1.0) * 40.0
    p_now, p_then = _num(current.get("p_value")), _num(previous.get("p_value"))
    if p_now is not None and p_then is not None:
        total += min(abs(math.log10(p_now + 1e-6) - math.log10(p_then + 1e-6)), 2.0) / 2.0 * 20.0
    total = round(total, 1)
    return total, "shifted" if total >= 15.0 else "steady"


def add_movement(current: list[dict], earlier: Optional[list[dict]]) -> None:
    """Fill in movement and movement_label on each of today's insights, in place."""
    if earlier is None:
        for insight in current:
            insight["movement"] = 0.0
            insight["movement_label"] = ""
        return
    before = {i.get("hypothesis_id"): i for i in earlier if i.get("hypothesis_id")}
    for insight in current:
        # An early signal that was an early signal yesterday has not moved in any way worth showing.
        prev = before.get(insight.get("hypothesis_id"))
        value, label = score(insight, prev)
        if _tier(insight) == 0 and prev is not None and _tier(prev) == 0:
            value, label = 0.0, "steady"
        insight["movement"] = value
        insight["movement_label"] = label

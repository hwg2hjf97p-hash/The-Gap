"""
Does published research on groups of people point the same way as a person's own finding?

The app shows this beside a finding ("Research on groups of people points the same way as your data so far"), never
inside it: the person's own numbers are not adjusted by population data in any way, and a finding is never made to
look more certain because a study agrees. When the two disagree the app says so and says the person's own data comes
first, because people differ.

A study can only be compared when it has been marked by hand (in the research review page) with what it found:
`effect_metric` is the reading it speaks to (one of its metric tags) and `effect_direction` is "up" when more of the
thing studied went with a higher reading, "down" when it went with a lower one. A card about a supplement is never
compared: "this agrees with you" would read as a reason to take it.
"""

from __future__ import annotations

from typing import Optional

from utils.supplements import tags_for_finding

DIRECTIONS = ("up", "down")


def agreement(card: dict, treatment_col: str, outcome_col: str, ate: Optional[float]) -> Optional[str]:
    """"agrees", "differs", or None when the two can't be compared."""
    if card.get("is_supplement"):
        return None
    metric, direction = card.get("effect_metric"), card.get("effect_direction")
    if not metric or direction not in DIRECTIONS:
        return None
    if ate is None or ate == 0:
        return None
    treatment_tags, outcome_tags = tags_for_finding(treatment_col, outcome_col)
    if metric not in outcome_tags:
        return None  # the study speaks to a different reading than the one the finding moves
    if not (set(card.get("metric_tags") or []) & set(treatment_tags)):
        return None  # and it has to be about the same habit
    finding_direction = "up" if ate > 0 else "down"
    return "agrees" if finding_direction == direction else "differs"

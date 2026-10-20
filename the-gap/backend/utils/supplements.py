"""
Supplements, handled carefully.

The Gap never tells anyone to take a supplement, never gives a dose, and never says a supplement will
change their results. Three things are allowed, each worded as information:

  1. Research cards. Published studies on a supplement can sit beside a finding they relate to
     ("Related research"). Every one carries the general disclaimer plus a caution written for that
     particular supplement (below), and the app hides the study behind a tap so it is never read
     without seeing the caution first.
  2. The person's own log. Someone who already takes magnesium and says so in their check-in gets a
     finding that only describes their own days with and without it. It is never framed as a reason to
     start, stop or change anything (see causal/interpreter.py), and it never reaches a push, a share
     card, "today's one thing" or the improvement plan.
  3. The chat assistant may explain what published research says, but never recommends one.

Melatonin is prescription-only in most of Australia, so its research is not shown to people whose
time zone is Australian (the log still works for anyone who already takes it).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Supplement:
    key: str                      # the key stored in the check-in and used in the hypothesis column took_<key>
    label: str
    keywords: tuple[str, ...]     # how a research card is recognised as being about it
    note: str                     # the caution specific to this supplement
    loggable: bool = True         # offered in the check-in (only where the engine has something to compare)
    research_hidden_in_au: bool = False


SUPPLEMENTS: tuple[Supplement, ...] = (
    Supplement(
        "magnesium", "Magnesium", ("magnesium",),
        "Extra magnesium can upset the stomach, and people with kidney problems need a doctor's advice first. "
        "It can also affect how some medicines are absorbed, including some antibiotics and bone medicines.",
    ),
    Supplement(
        "melatonin", "Melatonin", ("melatonin",),
        "Melatonin is a hormone. Products vary a lot in strength, it can cause drowsiness the next day, and it can interact "
        "with medicines such as blood thinners and some diabetes and blood-pressure medicines. It isn't advised in pregnancy "
        "or for children without a doctor. In Australia it is generally available only on prescription.",
        research_hidden_in_au=True,
    ),
    Supplement(
        "ashwagandha", "Ashwagandha", ("ashwagandha", "withania"),
        "Ashwagandha has been linked to rare cases of liver injury and is generally advised against in pregnancy and "
        "breastfeeding. It may interact with thyroid, sedative and immune-suppressing medicines. Many of the studies are small and short.",
    ),
    Supplement(
        "omega3", "Omega-3 (fish oil)", ("omega-3", "omega 3", "fish oil"),
        "Omega-3 supplements can thin the blood slightly, so they may interact with blood thinners, and higher amounts can upset "
        "the stomach. Ask a doctor first if you have a bleeding condition or take blood thinners.",
    ),
    Supplement(
        "creatine", "Creatine", ("creatine",),
        "Creatine can raise a blood marker (creatinine) that doctors use to check the kidneys, so tell your doctor if you take it. "
        "It can also cause stomach upset, and it isn't suited to people with kidney disease.",
        loggable=False,
    ),
)

BY_KEY = {s.key: s for s in SUPPLEMENTS}
CHECKIN_KEYS: tuple[str, ...] = tuple(s.key for s in SUPPLEMENTS if s.loggable)

# The sentence the research seeder adds to every supplement card (utils/evidence_seed.py).
CARD_MARKER = "Supplements can interact with medicines"

SUPPLEMENT_DISCLAIMER = (
    "This is general information from published research. It is not medical advice and not a recommendation to take anything. "
    "Supplements can interact with medicines and aren't right for everyone. Talk to a doctor or pharmacist before starting, "
    "stopping or changing one."
)


def clean_log(value: Optional[str]) -> Optional[str]:
    """
    A check-in's supplements answer as stored: None when it wasn't asked, "" when the person said they took none,
    otherwise the known keys, comma separated, in a fixed order.
    """
    if value is None:
        return None
    wanted = {part.strip().lower() for part in str(value).split(",")}
    return ",".join(k for k in CHECKIN_KEYS if k in wanted)


def match(text: str) -> Optional[Supplement]:
    lowered = (text or "").lower()
    for supplement in SUPPLEMENTS:
        if any(word in lowered for word in supplement.keywords):
            return supplement
    return None


def _card_text(card: dict) -> str:
    return " ".join(str(card.get(k) or "") for k in ("title", "plain_summary", "finding"))


def decorate_card(card: dict) -> dict:
    """The card with `is_supplement` and, for a supplement, the caution written for that one."""
    found = match(_card_text(card))
    flagged = CARD_MARKER in (card.get("caution_notes") or "")
    out = {**card, "is_supplement": flagged}
    if flagged:
        out["supplement_name"] = found.label if found else None
        out["supplement_note"] = found.note if found else None
    return out


def hidden_where_the_person_is(card: dict, tz: Optional[str]) -> bool:
    """True for research the person shouldn't be shown where they are (melatonin in Australia)."""
    found = match(_card_text(card))
    return bool(found and found.research_hidden_in_au and (tz or "").startswith("Australia/"))


# ── which research speaks to a finding ───────────────────────────────────────

_OUTCOME_TAGS = {
    "sleep_total_min": ["sleep_total_min", "sleep_score"],
    "sleep_deep_min": ["sleep_deep_min", "sleep_score"],
    "hrv_next": ["hrv"],
    "hrv": ["hrv"],
    "resting_hr": ["resting_hr"],
    "resting_hr_next": ["resting_hr"],
    "steps": ["steps"],
}
_TREATMENT_TAGS = {
    "alcohol_flag": ["alcohol_drinks"],
    "alcohol_drinks": ["alcohol_drinks"],
    "afternoon_caffeine": ["afternoon_caffeine"],
    "caffeine_drinks": ["afternoon_caffeine"],
    "high_caffeine_flag": ["afternoon_caffeine"],
    "screen_hours": ["screen_hours"],
    "late_screen_flag": ["screen_hours"],
    "steps": ["steps"],
    "active_energy": ["active_energy"],
    "stress_score": ["stress_score"],
    "high_stress_flag": ["stress_score"],
    "stress_event": ["stress_score"],
    "conflict_event": ["stress_score"],
    "mindful_minutes": ["stress_score", "hrv"],
    "workout_completed_flag": ["workout_completed_flag"],
    "water_ml": ["water_ml"],
    "sleep_total_min": ["sleep_total_min"],
    "sleep_deviation": ["sleep_total_min"],
    "sleep_debt_min": ["sleep_total_min"],
}


def tags_for_finding(treatment_col: str, outcome_col: str) -> tuple[list[str], list[str]]:
    """(tags about what the finding is about, tags about what it affects), as research-card metric tags."""
    return list(_TREATMENT_TAGS.get(treatment_col, [])), list(_OUTCOME_TAGS.get(outcome_col, []))


def pick_related(cards: list[dict], treatment_tags: list[str], outcome_tags: list[str], limit: int = 3, max_supplements: int = 1) -> list[dict]:
    """
    Up to `limit` cards for a finding: everyday-habit research first (best match, then newest), then at most
    `max_supplements` supplement card. A card only qualifies by sharing a tag with what the finding is about.
    """
    wanted = set(treatment_tags) | set(outcome_tags)

    def score(card: dict) -> tuple:
        tags = set(card.get("metric_tags") or [])
        return (
            len(tags & set(treatment_tags)) * 2 + len(tags & set(outcome_tags)),
            1 if card.get("study_type") == "meta-analysis" else 0,
            card.get("year") or 0,
        )

    eligible = [c for c in cards if wanted & set(c.get("metric_tags") or [])]
    habits = sorted([c for c in eligible if not c.get("is_supplement")], key=score, reverse=True)
    supplements = sorted([c for c in eligible if c.get("is_supplement")], key=score, reverse=True)
    room = max(0, limit - min(max_supplements, len(supplements)))
    return habits[:room] + supplements[:max_supplements]

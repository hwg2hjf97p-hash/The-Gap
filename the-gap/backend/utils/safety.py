"""
A gentle safety net for what people write in the app.

If someone writes that they may harm themselves, or that they are in a very dark place, the app should not carry on as if it
were an ordinary note: it answers with care and the numbers of free services. This is plain phrase matching, run the moment a note
or a question arrives, so it works with no AI, no subscription and no allowance left. It is a light check, not a safety system:
it will miss some wording, and it will sometimes fire on a phrase that was not meant that way (which is why the notice is gentle and
can be dismissed). The words people write here are never stored by this module, and nothing is logged beyond the level.

Two levels:
  "crisis"   self-harm or suicide, or not wanting to be alive
  "concern"  hopelessness, feeling like a burden, panic, not coping
Everyday mood words ("stressed", "anxious", "low", "tired") are deliberately NOT matched: the app treats those as diary notes.
"""

from __future__ import annotations

import re
from typing import Optional

CRISIS = "crisis"
CONCERN = "concern"

# What the person is told. Numbers are the free, 24-hour Australian services (checked against official pages in October 2026).
CRISIS_MESSAGE = (
    "I'm really sorry you're going through this, and I'm glad you said something. You matter, and you don't have to carry it alone. "
    "If you might act on these thoughts, or you're in danger, please call 000 now. You can also call Lifeline on 13 11 14 any time, "
    "day or night, or text them on 0477 13 11 14. Talking to someone you trust, or your doctor, can help too. "
    "If you're outside Australia, findahelpline.com lists free lines by country."
)
CONCERN_MESSAGE = (
    "That sounds really heavy, and I'm glad you told me. I'm only an app and can't help the way a person can, but you don't have to go "
    "through it alone. Lifeline (13 11 14) and Beyond Blue (1300 22 4636) are there any time, day or night, and a doctor or someone you "
    "trust can help too. If you ever feel you might hurt yourself, call 000."
)
SPOKEN_SUPPORT = "If you're struggling, Lifeline is on 13 11 14, any time. If you're in danger, call 000."

# Things that mean the opposite when they follow one of these ("I don't want to die", "never wanted to hurt myself").
_NEGATIONS = ("don't ", "dont ", "do not ", "didn't ", "never ", "not ", "no longer ", "wouldn't ", "won't ", "would never ", "would not ", "can't see myself ")

_CRISIS = [
    r"\bsuicid(?:e|al)\b",
    r"\bkill(?:ing)? myself\b",
    r"\bend(?:ing)? my (?:own )?life\b",
    r"\btake my (?:own )?life\b",
    r"\bwant(?:ed|s)? to die\b",
    r"\bwish i (?:was|were) dead\b",
    r"\bwish i (?:would|could|can) (?:just )?(?:die|disappear|not wake up)\b",
    r"\b(?:don't|dont|do not|no longer) want to (?:be here|be alive|live|wake up|exist)\b",
    r"\bno reason to (?:live|go on|keep going)\b",
    r"\bnot worth living\b",
    r"\bbetter off (?:dead|without me)\b",
    r"\bend it all\b",
    r"\bself[- ]?harm(?:ing)?\b",
    r"\b(?:hurt|harm|hurting|harming) myself\b",
    r"\bcut(?:ting)? myself\b",
    r"\bthinking (?:about|of) (?:dying|ending it)\b",
]
_CONCERN = [
    r"\bhopeless\b",
    r"\bworthless\b",
    r"\bcan't cope\b",
    r"\bcant cope\b",
    r"\bcan't go on\b",
    r"\bcant go on\b",
    r"\bcan't do this (?:any ?more|anymore)\b",
    r"\bno point (?:in )?(?:anything|going on|trying|living)\b",
    r"\bgive up on (?:everything|life)\b",
    r"\bpanic attack\b",
    r"\bfeel(?:ing)? (?:so )?empty\b",
    r"\bnobody (?:cares|would notice|would miss me)\b",
    r"\b(?:a )?burden (?:to|on) (?:everyone|everybody|my family|them)\b",
    r"\bwant(?:ed|s)? to disappear\b",
    r"\bcompletely alone\b",
]

_CRISIS_RE = [re.compile(p) for p in _CRISIS]
_CONCERN_RE = [re.compile(p) for p in _CONCERN]
# Phrases that already contain their own "don't": no negation check for these.
_SELF_NEGATED = ("want to be here", "want to be alive", "want to live", "want to wake up", "want to exist", "reason to", "worth living", "better off")


def _normalise(text: str) -> str:
    return " ".join(text.lower().replace("’", "'").replace("‘", "'").split())


def _negated(text: str, start: int, matched: str) -> bool:
    if any(marker in matched for marker in _SELF_NEGATED):
        return False
    before = text[max(0, start - 18):start]
    return any(before.endswith(n) or before.rstrip().endswith(n.strip()) for n in _NEGATIONS)


def assess(text: Optional[str]) -> Optional[str]:
    """"crisis", "concern" or None for what someone wrote. Crisis wins when both are present."""
    if not text:
        return None
    t = _normalise(text)
    for pattern in _CRISIS_RE:
        for m in pattern.finditer(t):
            if not _negated(t, m.start(), m.group(0)):
                return CRISIS
    for pattern in _CONCERN_RE:
        for m in pattern.finditer(t):
            if not _negated(t, m.start(), m.group(0)):
                return CONCERN
    return None


def message_for(level: str) -> str:
    return CRISIS_MESSAGE if level == CRISIS else CONCERN_MESSAGE

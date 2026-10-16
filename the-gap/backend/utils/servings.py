"""
A serving a person would recognise ("1 medium banana, 118 g") instead of "100 g".

Food databases store nutrition per 100 g, and many generic foods arrive with no serving at all, so the app showed
"100 g" for a banana or a slice of bread. Two ways to do better, tried in order:
  1. the household measures the database itself gives for the food (USDA foodMeasures / foodPortions)
  2. a short list of everyday foods with a typical serving (used only for plain, unprocessed matches)
Anything else stays at 100 g, which is honest rather than a guess.
"""

from __future__ import annotations

from typing import Optional

# Plain foods, matched on the first part of the name ("Bananas, raw" -> "bananas"). Typical Australian servings.
_COMMON = {
    "banana": ("1 medium", 118), "apple": ("1 medium", 182), "orange": ("1 medium", 131), "pear": ("1 medium", 178),
    "mandarin": ("1 medium", 88), "kiwifruit": ("1 medium", 69), "peach": ("1 medium", 150), "plum": ("1 medium", 66),
    "grapes": ("1 cup", 151), "strawberries": ("1 cup", 152), "blueberries": ("1 cup", 148), "avocado": ("1/2 medium", 100),
    "egg": ("1 large egg", 50), "eggs": ("1 large egg", 50), "potato": ("1 medium", 173), "sweet potato": ("1 medium", 130),
    "carrot": ("1 medium", 61), "tomato": ("1 medium", 123), "cucumber": ("1/2 medium", 150), "broccoli": ("1 cup", 91),
    "bread": ("1 slice", 32), "white bread": ("1 slice", 32), "wholemeal bread": ("1 slice", 35), "toast": ("1 slice", 32),
    "milk": ("1 cup", 258), "whole milk": ("1 cup", 258), "skim milk": ("1 cup", 258),
    "yoghurt": ("1 tub", 170), "yogurt": ("1 tub", 170), "cheese": ("1 slice", 20), "butter": ("1 tablespoon", 14),
    "rice": ("1 cup cooked", 158), "white rice": ("1 cup cooked", 158), "brown rice": ("1 cup cooked", 195),
    "pasta": ("1 cup cooked", 140), "oats": ("1/2 cup", 40), "rolled oats": ("1/2 cup", 40), "almonds": ("1 handful", 28),
    "peanut butter": ("1 tablespoon", 16), "olive oil": ("1 tablespoon", 14), "honey": ("1 tablespoon", 21),
    "chicken breast": ("1 breast", 172), "salmon": ("1 fillet", 154), "tuna": ("1 can", 95),
}

_SKIP_TEXT = ("quantity not specified", "100 g", "1 g", "10 g")


def default_serving(name: str) -> Optional[tuple[str, float]]:
    """A typical serving for a plain everyday food, or None."""
    text = (name or "").strip().lower()
    if not text:
        return None
    first, _, rest = text.partition(",")
    first = first.strip()
    if first not in _COMMON:
        return None
    # "Bananas, raw" or just "Banana" are plain; "Banana, with skin, dehydrated" is not.
    rest = rest.strip()
    if rest and rest not in ("raw", "fresh", "whole", "cooked", "boiled", "plain"):
        return None
    label, grams = _COMMON[first]
    return f"{label} ({round(grams)} g)", float(grams)


def portion_from_measures(measures: Optional[list[dict]]) -> Optional[tuple[str, float]]:
    """The first sensible household measure a database gives for a food, as (label, grams)."""
    for m in measures or []:
        grams = m.get("gramWeight")
        try:
            grams = float(grams)
        except (TypeError, ValueError):
            continue
        if not (5 <= grams <= 600):
            continue
        text = (m.get("disseminationText") or m.get("portionDescription") or "").strip()
        if not text:
            amount, modifier = m.get("amount"), (m.get("modifier") or (m.get("measureUnit") or {}).get("name") or "").strip()
            if amount and modifier and modifier.lower() != "undetermined":
                text = f"{float(amount):g} {modifier}"
        if not text or text.lower() in _SKIP_TEXT:
            continue
        return f"{text} ({round(grams)} g)", grams
    return None

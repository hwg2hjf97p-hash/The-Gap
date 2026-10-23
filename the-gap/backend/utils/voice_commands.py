"""
"Your voice, your command": a person's own spoken shortcuts, like saying "big bottle" to log 750 ml of water.

The shortcut is just words the person picks and one thing they choose to log. Matching them is in utils/log_router.py
(apply_custom), so Siri, the Shortcuts action and Quick Entry all understand them the same way. This file holds the rules for
what a shortcut may be, the list of what already works, and loading a person's shortcuts. It does not use AI.

Table DDL: see phase25.sql (voice_commands).
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import httpx

from utils.log_router import MAX_WATER_ML, _norm
from utils.saved_logging import _sb_headers, _sb_url

logger = logging.getLogger(__name__)

KINDS = {
    "water": "Water",
    "caffeine": "A coffee or caffeinated drink",
    "alcohol": "An alcoholic drink",
    "energy_drink": "An energy drink",
    "cigarettes": "A cigarette",
    "saved_food": "A saved food",
    "saved_meal": "A saved meal",
}
SAVED_KINDS = ("saved_food", "saved_meal")

MAX_COMMANDS = 30
MIN_PHRASE_CHARS, MAX_PHRASE_CHARS, MAX_PHRASE_WORDS = 2, 40, 6
MIN_WATER_ML = 50
COUNT_MAX = 10
SERVINGS_MIN, SERVINGS_MAX = 0.25, 20.0

# Words that on their own would catch almost any sentence.
STOP_WORDS = {"a", "an", "the", "and", "or", "i", "my", "me", "of", "to", "it", "is", "was", "had", "have", "just", "some", "one", "two", "three"}

# What already works with no setup, shown in the app so people can see how to talk to it.
EXAMPLES = [
    {"say": "a glass of water", "logs": "250 ml of water (a cup is 250 ml, a bottle 500 ml)"},
    {"say": "just had some water", "logs": "250 ml of water, one glass"},
    {"say": "500 ml of water", "logs": "500 ml of water"},
    {"say": "two bottles of water", "logs": "1,000 ml of water"},
    {"say": "a flat white", "logs": "1 coffee (also latte, espresso, cappuccino and more)"},
    {"say": "two beers", "logs": "2 alcoholic drinks"},
    {"say": "an energy drink", "logs": "1 energy drink"},
    {"say": "just had a smoke", "logs": "1 cigarette"},
    {"say": "I weigh 72.4 kg", "logs": "your weight, 72.4 kg"},
    {"say": "my usual protein shake", "logs": "your saved food or meal with that name, if you've saved one"},
    {"say": "had a burger", "logs": "a note to finish logging in the app, if it isn't a saved food"},
]


class Problem(ValueError):
    """A reason a shortcut can't be saved, in words for the person."""


def clean_phrase(raw: str) -> str:
    """The phrase as it will be matched: lower case, plain words only. Raises Problem if it can't be used."""
    phrase = _norm(raw)
    if not re.fullmatch(r"[a-z0-9' ]+", phrase or ""):
        raise Problem("Use plain words and numbers only, with no punctuation.")
    if len(phrase) < MIN_PHRASE_CHARS or len(phrase) > MAX_PHRASE_CHARS:
        raise Problem(f"Keep the phrase between {MIN_PHRASE_CHARS} and {MAX_PHRASE_CHARS} letters.")
    words = phrase.split(" ")
    if len(words) > MAX_PHRASE_WORDS:
        raise Problem(f"Keep the phrase to {MAX_PHRASE_WORDS} words or fewer.")
    if all(w in STOP_WORDS or w.isdigit() for w in words):
        raise Problem("That phrase is too common. It would catch ordinary sentences. Make it more specific.")
    return phrase


def check_command(kind: str, amount: float, ref_id: Optional[str], saved_foods: list[dict], saved_meals: list[dict]) -> dict:
    """The kind, amount and saved item cleaned and checked. Raises Problem. Returns the fields to store."""
    if kind not in KINDS:
        raise Problem("Pick what it should log.")
    if kind == "water":
        if not (MIN_WATER_ML <= amount <= MAX_WATER_ML):
            raise Problem(f"Water can be {MIN_WATER_ML} to {MAX_WATER_ML:,} ml.")
        return {"kind": kind, "amount": round(amount), "ref_id": None, "ref_name": None}
    if kind in SAVED_KINDS:
        if not (SERVINGS_MIN <= amount <= SERVINGS_MAX):
            raise Problem("Servings can be from a quarter up to 20.")
        items = saved_foods if kind == "saved_food" else saved_meals
        item = next((i for i in items if ref_id and str(i.get("id")) == ref_id), None)
        if not item:
            raise Problem("Pick one of your saved " + ("foods." if kind == "saved_food" else "meals."))
        return {"kind": kind, "amount": round(amount * 4) / 4, "ref_id": str(item["id"]), "ref_name": str(item.get("name") or "")[:80]}
    if not (1 <= amount <= COUNT_MAX) or amount != int(amount):
        raise Problem(f"Pick a number from 1 to {COUNT_MAX}.")
    return {"kind": kind, "amount": int(amount), "ref_id": None, "ref_name": None}


def describe(cmd: dict) -> str:
    """What a shortcut logs, in words."""
    kind, amount = cmd.get("kind"), float(cmd.get("amount") or 1)
    count = int(amount) if amount == int(amount) else amount
    if kind == "water":
        return f"{count:,} ml of water"
    if kind in SAVED_KINDS:
        name = cmd.get("ref_name") or ("a saved food" if kind == "saved_food" else "a saved meal")
        return name if amount == 1 else f"{count:g} × {name}"
    nouns = {"caffeine": ("coffee", "coffees"), "alcohol": ("alcoholic drink", "alcoholic drinks"), "energy_drink": ("energy drink", "energy drinks"), "cigarettes": ("cigarette", "cigarettes")}
    one, many = nouns.get(str(kind), ("item", "items"))
    return f"1 {one}" if count == 1 else f"{count} {many}"


async def load_commands(client: httpx.AsyncClient, user_id: str, strict: bool = False) -> list[dict]:
    """A person's shortcuts. Logging must never fail because of them, so unless `strict` any problem (the table isn't there yet) is an empty list."""
    try:
        resp = await client.get(
            _sb_url("voice_commands"),
            headers=_sb_headers(),
            params={"user_id": f"eq.{user_id}", "select": "id,phrase,kind,amount,ref_id,ref_name", "order": "created_at.asc", "limit": str(MAX_COMMANDS + 5)},
        )
        resp.raise_for_status()
        return list(resp.json() or [])
    except Exception as exc:
        if strict:
            raise
        logger.info("Loading voice commands failed (continuing without them): %s", exc)
        return []

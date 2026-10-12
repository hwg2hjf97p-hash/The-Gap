"""
Working out where a sentence belongs: "just drank 300ml of water", "just had a
cigarette", "had my usual brekky", "boss just yelled at me".

Used for anything the person says or types as a quick log (Quick Entry now,
Siri and Shortcuts later), so every doorway sorts things the same way.

This is plain word and number matching, on purpose. It is predictable, needs no
AI (so nothing about the person leaves the server), and the spoken answer can
say exactly what was logged. A sentence it doesn't recognise is kept as a note,
and every sentence is also saved as a note whatever else is done with it, so
nothing is lost if it guesses wrong.

parse_log() is pure (no database); applying the result is in routers/log.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "couple": 2, "half": 0.5,
}
QTY = r"(?P<qty>\d+(?:\.\d+)?|a|an|one|two|three|four|five|six|seven|eight|nine|ten|half(?:\s+a)?)"

GLASS_ML, CUP_ML, BOTTLE_ML = 250, 250, 500
MAX_WATER_ML = 3000


@dataclass
class Action:
    kind: str                       # water | cigarettes | alcohol | caffeine | energy_drink | weight | saved_food | saved_meal | food_note
    amount: float = 0.0             # ml, count, or kg
    label: str = ""                 # what was understood, in words
    ref_id: Optional[str] = None    # saved food / meal id
    servings: float = 1.0
    detail: str = ""


@dataclass
class Parsed:
    actions: list[Action] = field(default_factory=list)
    unsure: list[str] = field(default_factory=list)   # things noticed but not understood well enough to log


def _norm(text: str) -> str:
    t = (text or "").lower().replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", t).strip()


def _num(word: str) -> float:
    word = word.strip().lower()
    if word.startswith("half"):
        return 0.5
    if word in NUMBER_WORDS:
        return float(NUMBER_WORDS[word])
    try:
        return float(word)
    except ValueError:
        return 1.0


def time_bucket(hour: float) -> str:
    """The check-in's time-of-day words for a clock hour."""
    if hour < 12:
        return "morning" if hour >= 4 else "late"
    if hour < 17:
        return "afternoon"
    if hour < 22:
        return "evening"
    return "late"


def guess_meal(hour: float) -> str:
    if 4 <= hour < 10.5:
        return "breakfast"
    if 10.5 <= hour < 15:
        return "lunch"
    if 17 <= hour < 22:
        return "dinner"
    return "snack"


# ── saved foods and meals ────────────────────────────────────────────────────

# Words dropped from a saved name before matching ("my regular protein drink" is the saved "protein drink").
NAME_FILLER = {"my", "the", "a", "an", "some", "usual", "regular", "normal", "standard", "typical", "favourite", "favorite"}
# Words that sit between a number and what it counts ("two of my protein drinks").
QUANTITY_GAP = {"my", "the", "usual", "regular", "of", "a", "an", "some"}


def _stem(token: str) -> str:
    return token[:-1] if len(token) > 3 and token.endswith("s") and not token.endswith("ss") else token


def _tokens(text: str) -> list[str]:
    return [_stem(t) for t in re.findall(r"[a-z0-9']+", _norm(text))]


def _name_tokens(text: str) -> list[str]:
    return [t for t in _tokens(text) if t not in NAME_FILLER]


def _quantity_before(text_tokens: list[str], first_index: int) -> float:
    """"two protein drinks" -> 2. Looks back a few words for a number."""
    for back in range(1, 4):
        i = first_index - back
        if i < 0:
            break
        word = text_tokens[i]
        if re.fullmatch(r"\d+(?:\.\d+)?", word) or word in NUMBER_WORDS or word == "half":
            return max(0.25, min(20.0, _num(word)))
        if word not in QUANTITY_GAP:
            break
    return 1.0


def match_saved(text: str, items: list[dict]) -> Optional[tuple[dict, float]]:
    """
    The saved food or meal the sentence refers to, with how many servings, or None.
    A saved item matches when every word of its name (or one of its aliases)
    appears in the sentence; the most specific name wins, then the most used.
    """
    text_tokens = _tokens(text)
    wanted = set(text_tokens)
    best: Optional[tuple[tuple[int, int], dict, str]] = None
    for item in items:
        for name in [item.get("name", "")] + list(item.get("aliases") or []):
            name_tokens = _name_tokens(name)
            if not name_tokens or not all(t in wanted for t in name_tokens):
                continue
            score = (len(name_tokens), int(item.get("use_count") or 0))
            if best is None or score > best[0]:
                best = (score, item, name_tokens[0])
    if best is None:
        return None
    first = text_tokens.index(best[2]) if best[2] in text_tokens else 0
    return best[1], _quantity_before(text_tokens, first)


# ── drinks, smokes and weight ────────────────────────────────────────────────

WATER_UNIT = re.compile(rf"\b{QTY}\s*(?P<unit>ml|millilit(?:re|er)s?|l|lit(?:re|er)s?|glass(?:es)?|bottles?|cups?)\b")
CIGARETTE = re.compile(rf"(?:\b{QTY}\s+)?\b(?:cigarettes?|ciggies|ciggy|cigs?|durries|durrie|rollies|rollie)\b")
SMOKE_VERB = re.compile(r"\b(?:had|having|just had|grabbed|bummed|lit)\s+(?:a|an|another|one)\s+smoke\b|\bjust smoked\b|\bsmoked\s+(?:a|an|one|two|three|\d+)\s+(?:cigarettes?|ciggies|cigs?)\b")
SMOKED_FOOD = re.compile(r"\bsmoked\s+(?:salmon|ham|bacon|meat|chicken|fish|cheese|paprika|sausage|trout|turkey|brisket|ribs)\b")
ALCOHOL_NOUN = r"(?:beers?|wines?|ciders?|pints?|schooners?|middies|stubbies|tinnies|shots?|cocktails?|whisky|whiskey|vodka|gin|rum|bourbon|tequila|spirits|champagne|prosecco|margaritas?|mimosas?)"
# "a pint of milk" and "a shot of espresso" are not drinks of alcohol.
ALCOHOL = re.compile(
    rf"(?:\b{QTY}\s+(?:(?:glass(?:es)?|pints?|schooners?|cans?|bottles?)\s+of\s+)?)?\b{ALCOHOL_NOUN}\b(?!\s+of\s+(?:milk|water|juice|cola|coke|soda|ice cream|espresso|coffee))"
)
NOT_ALCOHOL = re.compile(r"\b(?:root beer|ginger beer|non[- ]?alcoholic|alcohol[- ]free|zero alcohol|0%)\b")
COFFEE = re.compile(
    rf"(?:\b{QTY}\s+)?\b(?:coffees?|espressos?|flat whites?|lattes?|cappuccinos?|long blacks?|americanos?|macchiatos?|cold brews?|mochas?|cortados?)\b"
)
ENERGY = re.compile(rf"(?:\b{QTY}\s+)?\b(?:energy drinks?|red bulls?|monsters?|v energy|celsius)\b")
WEIGHT = re.compile(r"\b(?:i\s+)?(?:weigh(?:ed)?(?:\s+in)?(?:\s+at)?|my weight is|weight is|i'm|i am)\s*(?P<n>\d{2,3}(?:\.\d{1,2})?)\s*(?P<u>kg|kgs|kilos?|kilograms?|lbs?|pounds?)\b")

FOOD_WORDS = {
    "egg", "eggs", "toast", "bacon", "bread", "rice", "pasta", "noodles", "chicken", "beef", "steak", "pork", "lamb",
    "fish", "salmon", "tuna", "burger", "pizza", "salad", "apple", "banana", "orange", "berries", "yogurt", "yoghurt",
    "cereal", "oats", "porridge", "muesli", "granola", "sandwich", "sandwiches", "wrap", "sushi", "soup", "chips", "fries",
    "chocolate", "biscuit", "biscuits", "cookie", "cookies", "cake", "ice cream", "cheese", "milk", "smoothie",
    "shake", "protein bar", "bar", "muffin", "pie", "sausage", "sausages", "curry", "stir fry", "tacos", "taco",
    "burrito", "potato", "potatoes", "veggies", "vegetables", "fruit", "nuts", "almonds", "peanut butter", "avocado",
    "pancakes", "waffles", "croissant", "bagel", "crumpet", "tea", "juice", "cola", "coke", "soda", "lollies", "snack",
    "breakfast", "brekky", "brunch", "lunch", "dinner", "supper", "meal", "takeaway", "kebab", "lasagne", "lasagna",
}
FOOD_VERB = re.compile(r"\b(?:ate|eaten|eating|had|have|having|grabbed|snacked on|munched|devoured)\b|\bfor (?:breakfast|brekky|brunch|lunch|dinner|supper)\b")


def _qty(match: re.Match, default: float = 1.0) -> float:
    q = match.groupdict().get("qty")
    return default if not q else max(0.0, _num(q))


def parse_log(text: str, hour: float, saved_foods: Optional[list[dict]] = None, saved_meals: Optional[list[dict]] = None) -> Parsed:
    """The actions a sentence contains. `hour` is the local clock time (0-24) it was said."""
    t = _norm(text)
    out = Parsed()
    if not t:
        return out

    # Weight: "I weigh 72.4", "weighed in at 160 pounds"
    w = WEIGHT.search(t)
    if w:
        kg = float(w.group("n"))
        if w.group("u").startswith(("lb", "pound")):
            kg *= 0.45359237
        if 20 <= kg <= 400:
            out.actions.append(Action("weight", round(kg, 1), label=f"{round(kg, 1)} kg"))

    # Saved meals and foods first, so "my usual protein drink" is the saved food, not a guess
    saved_names: set[str] = set()
    meal_hit = match_saved(t, saved_meals or [])
    if meal_hit:
        meal, servings = meal_hit
        out.actions.append(Action("saved_meal", amount=servings, label=meal["name"], ref_id=meal["id"], servings=servings))
        saved_names |= set(_name_tokens(meal["name"]))
    food_hit = match_saved(t, saved_foods or [])
    if food_hit and not (meal_hit and set(_name_tokens(food_hit[0]["name"])) <= saved_names):
        food, servings = food_hit
        out.actions.append(Action("saved_food", amount=servings, label=food["name"], ref_id=food["id"], servings=servings))

    # Water
    if re.search(r"\b(?:water|hydrat\w*)\b", t):
        ml: Optional[float] = None
        m = WATER_UNIT.search(t)
        if m:
            n, unit = _num(m.group("qty")), m.group("unit")
            if unit.startswith(("ml", "milli")):
                ml = n
            elif unit == "l" or unit.startswith("lit"):
                ml = n * 1000
            elif unit.startswith("glass"):
                ml = n * GLASS_ML
            elif unit.startswith("bottle"):
                ml = n * BOTTLE_ML
            else:
                ml = n * CUP_ML
        elif re.search(r"\b(?:drank|drink|had|having|sipped|chugged|finished)\b", t):
            ml = GLASS_ML  # "had some water": one glass, said back so it can be corrected
        if ml is not None:
            if 0 < ml <= MAX_WATER_ML:
                out.actions.append(Action("water", round(ml), label=f"{round(ml)} ml of water"))
            else:
                out.unsure.append("water amount")

    # Cigarettes
    count = 0.0
    for m in CIGARETTE.finditer(t):
        count += _qty(m)
    if SMOKE_VERB.search(t) and not SMOKED_FOOD.search(t) and count == 0:
        count = 1.0
    if count > 0:
        out.actions.append(Action("cigarettes", min(count, 40), label="1 cigarette" if count == 1 else f"{int(count)} cigarettes"))

    # Alcohol
    if not NOT_ALCOHOL.search(t):
        drinks = 0.0
        bottle = bool(re.search(r"\bbottles? of (?:wine|champagne|prosecco|spirits|whisky|whiskey|vodka|gin|rum)\b", t))
        for m in ALCOHOL.finditer(t):
            drinks += _qty(m)
        if bottle:
            out.unsure.append("a bottle (how many drinks?)")
            drinks = 0.0
        if drinks > 0:
            out.actions.append(Action("alcohol", min(drinks, 40), label="1 alcoholic drink" if drinks == 1 else f"{int(drinks)} alcoholic drinks"))

    # Energy drinks and coffee (an energy drink is not also counted as a coffee)
    energy = sum(_qty(m) for m in ENERGY.finditer(t))
    if energy > 0:
        out.actions.append(Action("energy_drink", min(energy, 20), label="1 energy drink" if energy == 1 else f"{int(energy)} energy drinks"))
    if not re.search(r"\bdecaf\b", t):
        coffee = sum(_qty(m) for m in COFFEE.finditer(t))
        if coffee > 0:
            out.actions.append(Action("caffeine", min(coffee, 20), label="1 coffee" if coffee == 1 else f"{int(coffee)} coffees"))

    # Food nobody has saved: kept as a note to finish in the app, never guessed at
    recognised_food = any(a.kind in ("saved_food", "saved_meal") for a in out.actions)
    handled_drinks = any(a.kind in ("water", "alcohol", "caffeine", "energy_drink") for a in out.actions)
    if not recognised_food and FOOD_VERB.search(t):
        words = set(re.findall(r"[a-z]+", t)) | {" ".join(p) for p in zip(re.findall(r"[a-z]+", t), re.findall(r"[a-z]+", t)[1:])}
        if words & FOOD_WORDS and not (handled_drinks and not (words & (FOOD_WORDS - {"tea", "juice", "cola", "coke", "soda", "milk"}))):
            out.actions.append(Action("food_note", label=text.strip()))
    return out


# ── what Siri or the app says back ───────────────────────────────────────────

def spoken_summary(summaries: list[str], note_only: bool, unsure: list[str], food_note: bool) -> str:
    """A short sentence saying what was logged."""
    if summaries:
        sentence = "Logged " + " and ".join(summaries) + "."
    elif food_note:
        sentence = "I don't have that food saved, so I kept it as a note to log in the app."
    else:
        sentence = "Saved to your journal."
    if unsure and summaries:
        sentence += " I kept the rest as a note."
    elif unsure:
        sentence = "Saved to your journal. I wasn't sure about " + unsure[0] + "."
    return sentence

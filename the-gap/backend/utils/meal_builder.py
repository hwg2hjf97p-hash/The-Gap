"""
Building a meal from ingredients: a home-cooked spag bol with its oil and cheese, saved once and logged by the serve.

A saved meal (utils/saved_logging.py) is a list of foods that are all logged together, each at `servings` of its own serving
size. A home-made recipe makes several serves, so each ingredient is stored as its share of ONE serve (its amount divided by how
many serves the recipe makes). Logging the meal once is then one serve; twice is two. The ingredients as the person entered them
(amounts, units, serves) are kept alongside in `recipe`, so the meal can be opened and edited later.

Nothing here is looked up or guessed: the numbers are the ones on the foods the person picked.
"""

from __future__ import annotations

from typing import Optional

MACROS = ("calories", "protein_g", "carbs_g", "fat_g")
MAX_INGREDIENTS = 40
MAX_SERVES = 40
MAX_SERVING_UNITS = 200       # of a food's own serving, when the amount is in servings
MAX_KCAL_PER_SERVE = 10000


class BuildProblem(ValueError):
    """A reason a meal can't be saved, in words for the person."""


def ingredient_units(ing: dict) -> float:
    """How many of the food's own serving sizes an ingredient is, whichever way the person entered it."""
    name = str(ing.get("name") or "That ingredient")
    amount = float(ing.get("amount") or 0)
    if amount <= 0:
        raise BuildProblem(f"Give {name} an amount.")
    if ing.get("unit") == "g":
        grams = ing.get("serving_grams")
        if not grams or float(grams) <= 0:
            raise BuildProblem(f"{name} can't be measured in grams. Use servings for it.")
        return amount / float(grams)
    if amount > MAX_SERVING_UNITS:
        raise BuildProblem(f"{name}: that's a lot of servings. Check the amount.")
    return amount


def build_items(ingredients: list[dict], serves: float) -> list[dict]:
    """The saved meal's items: every ingredient as its share of one serve."""
    if not ingredients:
        raise BuildProblem("Add at least one ingredient.")
    if len(ingredients) > MAX_INGREDIENTS:
        raise BuildProblem(f"A meal can have up to {MAX_INGREDIENTS} ingredients.")
    if not (1 <= serves <= MAX_SERVES):
        raise BuildProblem(f"A meal makes between 1 and {MAX_SERVES} serves.")
    items = []
    for ing in ingredients:
        per = ing.get("per_serving") or {}
        items.append(
            {
                "food_name": str(ing.get("name") or "Food").strip()[:200],
                "brand": (str(ing.get("brand") or "").strip() or None),
                "servings": round(ingredient_units(ing) / serves, 4),
                "serving_label": ing.get("serving_label"),
                "serving_grams": ing.get("serving_grams"),
                "per_serving": {k: round(float(per.get(k) or 0), 3) for k in MACROS},
            }
        )
    return items


def per_serve_totals(items: list[dict]) -> dict:
    """The calories and macros of one serve."""
    return {k: round(sum(float((i.get("per_serving") or {}).get(k) or 0) * float(i.get("servings") or 1) for i in items), 1) for k in MACROS}


def check_serve_size(items: list[dict]) -> None:
    """Catches a mistyped amount (a kilo of oil) before it is saved."""
    if per_serve_totals(items)["calories"] > MAX_KCAL_PER_SERVE:
        raise BuildProblem("That's over 10,000 kcal in one serve. Check the amounts and how many serves it makes.")


def recipe_json(name: str, serves: float, cooked_weight_g: Optional[float], ingredients: list[dict]) -> dict:
    """What is needed to open the meal again for editing, exactly as the person entered it."""
    return {
        "serves": serves,
        "cooked_weight_g": cooked_weight_g,
        "ingredients": [
            {
                "name": str(i.get("name") or "")[:120],
                "brand": i.get("brand"),
                "serving_label": i.get("serving_label"),
                "serving_grams": i.get("serving_grams"),
                "per_serving": {k: float((i.get("per_serving") or {}).get(k) or 0) for k in MACROS},
                "amount": float(i.get("amount") or 0),
                "unit": "g" if i.get("unit") == "g" else "serving",
                "source": i.get("source"),
            }
            for i in ingredients
        ],
    }

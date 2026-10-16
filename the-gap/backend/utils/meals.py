"""
Everyday meals in the food search ("spaghetti bolognese", "butter chicken"), each with the nutrition published for one
serve on a named recipe page and a link to that recipe.

Only the dish name, the published per-serve numbers and the link are kept here. The ingredients and method stay on the
author's own page, and the app opens it from a "Recipe" button. The data is in data/meals/common_meals.json with its
source and collection date. Nothing is estimated by us.

This module also turns the person's own "ideas for this week" recipes (written for them by the AI, cached weekly) into
search results, so a recipe they were shown can be logged from the search box.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "meals" / "common_meals.json"


def _norm(text: str) -> str:
    text = (text or "").lower().replace("’", "'").replace("'", "")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


@lru_cache(maxsize=1)
def load_meals() -> tuple[dict, ...]:
    raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    by, base, collected = raw["by"], raw["base_url"], raw.get("collected", "")
    meals = []
    for name, aliases, kcal, protein, carbs, fat, serving, slug in raw["meals"]:
        meals.append({
            "source": "common_meal", "source_id": f"rte:{slug}", "name": name, "brand": by,
            "serving_label": serving, "serving_grams": None,
            "per_serving": {"calories": float(kcal), "protein_g": float(protein), "carbs_g": float(carbs), "fat_g": float(fat)},
            "recipe_url": f"{base}{slug}/", "recipe_source": by,
            "note": f"Nutrition per serve as published by {by}, collected {collected}. Your portion may differ.",
            "_names": [_norm(name)] + [_norm(a) for a in aliases],
        })
    return tuple(meals)


def _public(item: dict) -> dict:
    return {k: v for k, v in item.items() if not k.startswith("_")}


def _words_match(tokens: list[str], text: str) -> bool:
    words = text.split()
    return all(any(w.startswith(t) for w in words) for t in tokens)


def search(query: str, limit: int = 4) -> list[dict]:
    """Meals whose name (or a common spelling or nickname) matches every word typed, best match first."""
    q = _norm(query)
    tokens = q.split()
    if len(q) < 3 or not tokens:
        return []
    found: list[tuple[tuple, dict]] = []
    for meal in load_meals():
        hit = next((n for n in meal["_names"] if _words_match(tokens, n)), None)
        if hit is None:
            continue
        exact = 0 if q in meal["_names"] else 1
        found.append(((exact, len(meal["name"]), meal["name"]), meal))
    found.sort(key=lambda pair: pair[0])
    return [_public(m) for _, m in found[:limit]]


def from_week_recipes(recipes: list[dict], query: str, limit: int = 3) -> list[dict]:
    """The person's own recipe ideas for this week that match the search, as loggable items with their recipe attached."""
    tokens = _norm(query).split()
    if not tokens or len(_norm(query)) < 3:
        return []
    out = []
    for r in recipes or []:
        title = r.get("title") or ""
        est = r.get("estimate") or {}
        calories = est.get("calories")
        if not title or not calories or not _words_match(tokens, _norm(title)):
            continue
        servings = r.get("servings")
        out.append({
            "source": "recipe", "source_id": title, "name": title, "brand": "Your ideas this week",
            "serving_label": "1 serving (rough estimate)", "serving_grams": None,
            "per_serving": {"calories": float(calories), "protein_g": float(est.get("protein_g") or 0), "carbs_g": 0.0, "fat_g": 0.0},
            "note": "A rough estimate of calories and protein only; carbs and fat are not included.",
            "recipe": {
                "title": title, "summary": r.get("summary") or "", "time_min": r.get("time_min"),
                "servings": servings, "ingredients": r.get("ingredients") or [], "steps": r.get("steps") or [],
            },
        })
    return out[:limit]

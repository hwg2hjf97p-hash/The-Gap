"""
Takeaway and restaurant menu items, to log in one tap ("Quarter Pounder meal, large, with Coke").

Food databases (USDA, Open Food Facts) have few restaurant menu items, so these come from each chain's own
published nutrition information, kept in data/takeaway/<chain>_<country>.json with the source and the date
it was collected. Nothing here is guessed: an item whose published energy didn't agree with its published
protein, carbohydrate and fat was left out. Meals are worked out by adding up their parts.

Adding a chain = adding one more JSON file in the same shape.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "takeaway"
SIZE_ORDER = {"small": 0, "medium": 1, "large": 2}


def _norm(text: str) -> str:
    text = (text or "").lower().replace("’", "'").replace("é", "e")
    text = text.replace("'", "").replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _slug(text: str) -> str:
    return _norm(text).replace(" ", "-")


def _macros(row: list) -> dict:
    return {"calories": float(row[2]), "protein_g": float(row[3]), "carbs_g": float(row[4]), "fat_g": float(row[5])}


def _sum(parts: list[dict]) -> dict:
    return {k: round(sum(p[k] for p in parts), 1) for k in ("calories", "protein_g", "carbs_g", "fat_g")}


@lru_cache(maxsize=1)
def load_chains() -> tuple[dict, ...]:
    """Every chain file, with its items and generated meals as ready-to-use food items."""
    chains = []
    for path in sorted(DATA_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        name = raw["chain"]
        note = f"{name} nutrition information, collected {raw.get('collected', '')}"
        by_name: dict[str, dict] = {}
        items: list[dict] = []

        def make(item_name: str, per: dict, category: str, label: str, kind: str) -> dict:
            return {
                "source": "takeaway", "source_id": f"{_slug(name)}:{_slug(item_name)}", "name": item_name, "brand": name,
                "serving_label": label, "serving_grams": None, "per_serving": per,
                "category": category, "kind": kind, "note": note,
            }

        labels = raw.get("labels", {})
        for row in raw["items"]:
            item = make(row[1], _macros(row), row[0], labels.get(row[0], "1 serve"), "item")
            by_name[row[1]] = item
            items.append(item)

        meals: list[dict] = []
        spec = raw.get("meals")
        if spec:
            for main in spec["mains"]:
                if main not in by_name:
                    continue
                for size in spec["sizes"]:
                    side = by_name.get(spec["side"].format(size=size))
                    if not side:
                        continue
                    for drink_label, pattern in spec["drinks"]:
                        drink = by_name.get(pattern.format(size=size))
                        if not drink:
                            continue
                        per = _sum([by_name[main]["per_serving"], side["per_serving"], drink["per_serving"]])
                        meals.append(make(f"{main} Meal ({size}) with {drink_label}", per, "meals", "1 meal", "meal"))
        chains.append({
            "name": name, "aliases": [_norm(a) for a in raw.get("aliases", [])] + [_norm(name)],
            "country": raw.get("country"), "collected": raw.get("collected"), "source": raw.get("source"),
            "featured": raw.get("featured") or ["beef", "chicken"], "max_gap": raw.get("max_gap", 0.20),
            "items": items, "meals": meals,
        })
    return tuple(chains)


def _size_rank(item: dict) -> int:
    match = re.search(r"\((small|medium|large)\)", item["name"].lower())
    return SIZE_ORDER[match.group(1)] if match else 1


def _sort_key(item: dict, tokens: list[str]) -> tuple:
    """Exact name first; then the shortest dish name (the plain one before the Double), small to large, Coke before Coke Zero."""
    name = item["name"]
    dish = name.split(" Meal (")[0] if item["kind"] == "meal" else name
    return (0 if _norm(name) == " ".join(tokens) else 1, len(dish), _size_rank(item), name)


def _matches(tokens: list[str], name: str) -> bool:
    words = _norm(name).split()
    return all(any(w.startswith(t) for w in words) for t in tokens)


def search(query: str, limit: int = 8) -> list[dict]:
    """Menu items for a typed search: a chain's name (or a nickname like "maccas") with or without a dish, or just a dish."""
    q = _norm(query)
    if len(q) < 2:
        return []
    groups: list[list[dict]] = []
    for chain in load_chains():
        remaining = q
        chain_named = False
        for alias in sorted(chain["aliases"], key=len, reverse=True):
            if alias and re.search(rf"(^|\s){re.escape(alias)}(\s|$)", remaining):
                remaining = re.sub(rf"(^|\s){re.escape(alias)}(\s|$)", " ", remaining).strip()
                chain_named = True
                break
        tokens = remaining.split()
        if chain_named and not tokens:
            # Just the chain's name: show its main dishes first.
            featured = [i for i in chain["items"] if i["category"] in chain["featured"]] or chain["items"]
            groups.append(featured[: max(limit, 8)])
            continue
        if not tokens or (not chain_named and len(q) < 3):
            continue
        wants_meal = "meal" in tokens or "meals" in tokens
        pool = chain["meals"] if wants_meal else chain["items"]
        found = [i for i in pool if _matches(tokens, i["name"])]
        found.sort(key=lambda i: _sort_key(i, tokens))
        if found and not chain_named and not wants_meal:
            # A plain word like "chicken" matches every chain: take a few from each so the usual foods still show too.
            found = found[:3]
        groups.append(found)
    # One chain at a time when it was named; otherwise a fair mix across chains.
    out: list[dict] = []
    for rank in range(max((len(g) for g in groups), default=0)):
        out.extend(g[rank] for g in groups if rank < len(g))
    if len([g for g in groups if g]) > 1:
        return out[: min(limit, 6)]
    return [i for g in groups for i in g][:limit]


def chains_summary() -> list[dict]:
    return [{"name": c["name"], "items": len(c["items"]), "meals": len(c["meals"]), "collected": c["collected"]} for c in load_chains()]

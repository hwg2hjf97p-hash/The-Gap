"""
Logging a saved food or a saved meal ("my regulars") into the food log.

Saved foods and meals are copies of foods the person has logged before, so one
tap (or one sentence) logs the exact same thing again. The nutrition numbers
are the ones they saved; nothing is looked up or guessed.

Table DDL: see phase10.sql (saved_foods, saved_meals).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx

from utils.log_router import guess_meal

logger = logging.getLogger(__name__)

MACROS = ("calories", "protein_g", "carbs_g", "fat_g")
MAX_ENTRY_KCAL = 10000


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


def food_log_row(
    user_id: str,
    local_date: str,
    meal: str,
    item: dict,
    servings: float,
    local_hour: Optional[float],
    source: str,
) -> dict:
    """
    One food_log row from a saved item. `item` carries per-serving numbers either
    flat (saved_foods: calories, protein_g, ...) or under "per_serving" (items of a
    saved meal). Totals are worked out here, once, like routers/nutrition.log_food.
    """
    per = item.get("per_serving") or item
    totals = {k: round(float(per.get(k) or 0) * servings, 1) for k in MACROS}
    return {
        "user_id": user_id,
        "local_date": local_date,
        "meal": meal,
        "food_name": (item.get("food_name") or item.get("name") or "Food").strip()[:200],
        "brand": (item.get("brand") or "").strip() or None,
        "servings": round(servings, 3),
        "serving_label": item.get("serving_label"),
        "serving_grams": item.get("serving_grams"),
        "local_hour": None if local_hour is None else round(local_hour, 2),
        "source": source[:20],
        **totals,
    }


def saved_food_rows(user_id: str, food: dict, multiplier: float, local_date: str, local_hour: Optional[float], meal: Optional[str]) -> list[dict]:
    servings = float(food.get("default_servings") or 1) * multiplier
    row_meal = meal or food.get("default_meal") or guess_meal(local_hour if local_hour is not None else 12)
    return [food_log_row(user_id, local_date, row_meal, food, servings, local_hour, "saved")]


def saved_meal_rows(user_id: str, meal: dict, multiplier: float, local_date: str, local_hour: Optional[float], meal_override: Optional[str]) -> list[dict]:
    row_meal = meal_override or meal.get("meal") or guess_meal(local_hour if local_hour is not None else 12)
    rows = []
    for item in meal.get("items") or []:
        servings = float(item.get("servings") or 1) * multiplier
        rows.append(food_log_row(user_id, local_date, row_meal, item, servings, local_hour, "saved_meal"))
    return rows


def too_big(rows: list[dict]) -> bool:
    return any(r["calories"] > MAX_ENTRY_KCAL for r in rows)


async def insert_food_rows(client: httpx.AsyncClient, rows: list[dict]) -> list[dict]:
    """Saves the rows; returns what was saved (with ids, so they can be undone)."""
    if not rows:
        return []
    resp = await client.post(_sb_url("food_log"), headers=_sb_headers("return=representation"), json=rows)
    resp.raise_for_status()
    return resp.json() or []


async def bump_use(client: httpx.AsyncClient, table: str, user_id: str, item: dict) -> None:
    """Counts a use, so the most-used regulars come first and win a tie when matching by voice. Best effort."""
    try:
        resp = await client.patch(
            _sb_url(table),
            headers=_sb_headers("return=minimal"),
            params={"id": f"eq.{item['id']}", "user_id": f"eq.{user_id}"},
            json={"use_count": int(item.get("use_count") or 0) + 1, "last_used": datetime.now(timezone.utc).isoformat()},
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.info("Counting a saved-food use failed: %s", exc)


async def load_saved(client: httpx.AsyncClient, user_id: str) -> tuple[list[dict], list[dict]]:
    """(saved foods, saved meals) for matching and listing. Empty lists when the tables aren't there yet."""
    foods: list[dict] = []
    meals: list[dict] = []
    for table, target in (("saved_foods", foods), ("saved_meals", meals)):
        try:
            resp = await client.get(
                _sb_url(table),
                headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "select": "*", "order": "use_count.desc,last_used.desc.nullslast", "limit": "300"},
            )
            resp.raise_for_status()
            target.extend(resp.json() or [])
        except Exception as exc:
            logger.info("Loading %s failed (continuing without it): %s", table, exc)
    return foods, meals


def public_food(row: dict) -> dict:
    """A saved food in the same shape the app uses for any food, plus what makes it a saved one."""
    return {
        "source": "saved",
        "source_id": row["id"],
        "id": row["id"],
        "name": row["name"],
        "aliases": row.get("aliases") or [],
        "brand": row.get("brand"),
        "serving_label": row.get("serving_label") or "serving",
        "serving_grams": row.get("serving_grams"),
        "default_servings": float(row.get("default_servings") or 1),
        "per_serving": {k: float(row.get(k) or 0) for k in MACROS},
        "use_count": int(row.get("use_count") or 0),
    }


def public_meal(row: dict) -> dict:
    items = row.get("items") or []
    totals = {k: round(sum(float((i.get("per_serving") or {}).get(k) or 0) * float(i.get("servings") or 1) for i in items), 1) for k in MACROS}
    return {
        "id": row["id"],
        "name": row["name"],
        "aliases": row.get("aliases") or [],
        "meal": row.get("meal") or "snack",
        "items": [{"food_name": i.get("food_name"), "servings": i.get("servings"), "serving_label": i.get("serving_label")} for i in items],
        "totals": totals,
        "use_count": int(row.get("use_count") or 0),
        "recipe": row.get("recipe"),  # present for meals built from ingredients; lets the app reopen them for editing
    }

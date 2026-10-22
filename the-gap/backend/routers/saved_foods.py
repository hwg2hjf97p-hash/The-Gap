"""
"My regulars": foods and meals the person has saved so they can log them again in one tap or one sentence.

  GET    /nutrition/saved                  -> {"foods": [...], "meals": [...]}
  POST   /nutrition/saved/food             save a food (same numbers the person logged)
  POST   /nutrition/saved/meal-from-log    save the foods logged for a meal as one saved meal
  PATCH  /nutrition/saved/food/{id}        rename / change the alternative names
  PATCH  /nutrition/saved/meal/{id}
  DELETE /nutrition/saved/food/{id}
  DELETE /nutrition/saved/meal/{id}
  POST   /nutrition/saved/log              log a saved food or meal now

Table DDL: see phase10.sql.
"""

from __future__ import annotations

import logging
from datetime import date as date_type
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from auth import get_current_user_id
from routers.nutrition import PerServing
from utils.saved_logging import (
    _sb_headers,
    _sb_url,
    bump_use,
    insert_food_rows,
    load_saved,
    public_food,
    public_meal,
    saved_food_rows,
    saved_meal_rows,
    too_big,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/nutrition/saved", tags=["saved-foods"])

MEALS = ("breakfast", "lunch", "dinner", "snack")


def clean_aliases(aliases: list[str]) -> list[str]:
    out: list[str] = []
    for a in aliases:
        a = " ".join((a or "").split())[:40]
        if a and a.lower() not in {x.lower() for x in out}:
            out.append(a)
    return out[:8]


class SavedFoodBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    aliases: list[str] = Field(default_factory=list, max_length=8)
    brand: Optional[str] = Field(default=None, max_length=200)
    serving_label: Optional[str] = Field(default=None, max_length=100)
    serving_grams: Optional[float] = Field(default=None, gt=0, le=5000)
    per_serving: PerServing
    default_servings: float = Field(default=1, gt=0, le=20)
    default_meal: Optional[Literal["breakfast", "lunch", "dinner", "snack"]] = None


class MealFromLogBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    entry_ids: list[str] = Field(min_length=1, max_length=40)
    aliases: list[str] = Field(default_factory=list, max_length=8)
    meal: Optional[Literal["breakfast", "lunch", "dinner", "snack"]] = None


class RenameBody(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    aliases: Optional[list[str]] = Field(default=None, max_length=8)


class LogSavedBody(BaseModel):
    kind: Literal["food", "meal"]
    id: str
    local_date: str
    local_hour: Optional[float] = Field(default=None, ge=0, lt=24)
    meal: Optional[Literal["breakfast", "lunch", "dinner", "snack"]] = None
    servings: float = Field(default=1, gt=0, le=20)


def _check_date(value: str) -> None:
    try:
        date_type.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="local_date must be YYYY-MM-DD.")


def _duplicate(exc: Exception) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 409


@router.get("")
async def list_saved(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    async with httpx.AsyncClient(timeout=15) as client:
        foods, meals = await load_saved(client, user_id)
    return JSONResponse(content={"foods": [public_food(f) for f in foods], "meals": [public_meal(m) for m in meals]})


@router.post("/food")
async def save_food(body: SavedFoodBody, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    row = {
        "user_id": user_id,
        "name": body.name.strip(),
        "aliases": clean_aliases(body.aliases),
        "brand": (body.brand or "").strip() or None,
        "serving_label": body.serving_label,
        "serving_grams": body.serving_grams,
        "calories": body.per_serving.calories,
        "protein_g": body.per_serving.protein_g,
        "carbs_g": body.per_serving.carbs_g,
        "fat_g": body.per_serving.fat_g,
        "default_servings": body.default_servings,
        "default_meal": body.default_meal,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(_sb_url("saved_foods"), headers=_sb_headers("return=representation"), json=row)
            resp.raise_for_status()
            saved = (resp.json() or [None])[0]
    except Exception as exc:
        if _duplicate(exc):
            raise HTTPException(status_code=409, detail=f"You already have a saved food called \"{body.name.strip()}\".")
        logger.error("Saving a food failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Couldn't save that. Please try again.")
    return JSONResponse(content={"food": public_food(saved) if saved else None})


@router.post("/meal-from-log")
async def save_meal_from_log(body: MealFromLogBody, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                _sb_url("food_log"),
                headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "id": f"in.({','.join(body.entry_ids)})", "select": "*"},
            )
            resp.raise_for_status()
            entries = resp.json() or []
            if not entries:
                raise HTTPException(status_code=404, detail="Those entries weren't found.")
            items = []
            for e in entries:
                servings = float(e.get("servings") or 1) or 1.0
                items.append(
                    {
                        "food_name": e["food_name"],
                        "brand": e.get("brand"),
                        "servings": servings,
                        "serving_label": e.get("serving_label"),
                        "serving_grams": e.get("serving_grams"),
                        # The log keeps totals; a saved meal keeps what one serving is.
                        "per_serving": {k: round(float(e.get(k) or 0) / servings, 3) for k in ("calories", "protein_g", "carbs_g", "fat_g")},
                    }
                )
            meal_name = body.meal or entries[0].get("meal") or "snack"
            row = {"user_id": user_id, "name": body.name.strip(), "aliases": clean_aliases(body.aliases), "meal": meal_name, "items": items}
            created = await client.post(_sb_url("saved_meals"), headers=_sb_headers("return=representation"), json=row)
            created.raise_for_status()
            saved = (created.json() or [None])[0]
    except HTTPException:
        raise
    except Exception as exc:
        if _duplicate(exc):
            raise HTTPException(status_code=409, detail=f"You already have a saved meal called \"{body.name.strip()}\".")
        logger.error("Saving a meal failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Couldn't save that. Please try again.")
    return JSONResponse(content={"meal": public_meal(saved) if saved else None})


async def _rename(table: str, item_id: str, user_id: str, body: RenameBody) -> JSONResponse:
    changes: dict = {}
    if body.name is not None:
        changes["name"] = body.name.strip()
    if body.aliases is not None:
        changes["aliases"] = clean_aliases(body.aliases)
    if not changes:
        return JSONResponse(content={"success": True})
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.patch(_sb_url(table), headers=_sb_headers("return=minimal"), params={"id": f"eq.{item_id}", "user_id": f"eq.{user_id}"}, json=changes)
            resp.raise_for_status()
    except Exception as exc:
        if _duplicate(exc):
            raise HTTPException(status_code=409, detail="You already have one with that name.")
        logger.error("Renaming a saved item failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Couldn't save that. Please try again.")
    return JSONResponse(content={"success": True})


@router.patch("/food/{item_id}")
async def rename_food(item_id: str, body: RenameBody, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    return await _rename("saved_foods", item_id, user_id, body)


@router.patch("/meal/{item_id}")
async def rename_meal(item_id: str, body: RenameBody, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    return await _rename("saved_meals", item_id, user_id, body)


async def _delete(table: str, item_id: str, user_id: str) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.delete(_sb_url(table), headers=_sb_headers("return=minimal"), params={"id": f"eq.{item_id}", "user_id": f"eq.{user_id}"})
            resp.raise_for_status()
    except Exception as exc:
        logger.error("Deleting a saved item failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Couldn't remove that.")
    return JSONResponse(content={"success": True})


@router.delete("/food/{item_id}")
async def delete_food(item_id: str, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    return await _delete("saved_foods", item_id, user_id)


@router.delete("/meal/{item_id}")
async def delete_meal(item_id: str, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    return await _delete("saved_meals", item_id, user_id)


@router.post("/log")
async def log_saved(body: LogSavedBody, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    _check_date(body.local_date)
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            foods, meals = await load_saved(client, user_id)
            if body.kind == "food":
                item = next((f for f in foods if f["id"] == body.id), None)
                table = "saved_foods"
                rows = saved_food_rows(user_id, item, body.servings, body.local_date, body.local_hour, body.meal) if item else []
            else:
                item = next((m for m in meals if m["id"] == body.id), None)
                table = "saved_meals"
                rows = saved_meal_rows(user_id, item, body.servings, body.local_date, body.local_hour, body.meal) if item else []
            if not item or not rows:
                raise HTTPException(status_code=404, detail="That saved item wasn't found.")
            if too_big(rows):
                raise HTTPException(status_code=400, detail="That's more than 10,000 kcal in one entry. Check the amount.")
            saved = await insert_food_rows(client, rows)
            await bump_use(client, table, user_id, item)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Logging a saved item failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Couldn't log that. Please try again.")
    return JSONResponse(content={"logged": len(saved), "name": item["name"], "ids": [r["id"] for r in saved if isinstance(r, dict) and r.get("id")]})

"""
Nutrition — food logging, water tracking and daily goals for the "Your
Health" tab, all feeding the causal engine.

We deliberately don't integrate a calorie-counting app (MyFitnessPal's API
is closed to new developers): this is our own logging UI on top of free
food databases.
  - Text search: USDA FoodData Central (generic + branded foods). Needs
    USDA_API_KEY (free, instant at https://fdc.nal.usda.gov/api-key-signup);
    falls back to the shared DEMO_KEY, which is heavily rate-limited and
    only fit for development.
  - Barcodes: Open Food Facts (global, free, no key), falling back to USDA's
    branded database (UPC). OFF's *text* search is unreliable (frequent
    503s), so it's only a best-effort extra source for search.

Logged food/water flows into the engine through get_nutrition_dataframe(),
which uses the same column names Apple Health nutrition already uses
(dietary_energy, protein_g, ...) so in-app logs take precedence on days
that have them, plus water_ml and last_meal_hour for new hypotheses.

Table DDL (run once in Supabase SQL editor):
  CREATE TABLE IF NOT EXISTS food_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    local_date DATE NOT NULL,
    meal TEXT NOT NULL,
    food_name TEXT NOT NULL,
    brand TEXT,
    servings NUMERIC NOT NULL DEFAULT 1,
    serving_label TEXT,
    serving_grams NUMERIC,
    calories NUMERIC NOT NULL,
    protein_g NUMERIC NOT NULL DEFAULT 0,
    carbs_g NUMERIC NOT NULL DEFAULT 0,
    fat_g NUMERIC NOT NULL DEFAULT 0,
    local_hour NUMERIC,
    source TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
  );
  CREATE INDEX IF NOT EXISTS idx_food_log_user_date ON food_log (user_id, local_date);

  CREATE TABLE IF NOT EXISTS water_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    local_date DATE NOT NULL,
    amount_ml INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
  );
  CREATE INDEX IF NOT EXISTS idx_water_log_user_date ON water_log (user_id, local_date);

  CREATE TABLE IF NOT EXISTS nutrition_goals (
    user_id TEXT PRIMARY KEY,
    calorie_goal INTEGER,
    protein_goal_g INTEGER,
    water_goal_ml INTEGER,
    updated_at TIMESTAMPTZ DEFAULT NOW()
  );
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

import httpx
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from auth import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/nutrition", tags=["nutrition"])

USDA_BASE = "https://api.nal.usda.gov/fdc/v1"
OFF_BASE = "https://world.openfoodfacts.org"
OFF_HEADERS = {"User-Agent": "TheGap/1.0 (hello@causalme.com)"}
OFF_FIELDS = "code,product_name,brands,nutriments,serving_size,serving_quantity"
MACRO_KEYS = ("calories", "protein_g", "carbs_g", "fat_g")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# A day only counts as "fully logged" for the engine above this many
# logged kcal — someone who logged just a coffee isn't someone who ate
# 40 kcal, and the engine shouldn't read it that way. Same idea for water.
MIN_COMPLETE_DAY_KCAL = 500
MIN_COMPLETE_DAY_WATER_ML = 500


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


def _check_date(value: str) -> str:
    if not DATE_RE.match(value):
        raise HTTPException(status_code=400, detail="local_date must be YYYY-MM-DD.")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="local_date must be a real date.")
    return value


# ── Food database lookups ────────────────────────────────────────────────────

def _food_item(source: str, source_id: str, name: str, brand: Optional[str], per100: dict,
               serving_grams: Optional[float], serving_label: Optional[str]) -> dict:
    """Normalize any source into one shape: macros for ONE serving."""
    if serving_grams and serving_grams > 0:
        factor = serving_grams / 100.0
        label = serving_label or f"{round(serving_grams)} g"
    else:
        factor, serving_grams, label = 1.0, 100.0, "100 g"
    return {
        "source": source,
        "source_id": source_id,
        "name": name,
        "brand": brand or None,
        "serving_label": label,
        "serving_grams": serving_grams,
        "per_serving": {k: round(per100.get(k, 0.0) * factor, 1) for k in MACRO_KEYS},
    }


def _tidy(text: Optional[str]) -> str:
    text = (text or "").strip()
    return text.title() if text.isupper() else text


def _usda_key() -> str:
    return os.getenv("USDA_API_KEY", "").strip() or "DEMO_KEY"


def _usda_per100(food: dict) -> Optional[dict]:
    vals: dict[str, float] = {}
    numbers = {"208": "calories", "203": "protein_g", "205": "carbs_g", "204": "fat_g"}
    for n in food.get("foodNutrients", []) or []:
        key = numbers.get(str(n.get("nutrientNumber")))
        if not key or n.get("value") is None:
            continue
        if key == "calories" and str(n.get("unitName", "")).upper() != "KCAL":
            continue
        vals[key] = float(n["value"])
    if "calories" not in vals:
        # Many generic foods report energy only via Atwater factors; fall
        # back to the standard 4/4/9 estimate rather than dropping them.
        if all(k in vals for k in ("protein_g", "carbs_g", "fat_g")):
            vals["calories"] = 4 * vals["protein_g"] + 4 * vals["carbs_g"] + 9 * vals["fat_g"]
        else:
            return None
    return {k: vals.get(k, 0.0) for k in MACRO_KEYS}


def _usda_to_item(food: dict) -> Optional[dict]:
    per100 = _usda_per100(food)
    if not per100 or not food.get("description"):
        return None
    serving_grams, label = None, None
    unit = str(food.get("servingSizeUnit", "")).lower()
    size = food.get("servingSize")
    if size and unit in ("g", "grm", "ml", "mlt"):  # ml treated as ~g
        serving_grams = float(size)
        household = (food.get("householdServingFullText") or "").strip()
        label = f"{household} ({round(serving_grams)} g)" if household else None
    brand = _tidy(food.get("brandName") or food.get("brandOwner"))
    return _food_item("usda", str(food.get("fdcId")), _tidy(food["description"]), brand, per100, serving_grams, label)


async def _usda_search(client: httpx.AsyncClient, query: str, data_types: str, page_size: int) -> list[dict]:
    resp = await client.get(
        f"{USDA_BASE}/foods/search",
        params={"query": query, "dataType": data_types, "pageSize": page_size, "requireAllWords": "true", "api_key": _usda_key()},
    )
    resp.raise_for_status()
    return [i for i in (_usda_to_item(f) for f in resp.json().get("foods", [])) if i]


def _off_per100(nutriments: dict) -> Optional[dict]:
    kcal = nutriments.get("energy-kcal_100g")
    if kcal is None and nutriments.get("energy_100g") is not None:
        kcal = float(nutriments["energy_100g"]) / 4.184  # kJ -> kcal
    if kcal is None:
        return None
    return {
        "calories": float(kcal),
        "protein_g": float(nutriments.get("proteins_100g") or 0),
        "carbs_g": float(nutriments.get("carbohydrates_100g") or 0),
        "fat_g": float(nutriments.get("fat_100g") or 0),
    }


def _off_to_item(product: dict) -> Optional[dict]:
    per100 = _off_per100(product.get("nutriments") or {})
    name = (product.get("product_name") or "").strip()
    if not per100 or not name:
        return None
    serving_grams = None
    try:
        q = float(product.get("serving_quantity"))
        serving_grams = q if q > 0 else None
    except (TypeError, ValueError):
        pass
    label = (product.get("serving_size") or "").strip() or None
    brand = (product.get("brands") or "").split(",")[0].strip()
    return _food_item("off", str(product.get("code") or name), name, brand, per100, serving_grams, label)


async def _off_search(client: httpx.AsyncClient, query: str) -> list[dict]:
    resp = await client.get(
        f"{OFF_BASE}/cgi/search.pl",
        params={"search_terms": query, "search_simple": 1, "action": "process", "json": 1, "page_size": 8, "fields": OFF_FIELDS},
        headers=OFF_HEADERS,
        timeout=6,
    )
    resp.raise_for_status()
    return [i for i in (_off_to_item(p) for p in resp.json().get("products", [])) if i]


async def _safe(coro, what: str, failures: list[str]) -> list[dict]:
    try:
        return await coro
    except Exception as exc:
        logger.warning("Food search source %s failed: %s", what, exc)
        failures.append(what)
        return []


@router.get("/search")
async def search_foods(q: str = Query(..., min_length=2, max_length=80), user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    failures: list[str] = []
    async with httpx.AsyncClient(timeout=10) as client:
        generic, branded, off = await asyncio.gather(
            _safe(_usda_search(client, q, "Foundation,SR Legacy", 6), "usda_generic", failures),
            _safe(_usda_search(client, q, "Branded", 8), "usda_branded", failures),
            _safe(_off_search(client, q), "off", failures),
        )

    seen: set[tuple[str, str]] = set()
    results: list[dict] = []
    for item in generic + branded + off:
        key = (item["name"].lower(), (item["brand"] or "").lower())
        if key in seen:
            continue
        seen.add(key)
        results.append(item)

    # "degraded" tells the app to say search is limited right now (usually
    # the shared USDA demo key hitting its rate limit) instead of silently
    # showing a thin result list as if nothing matched.
    degraded = "usda_generic" in failures and "usda_branded" in failures
    return JSONResponse(content={"results": results[:20], "degraded": degraded})


@router.get("/barcode/{code}")
async def lookup_barcode(code: str, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    if not re.fullmatch(r"\d{6,14}", code):
        raise HTTPException(status_code=400, detail="That doesn't look like a valid barcode.")

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(f"{OFF_BASE}/api/v2/product/{code}.json", params={"fields": OFF_FIELDS}, headers=OFF_HEADERS, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == 1 or data.get("product"):
                    item = _off_to_item(data.get("product") or {})
                    if item:
                        return JSONResponse(content={"food": item})
        except Exception as exc:
            logger.warning("OFF barcode lookup failed for %s: %s", code, exc)

        try:
            resp = await client.get(
                f"{USDA_BASE}/foods/search",
                params={"query": code, "dataType": "Branded", "pageSize": 5, "api_key": _usda_key()},
            )
            resp.raise_for_status()
            wanted = code.lstrip("0")
            for food in resp.json().get("foods", []):
                if str(food.get("gtinUpc", "")).lstrip("0") == wanted:
                    item = _usda_to_item(food)
                    if item:
                        return JSONResponse(content={"food": item})
        except Exception as exc:
            logger.warning("USDA barcode lookup failed for %s: %s", code, exc)

    return JSONResponse(content={"food": None})


# ── Logging ──────────────────────────────────────────────────────────────────

class PerServing(BaseModel):
    calories: float = Field(ge=0, le=5000)
    protein_g: float = Field(default=0, ge=0, le=500)
    carbs_g: float = Field(default=0, ge=0, le=1000)
    fat_g: float = Field(default=0, ge=0, le=500)


class LogFoodRequest(BaseModel):
    local_date: str
    meal: Literal["breakfast", "lunch", "dinner", "snack"]
    food_name: str = Field(min_length=1, max_length=200)
    brand: Optional[str] = Field(default=None, max_length=200)
    per_serving: PerServing
    servings: float = Field(gt=0, le=50)
    serving_label: Optional[str] = Field(default=None, max_length=100)
    serving_grams: Optional[float] = Field(default=None, gt=0, le=5000)
    local_hour: Optional[float] = Field(default=None, ge=0, lt=24)
    source: Optional[str] = Field(default=None, max_length=20)


@router.post("/log")
async def log_food(body: LogFoodRequest, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    _check_date(body.local_date)
    # Totals are computed here, once, from per-serving values — the client
    # never gets to send an inconsistent total.
    totals = {k: round(getattr(body.per_serving, k) * body.servings, 1) for k in MACRO_KEYS}
    if totals["calories"] > 10000:
        raise HTTPException(status_code=400, detail="That's more than 10,000 kcal in one entry — check the amount.")

    payload = {
        "user_id": user_id,
        "local_date": body.local_date,
        "meal": body.meal,
        "food_name": body.food_name.strip(),
        "brand": (body.brand or "").strip() or None,
        "servings": body.servings,
        "serving_label": body.serving_label,
        "serving_grams": body.serving_grams,
        "local_hour": body.local_hour,
        "source": body.source,
        **totals,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(_sb_url("food_log"), headers=_sb_headers("return=representation"), json=payload)
            resp.raise_for_status()
            row = resp.json()[0]
    except Exception as exc:
        logger.error("Logging food failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Couldn't save that — please try again.")
    return JSONResponse(content={"entry": row})


@router.delete("/log/{entry_id}")
async def delete_food_entry(entry_id: str, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.delete(
                _sb_url("food_log"),
                headers=_sb_headers("return=minimal"),
                params={"id": f"eq.{entry_id}", "user_id": f"eq.{user_id}"},
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.error("Deleting food entry failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Couldn't remove that entry.")
    return JSONResponse(content={"success": True})


class WaterRequest(BaseModel):
    local_date: str
    amount_ml: int = Field(gt=0, le=3000)


@router.post("/water")
async def add_water(body: WaterRequest, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    _check_date(body.local_date)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _sb_url("water_log"),
                headers=_sb_headers("return=representation"),
                json={"user_id": user_id, "local_date": body.local_date, "amount_ml": body.amount_ml},
            )
            resp.raise_for_status()
            row = resp.json()[0]
    except Exception as exc:
        logger.error("Logging water failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Couldn't save that — please try again.")
    return JSONResponse(content={"entry": row})


@router.delete("/water/{entry_id}")
async def delete_water_entry(entry_id: str, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.delete(
                _sb_url("water_log"),
                headers=_sb_headers("return=minimal"),
                params={"id": f"eq.{entry_id}", "user_id": f"eq.{user_id}"},
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.error("Deleting water entry failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Couldn't remove that entry.")
    return JSONResponse(content={"success": True})


# ── Reading a day / recents / goals ─────────────────────────────────────────

async def _get_rows(client: httpx.AsyncClient, table: str, params: dict) -> list[dict]:
    resp = await client.get(_sb_url(table), headers=_sb_headers(), params=params)
    resp.raise_for_status()
    return resp.json() or []


@router.get("/day")
async def get_day(local_date: str, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    _check_date(local_date)
    base = {"user_id": f"eq.{user_id}"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            food, water, goals = await asyncio.gather(
                _get_rows(client, "food_log", {**base, "local_date": f"eq.{local_date}", "select": "*", "order": "created_at.asc"}),
                _get_rows(client, "water_log", {**base, "local_date": f"eq.{local_date}", "select": "id,amount_ml", "order": "created_at.asc"}),
                _get_rows(client, "nutrition_goals", {**base, "select": "calorie_goal,protein_goal_g,water_goal_ml"}),
            )
    except httpx.HTTPStatusError as exc:
        # PostgREST answers 404 for a table that was never created — the
        # most likely cause right after this feature ships, since the
        # CREATE TABLE statements are run by hand.
        logger.error("Loading nutrition day failed for %s: HTTP %s from %s", user_id[:8], exc.response.status_code, exc.request.url.path)
        if exc.response.status_code == 404:
            raise HTTPException(status_code=500, detail="Your food log isn't set up on the server yet — the database tables still need creating.")
        raise HTTPException(status_code=500, detail="Couldn't load your log — please try again.")
    except Exception as exc:
        logger.error("Loading nutrition day failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Couldn't load your log — please try again.")

    totals = {k: round(sum(float(r.get(k) or 0) for r in food), 1) for k in MACRO_KEYS}
    return JSONResponse(content={
        "local_date": local_date,
        "entries": food,
        "totals": totals,
        "water_ml": sum(int(r["amount_ml"]) for r in water),
        "water_entries": water,
        "goals": goals[0] if goals else None,
    })


@router.get("/recent")
async def get_recent_foods(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    """Distinct recently logged foods, for one-tap re-logging."""
    since = (datetime.now(timezone.utc) - timedelta(days=60)).date().isoformat()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            rows = await _get_rows(client, "food_log", {
                "user_id": f"eq.{user_id}", "local_date": f"gte.{since}", "select": "*",
                "order": "created_at.desc", "limit": "200",
            })
    except Exception as exc:
        logger.error("Loading recent foods failed for %s: %s", user_id[:8], exc)
        return JSONResponse(content={"results": []})

    seen: set[tuple[str, str]] = set()
    results: list[dict] = []
    for r in rows:
        key = (r["food_name"].lower(), (r.get("brand") or "").lower())
        servings = float(r.get("servings") or 1) or 1.0
        if key in seen:
            continue
        seen.add(key)
        results.append({
            "source": "recent",
            "source_id": r["id"],
            "name": r["food_name"],
            "brand": r.get("brand"),
            "serving_label": r.get("serving_label") or "1 serving",
            "serving_grams": r.get("serving_grams"),
            "per_serving": {k: round(float(r.get(k) or 0) / servings, 1) for k in MACRO_KEYS},
        })
        if len(results) >= 25:
            break
    return JSONResponse(content={"results": results})


class GoalsRequest(BaseModel):
    calorie_goal: Optional[int] = Field(default=None, ge=500, le=10000)
    protein_goal_g: Optional[int] = Field(default=None, ge=0, le=500)
    water_goal_ml: Optional[int] = Field(default=None, ge=0, le=10000)


@router.get("/goals")
async def get_goals(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            rows = await _get_rows(client, "nutrition_goals", {"user_id": f"eq.{user_id}", "select": "calorie_goal,protein_goal_g,water_goal_ml"})
    except Exception as exc:
        logger.error("Loading nutrition goals failed for %s: %s", user_id[:8], exc)
        return JSONResponse(content={"goals": None})
    return JSONResponse(content={"goals": rows[0] if rows else None})


@router.put("/goals")
async def set_goals(body: GoalsRequest, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    payload = {
        "user_id": user_id,
        "calorie_goal": body.calorie_goal,
        "protein_goal_g": body.protein_goal_g,
        "water_goal_ml": body.water_goal_ml,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _sb_url("nutrition_goals"),
                headers=_sb_headers("resolution=merge-duplicates,return=representation"),
                params={"on_conflict": "user_id"},
                json=payload,
            )
            resp.raise_for_status()
            row = resp.json()[0]
    except Exception as exc:
        logger.error("Saving nutrition goals failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Couldn't save your goals — please try again.")
    return JSONResponse(content={"goals": {k: row.get(k) for k in ("calorie_goal", "protein_goal_g", "water_goal_ml")}})


# ── Engine input ─────────────────────────────────────────────────────────────

def get_nutrition_dataframe(user_id: str, days: int = 180) -> pd.DataFrame:
    """
    Date-indexed daily nutrition for the causal engine:
      dietary_energy, protein_g, carbs_g, fat_g — same names Apple Health
        nutrition uses, so daily_sync can let in-app logs override it
      last_meal_hour — local hour of day of the day's last logged food
      water_ml
    Only days that look fully logged contribute (see MIN_COMPLETE_DAY_*).
    """
    since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    params = {"user_id": f"eq.{user_id}", "local_date": f"gte.{since}"}
    frames = []
    try:
        food = httpx.get(
            _sb_url("food_log"), headers=_sb_headers(),
            params={**params, "select": "local_date,calories,protein_g,carbs_g,fat_g,local_hour"}, timeout=10,
        )
        food.raise_for_status()
        rows = food.json() or []
        if rows:
            f = pd.DataFrame(rows)
            f["local_hour"] = pd.to_numeric(f["local_hour"], errors="coerce")
            for col in ("calories", "protein_g", "carbs_g", "fat_g"):
                f[col] = pd.to_numeric(f[col], errors="coerce").fillna(0)
            g = f.groupby("local_date").agg(
                dietary_energy=("calories", "sum"), protein_g=("protein_g", "sum"),
                carbs_g=("carbs_g", "sum"), fat_g=("fat_g", "sum"), last_meal_hour=("local_hour", "max"),
            )
            g = g[g["dietary_energy"] >= MIN_COMPLETE_DAY_KCAL]
            frames.append(g)

        water = httpx.get(
            _sb_url("water_log"), headers=_sb_headers(),
            params={**params, "select": "local_date,amount_ml"}, timeout=10,
        )
        water.raise_for_status()
        wrows = water.json() or []
        if wrows:
            w = pd.DataFrame(wrows)
            w["amount_ml"] = pd.to_numeric(w["amount_ml"], errors="coerce").fillna(0)
            wg = w.groupby("local_date").agg(water_ml=("amount_ml", "sum"))
            frames.append(wg[wg["water_ml"] >= MIN_COMPLETE_DAY_WATER_ML])
    except Exception as exc:
        logger.error("Nutrition dataframe fetch failed: %s", exc)
        return pd.DataFrame()

    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, axis=1)
    df.index = pd.to_datetime(df.index)
    return df.sort_index()

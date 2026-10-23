"""
One door for quick logs: something typed into Quick Entry now, and later
something said to Siri or run from a Shortcut or the Action Button.

  POST /log/text                      a sentence; it is sorted into water, saved foods and meals,
                                      cigarettes, alcohol, coffee, energy drinks, weight, or a note
  GET  /log/food-notes                foods mentioned that weren't saved, waiting to be logged in the app
  POST /log/food-notes/{id}/resolve   mark one done

The sorting itself is utils/log_router.py (plain word matching, no AI). Every
sentence is also kept as a Quick Entry note with its exact time, whatever else
was done with it, so a wrong guess never loses anything.

Table DDL: see phase10.sql.
"""

from __future__ import annotations

import logging
from datetime import date as date_type, datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from auth import get_current_user_id
from routers.journal import _count_today, _get_streak, save_note
from routers.weight import delete_weight, save_weight
from utils import drink_times
from utils.local_time import DEFAULT_TZ
from utils.log_undo import Undo, restorable_fields, safe_ids, snapshot_checkin
from utils.voice_commands import load_commands
from utils.log_router import Action, Parsed, parse_log, spoken_summary, time_bucket
from utils.saved_logging import (
    _sb_headers,
    _sb_url,
    bump_use,
    insert_food_rows,
    load_saved,
    saved_food_rows,
    saved_meal_rows,
    too_big,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/log", tags=["log"])

MAX_TEXT = 500
COUNT_FIELDS = {
    "cigarettes": "cigarettes",
    "alcohol": "alcohol_drinks",
    "caffeine": "caffeine_drinks",
    "energy_drink": "energy_drinks",
}


class LogTextBody(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT)
    local_date: Optional[str] = None
    occurred_at: Optional[datetime] = None
    tz: Optional[str] = Field(default=None, max_length=64)
    source: Optional[str] = Field(default="app", max_length=20)


def local_clock(occurred_at: Optional[datetime], tz_name: Optional[str]) -> tuple[datetime, datetime, str]:
    """(the moment in UTC, the same moment where the person was, the time zone used)."""
    moment = occurred_at or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    moment = moment.astimezone(timezone.utc)
    for name in (tz_name, DEFAULT_TZ):
        if not name:
            continue
        try:
            return moment, moment.astimezone(ZoneInfo(name)), name
        except Exception:
            continue
    return moment, moment, "UTC"


def hour_of(local: datetime) -> float:
    return round(local.hour + local.minute / 60.0, 2)


# ── applying what was understood ─────────────────────────────────────────────

async def _add_to_checkin(client: httpx.AsyncClient, user_id: str, day: str, hour: float, adds: dict[str, float], alcohol: bool, pm_caffeine: bool, snapshot: Optional[dict] = None) -> dict[str, int]:
    """
    Adds to today's check-in counts without touching anything else in it. A day that has no
    check-in yet gets a partial one, whose unanswered questions stay unanswered (null), not "no".
    Returns the new totals for the counts that changed.
    """
    resp = await client.get(_sb_url("daily_checkins"), headers=_sb_headers(), params={"user_id": f"eq.{user_id}", "date": f"eq.{day}", "select": "*", "limit": "1"})
    resp.raise_for_status()
    rows = resp.json() or []
    existing = rows[0] if rows else None
    if snapshot is not None:
        snapshot["before"] = snapshot_checkin(existing)  # so the log can be undone exactly

    payload: dict = {"user_id": user_id, "date": day}
    totals: dict[str, int] = {}
    for field, amount in adds.items():
        total = int((existing or {}).get(field) or 0) + int(round(amount))
        payload[field] = total
        totals[field] = total
    bucket = time_bucket(hour)
    if "alcohol_drinks" in adds:
        payload["alcohol"] = True
        # Each drink adds its time of day to the day's list (a beer at 1 pm and another at 8 pm gives both).
        before = drink_times.clean((existing or {}).get("alcohol_time"))
        merged = drink_times.add(before, bucket)
        if merged != before:
            payload["alcohol_time"] = merged
    if "energy_drinks" in adds and not (existing or {}).get("energy_drink_time"):
        payload["energy_drink_time"] = bucket
    if pm_caffeine:
        payload["afternoon_caffeine"] = True
    if existing is None:
        payload["partial"] = True
        payload.setdefault("alcohol", None)
        payload.setdefault("afternoon_caffeine", None)

    droppable = {"partial", "caffeine_drinks", "alcohol_time", "energy_drink_time"}
    for _ in range(len(droppable) + 1):
        save = await client.post(
            _sb_url("daily_checkins"),
            headers=_sb_headers("resolution=merge-duplicates,return=minimal"),
            params={"on_conflict": "user_id,date"},
            json=payload,
        )
        if save.status_code == 400 and "PGRST204" in save.text:
            missing = next((c for c in droppable if f"'{c}'" in save.text and c in payload), None)
            if missing:
                payload.pop(missing)
                totals.pop(missing, None)
                continue
        save.raise_for_status()
        return totals
    raise RuntimeError("daily_checkins rejected the log")


async def _water_today(client: httpx.AsyncClient, user_id: str, day: str) -> int:
    resp = await client.get(_sb_url("water_log"), headers=_sb_headers(), params={"user_id": f"eq.{user_id}", "local_date": f"eq.{day}", "select": "amount_ml"})
    resp.raise_for_status()
    return sum(int(r["amount_ml"]) for r in resp.json() or [])


async def _weight_on(client: httpx.AsyncClient, user_id: str, day: str) -> Optional[float]:
    """The weight already saved for a day, if any (so a log that replaces it can be undone)."""
    try:
        resp = await client.get(_sb_url("weight_log"), headers=_sb_headers(), params={"user_id": f"eq.{user_id}", "local_date": f"eq.{day}", "select": "weight_kg", "limit": "1"})
        resp.raise_for_status()
        rows = resp.json() or []
        return float(rows[0]["weight_kg"]) if rows else None
    except Exception:
        return None


async def _add_water(client: httpx.AsyncClient, user_id: str, day: str, hour: float, ml: int) -> tuple[int, Optional[str]]:
    """Adds a water entry. Returns today's total and the new entry's id (None if the database didn't say)."""
    row = {"user_id": user_id, "local_date": day, "amount_ml": ml, "local_hour": hour}
    resp = await client.post(_sb_url("water_log"), headers=_sb_headers("return=representation"), json=row)
    if resp.status_code == 400 and "PGRST204" in resp.text:
        row.pop("local_hour")  # the time-of-day column isn't there yet
        resp = await client.post(_sb_url("water_log"), headers=_sb_headers("return=representation"), json=row)
    resp.raise_for_status()
    try:
        new_id = (resp.json() or [{}])[0].get("id")
    except Exception:
        new_id = None
    return await _water_today(client, user_id, day), new_id


async def apply_actions(user_id: str, parsed: Parsed, day: str, hour: float, undo: Optional[dict] = None) -> tuple[list[dict], list[str]]:
    """Does what was understood. Returns (what was logged, for the app; the same as short phrases for speaking).
    If `undo` is given, what was created is written into it (see utils/log_undo.py) so the log can be reversed."""
    undo = undo if undo is not None else {}
    logged: list[dict] = []
    phrases: list[str] = []
    count_adds: dict[str, float] = {}
    count_actions: dict[str, Action] = {}
    for action in parsed.actions:
        if action.kind in COUNT_FIELDS:
            count_adds[COUNT_FIELDS[action.kind]] = count_adds.get(COUNT_FIELDS[action.kind], 0) + action.amount
            count_actions[COUNT_FIELDS[action.kind]] = action

    async with httpx.AsyncClient(timeout=20) as client:
        # Check-in counts, together in one save
        if count_adds:
            try:
                snapshot: dict = {}
                totals = await _add_to_checkin(client, user_id, day, hour, count_adds, "alcohol_drinks" in count_adds, "caffeine_drinks" in count_adds and hour >= 14, snapshot)
                undo.update(checkin_day=day, checkin_touched=True, checkin_before=snapshot.get("before"))
                for field, action in count_actions.items():
                    if field not in totals:
                        continue
                    logged.append({"kind": action.kind, "summary": f"{action.label} ({totals[field]} today)"})
                    phrases.append(f"{action.label}, {totals[field]} today" if len(count_actions) == 1 else action.label)
            except Exception as exc:
                logger.error("Adding to the check-in failed for %s: %s", user_id[:8], exc)

        foods, meals = (None, None)
        for action in parsed.actions:
            try:
                if action.kind == "water":
                    total, water_id = await _add_water(client, user_id, day, hour, int(action.amount))
                    if water_id:
                        undo.setdefault("water_ids", []).append(water_id)
                    logged.append({"kind": "water", "summary": f"{action.label} ({total} ml today)"})
                    phrases.append(f"{action.label}, {total} ml today")
                elif action.kind == "weight":
                    previous_kg = await _weight_on(client, user_id, day)
                    await save_weight(user_id, day, float(action.amount))
                    undo.update(weight_day=day, weight_touched=True, weight_previous_kg=previous_kg)
                    logged.append({"kind": "weight", "summary": f"Weight {action.label}"})
                    phrases.append(f"your weight, {action.label}")
                elif action.kind in ("saved_food", "saved_meal"):
                    if foods is None:
                        foods, meals = await load_saved(client, user_id)
                    if action.kind == "saved_food":
                        item = next((f for f in foods or [] if f["id"] == action.ref_id), None)
                        rows = saved_food_rows(user_id, item, action.servings, day, hour, None) if item else []
                        table = "saved_foods"
                    else:
                        item = next((m for m in meals or [] if m["id"] == action.ref_id), None)
                        rows = saved_meal_rows(user_id, item, action.servings, day, hour, None) if item else []
                        table = "saved_meals"
                    if not item or not rows or too_big(rows):
                        continue
                    saved = await insert_food_rows(client, rows)
                    undo.setdefault("food_ids", []).extend(r["id"] for r in saved if isinstance(r, dict) and r.get("id"))
                    await bump_use(client, table, user_id, item)
                    kcal = round(sum(r["calories"] for r in rows))
                    name = action.label if action.servings == 1 else f"{action.servings:g} × {action.label}"
                    logged.append({"kind": action.kind, "summary": f"{name} ({kcal} kcal)"})
                    phrases.append(f"your {action.label}" if action.servings == 1 else f"{action.servings:g} {action.label}")
            except Exception as exc:
                logger.error("Applying a %s log failed for %s: %s", action.kind, user_id[:8], exc)
    return logged, phrases


async def process_log_text(user_id: str, text: str, local_date: Optional[str], occurred_at: Optional[datetime], tz: Optional[str], source: str) -> dict:
    """Sorts one sentence, does what it understood, keeps the sentence as a note, and says what happened."""
    text = " ".join(text.split())[:MAX_TEXT]
    moment, local, tz_used = local_clock(occurred_at, tz)
    day = local_date or local.date().isoformat()
    try:
        date_type.fromisoformat(day)
    except ValueError:
        day = local.date().isoformat()
    hour = hour_of(local)

    async with httpx.AsyncClient(timeout=15) as client:
        foods, meals = await load_saved(client, user_id)
        custom = await load_commands(client, user_id)
    parsed = parse_log(text, hour, foods, meals, custom)

    undo: dict = {}
    logged, phrases = await apply_actions(user_id, parsed, day, hour, undo)
    food_note = any(a.kind == "food_note" for a in parsed.actions)
    try:
        note_id = await save_note(
            user_id, text, day, moment, tz_used, source,
            routed_to=[{"kind": item["kind"], "summary": item["summary"]} for item in logged] or None,
            food_note=food_note,
        )
        if note_id:
            undo["note_id"] = note_id
    except Exception as exc:
        logger.error("Saving the note failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Could not save that. Please try again.")

    count_today = await _count_today(user_id, day)
    streak = await _get_streak(user_id, day)
    return {
        "success": True,
        "count_today": count_today,
        "streak": streak,
        "logged": logged,
        "food_note": food_note,
        "spoken": spoken_summary(phrases, not logged, parsed.unsure, food_note and not logged),
        "undo": undo or None,
    }


@router.post("/text")
async def log_text(body: LogTextBody, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Entry can't be empty.")
    result = await process_log_text(user_id, body.text, body.local_date, body.occurred_at, body.tz, body.source or "app")
    return JSONResponse(content=result)


@router.get("/food-notes")
async def food_notes(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    """Foods said or typed that weren't saved foods, waiting to be logged properly."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                _sb_url("quick_entries"),
                headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "food_note": "eq.true", "resolved_at": "is.null", "select": "id,entry_text,local_date,occurred_at", "order": "created_at.desc", "limit": "10"},
            )
            resp.raise_for_status()
            return JSONResponse(content={"notes": resp.json() or []})
    except Exception as exc:
        logger.info("Loading food notes failed (continuing without them): %s", exc)
        return JSONResponse(content={"notes": []})


def _valid_day(value: Optional[str]) -> Optional[str]:
    try:
        return date_type.fromisoformat(value).isoformat() if value else None
    except ValueError:
        return None


async def undo_quick_entry(user_id: str, undo: Undo) -> list[str]:
    """Reverses one quick log. Every change is scoped to this person. Returns what couldn't be undone (empty when all went well)."""
    failed: list[str] = []
    async with httpx.AsyncClient(timeout=20) as client:

        async def remove(table: str, params: dict, what: str) -> None:
            try:
                resp = await client.delete(_sb_url(table), headers=_sb_headers("return=minimal"), params={**params, "user_id": f"eq.{user_id}"})
                resp.raise_for_status()
            except Exception as exc:
                logger.error("Undo: removing %s failed for %s: %s", what, user_id[:8], exc)
                failed.append(what)

        note = safe_ids([undo.note_id])
        if note:
            await remove("quick_entries", {"id": f"eq.{note[0]}"}, "the note")
        water = safe_ids(undo.water_ids)
        if water:
            await remove("water_log", {"id": f"in.({','.join(water)})"}, "the water")
        food = safe_ids(undo.food_ids)
        if food:
            await remove("food_log", {"id": f"in.({','.join(food)})"}, "the food")

        day = _valid_day(undo.checkin_day)
        if undo.checkin_touched and day:
            try:
                where = {"user_id": f"eq.{user_id}", "date": f"eq.{day}"}
                if undo.checkin_before is None:
                    # The log started this day's check-in. Take it away only while it's still that bare one.
                    resp = await client.get(_sb_url("daily_checkins"), headers=_sb_headers(), params={**where, "select": "partial", "limit": "1"})
                    resp.raise_for_status()
                    rows = resp.json() or []
                    if rows and rows[0].get("partial"):
                        await remove("daily_checkins", {"date": f"eq.{day}", "partial": "eq.true"}, "the check-in change")
                else:
                    fields = restorable_fields(undo.checkin_before)
                    for _ in range(len(fields) + 1):
                        if not fields:
                            break
                        resp = await client.patch(_sb_url("daily_checkins"), headers=_sb_headers("return=minimal"), params=where, json=fields)
                        if resp.status_code == 400 and "PGRST204" in resp.text:
                            missing = next((c for c in fields if f"'{c}'" in resp.text), None)
                            if missing:
                                fields.pop(missing)
                                continue
                        resp.raise_for_status()
                        break
            except Exception as exc:
                logger.error("Undo: restoring the check-in failed for %s: %s", user_id[:8], exc)
                failed.append("the check-in change")

    weight_day = _valid_day(undo.weight_day)
    if undo.weight_touched and weight_day:
        try:
            previous = undo.weight_previous_kg
            if previous is None:
                await delete_weight(date_type.fromisoformat(weight_day), user_id)
            elif 20 <= previous <= 500:
                await save_weight(user_id, weight_day, round(previous, 2))
        except Exception as exc:
            logger.error("Undo: restoring the weight failed for %s: %s", user_id[:8], exc)
            failed.append("the weight")
    return failed


@router.post("/undo")
async def undo_log(body: Undo, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    """Reverses a quick log, using the `undo` that came back with it."""
    failed = await undo_quick_entry(user_id, body)
    if failed:
        raise HTTPException(status_code=500, detail="Couldn't undo " + " or ".join(failed) + ". You can remove it from today's log.")
    return JSONResponse(content={"success": True})


@router.post("/food-notes/{note_id}/resolve")
async def resolve_food_note(note_id: str, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.patch(
                _sb_url("quick_entries"),
                headers=_sb_headers("return=minimal"),
                params={"id": f"eq.{note_id}", "user_id": f"eq.{user_id}"},
                json={"resolved_at": datetime.now(timezone.utc).isoformat()},
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.error("Resolving a food note failed for %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=500, detail="Couldn't update that.")
    return JSONResponse(content={"success": True})


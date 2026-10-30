"""
"Describe it": turn a person's own words about a home-cooked meal into an editable ingredient list (see utils/meal_describe.py).

  POST /nutrition/describe   {"text": "Spag bol for 4: 500 g mince, a jar of sauce, 200 g spaghetti, a tablespoon of oil"}

Nothing is saved or logged here. The app puts the list into the meal builder for the person to check and change.
It follows the other AI features: off when the person has turned AI off, needs an active subscription or free week, and counts
against their monthly AI allowance.

The answer is one of:
  {"name", "serves", "ingredients": [...], "notes": [...]}   the list (each ingredient says if it was guessed, or is an estimate)
  {"ai_off": true}        AI features are switched off for this person
  {"budget_used": true, "message": ...}   this month's AI allowance is used up
  {"empty": true, "message": ...}         nothing that sounded like ingredients
  {"failed": true, "message": ...}        the AI couldn't be reached
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from auth import get_current_user_id
from routers.nutrition import _usda_search
from utils import ai_budget
from utils.consent import ai_allowed
from utils.entitlement import require_subscription
from utils.meal_describe import ground, read_description

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/nutrition/describe", tags=["nutrition"])

MIN_CHARS = 8
USDA_TYPES = "Foundation,SR Legacy"  # generic foods, not branded products

# What the database said for a name, so common ingredients (onion, olive oil) aren't looked up again and again.
_matches: dict[str, list] = {}
_MAX_CACHED = 400


class DescribeBody(BaseModel):
    text: str = Field(min_length=3, max_length=800)


@router.post("")
async def describe_meal(body: DescribeBody, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    text = " ".join(body.text.split())
    if len(text) < MIN_CHARS:
        return JSONResponse(content={"empty": True, "message": "Tell me a bit more about what goes into it."})
    if not await ai_allowed(user_id):
        return JSONResponse(content={"ai_off": True})
    await require_subscription(user_id)

    async with ai_budget.metered(user_id, "meal_describe") as meter:
        read = None if meter.blocked else await read_description(text)
    if meter.blocked:
        return JSONResponse(content={"budget_used": True, "message": "You've used this month's AI allowance, which starts again on " + ai_budget.resets_on() + ". You can still build the meal by searching for ingredients."})
    if read is None:
        return JSONResponse(content={"failed": True, "message": "Couldn't work that out just now. Try again, or add the ingredients by searching."})
    if not read["ingredients"]:
        return JSONResponse(content={"empty": True, "message": "I couldn't find any ingredients in that. Try listing what goes in, like 500 g mince, a jar of sauce and 200 g pasta."})

    async with httpx.AsyncClient(timeout=10) as client:

        async def search(term: str) -> list:
            key = term.lower()
            if key in _matches:
                return _matches[key]
            items = await _usda_search(client, term, USDA_TYPES, 5)
            if len(_matches) >= _MAX_CACHED:
                _matches.clear()
            _matches[key] = items
            return items

        ingredients = await ground(read["ingredients"], search)

    if not ingredients:
        return JSONResponse(content={"empty": True, "message": "I couldn't work out the amounts from that. Try adding how much of each ingredient."})
    return JSONResponse(content={"name": read["name"], "serves": read["serves"], "ingredients": ingredients, "notes": read["notes"]})

"""
The written summary for a workout rundown (see utils/rundown_summary.py).

  POST /workouts/rundown-summary   {the numbers from one finished workout}

Only numbers and movement names are sent, never a name, title or note. Nothing is stored here: the app keeps the text on the phone.
It follows the other AI features: off when the person has turned AI off, needs an active subscription or free week, and counts
against their monthly AI allowance. When anything stops it, the app keeps the plain summary it wrote from the same numbers.

The answer is one of:
  {"summary": "..."}                         the written summary (it has passed the checks)
  {"ai_off": true}                           AI features are switched off for this person
  {"budget_used": true, "message": ...}      this month's AI allowance is used up
  {"failed": true}                           the AI couldn't be reached or its text didn't pass the checks
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from auth import get_current_user_id
from utils import ai_budget, safety
from utils.consent import ai_allowed
from utils.entitlement import require_subscription
from utils.rundown_summary import MAX_MOVEMENTS, RundownFacts, write_summary

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/workouts/rundown-summary", tags=["workouts"])

DAILY_LIMIT = 40  # far more than anyone finishes in a day; the allowance is the real limit
_calls: dict[str, list[float]] = {}


def _within_daily_limit(user_id: str) -> bool:
    now = time.time()
    recent = [t for t in _calls.get(user_id, []) if now - t < 86400]
    if len(recent) >= DAILY_LIMIT:
        _calls[user_id] = recent
        return False
    recent.append(now)
    if len(_calls) > 5000:
        _calls.clear()
    _calls[user_id] = recent
    return True


@router.post("")
async def rundown_summary(body: RundownFacts, user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    # Limits checked here rather than as Field constraints, which are spelled differently across pydantic major versions.
    if len(body.movements) > MAX_MOVEMENTS:
        raise HTTPException(status_code=400, detail="That workout is too large to summarise.")
    if not await ai_allowed(user_id):
        return JSONResponse(content={"ai_off": True})
    await require_subscription(user_id)
    # The movement names are the only words in the request. If one looks like someone in distress, no AI call is made.
    if safety.assess(" ".join(m.name for m in body.movements)) is not None:
        return JSONResponse(content={"failed": True})
    if not _within_daily_limit(user_id):
        return JSONResponse(content={"failed": True})

    async with ai_budget.metered(user_id, "rundown_summary") as meter:
        text = None if meter.blocked else await write_summary(body)
    if meter.blocked:
        return JSONResponse(content={"budget_used": True, "message": "You've used this month's AI allowance, which starts again on " + ai_budget.resets_on() + "."})
    if text is None:
        return JSONResponse(content={"failed": True})
    return JSONResponse(content={"summary": text})

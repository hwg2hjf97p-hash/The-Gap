"""
GET /ai-usage — how much of this month's AI allowance the person has used,
for the little meter in the app and the "used up" message. Percent only, never
money. See utils/ai_budget.py.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from auth import get_current_user_id
from utils import ai_budget

router = APIRouter(prefix="/ai-usage", tags=["ai-usage"])


@router.get("")
async def get_ai_usage(user_id: str = Depends(get_current_user_id)) -> JSONResponse:
    st = await ai_budget.status(user_id)
    return JSONResponse(
        content={
            "tier": st["tier"],
            "used_pct": st["used_pct"],
            "exhausted": bool(st["exhausted"]) and ai_budget.enforcing(),
            "resets_on": st["resets_on"],
            "message": ai_budget.blocked_message(st) if st["exhausted"] and ai_budget.enforcing() else None,
        }
    )

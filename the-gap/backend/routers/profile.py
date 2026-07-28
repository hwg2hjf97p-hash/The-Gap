from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from sync.user_profile_store import save_user_profile, get_user_profile

router = APIRouter(prefix="/profile", tags=["profile"])


class ProfileRequest(BaseModel):
    user_id: str
    weight_kg: float | None = None
    height_cm: float | None = None
    age: int | None = None


@router.post("")
async def set_profile(body: ProfileRequest) -> JSONResponse:
    saved = await save_user_profile(body.user_id, body.weight_kg, body.height_cm, body.age)
    if not saved:
        raise HTTPException(status_code=500, detail="Couldn't save profile — please try again.")
    return JSONResponse(content={"status": "ok"})


@router.get("/{user_id}")
async def read_profile(user_id: str) -> JSONResponse:
    profile = await get_user_profile(user_id)
    if not profile:
        return JSONResponse(content={"weight_kg": None, "height_cm": None, "age": None})
    return JSONResponse(content=profile)

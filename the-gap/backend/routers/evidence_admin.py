"""
Reviewing the research library. Protected by ADMIN_SECRET (sent as the
X-Admin-Secret header); without that variable set on the server these routes
answer "not found", like the debug pages.

  GET   /admin/evidence?status=pending|approved|rejected&category=&limit=&offset=
  GET   /admin/evidence/stats
  PATCH /admin/evidence/{id}            edit a card's words (re-runs the automatic checks)
  POST  /admin/evidence/{id}/approve    only when every automatic check passes
  POST  /admin/evidence/{id}/reject
  POST  /admin/evidence/{id}/unapprove  take a card back out of use
  POST  /admin/evidence/seed            collect more studies in the background
  GET   /admin/evidence/seed/status

Approval is the only way `verified` becomes true.
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from utils import evidence_seed
from utils.evidence_checks import blocking_problems, can_approve, text_checks
from utils.evidence_topics import CATEGORY_KEYS, topics_for

logger = logging.getLogger(__name__)


def require_admin(x_admin_secret: str = Header(default="")) -> None:
    expected = os.getenv("ADMIN_SECRET", "").strip()
    if not expected:
        raise HTTPException(status_code=404, detail="Not found")
    if not secrets.compare_digest(x_admin_secret.strip(), expected):
        raise HTTPException(status_code=401, detail="Wrong password.")


router = APIRouter(prefix="/admin/evidence", tags=["admin"], dependencies=[Depends(require_admin)])

_TASKS: set = set()
EDITABLE = ("title", "plain_summary", "finding", "population", "caution_notes", "experiment_label", "category", "sample_size", "weight_related", "metric_tags")


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


async def _get_card_with_source(client: httpx.AsyncClient, card_id: str) -> tuple[dict, dict]:
    card_resp = await client.get(_sb_url("evidence_cards"), headers=_sb_headers(), params={"id": f"eq.{card_id}", "select": "*", "limit": "1"})
    card_resp.raise_for_status()
    cards = card_resp.json() or []
    if not cards:
        raise HTTPException(status_code=404, detail="Card not found.")
    src_resp = await client.get(_sb_url("evidence_sources"), headers=_sb_headers(), params={"card_id": f"eq.{card_id}", "select": "*", "limit": "1"})
    src_resp.raise_for_status()
    sources = src_resp.json() or []
    return cards[0], (sources[0] if sources else {})


def _recheck(card: dict, source: dict) -> dict:
    """The text checks run again on the card as it now reads; the network results are kept."""
    old = source.get("checks") or {}
    fresh = text_checks(card, source.get("abstract") or "")
    return {**old, **fresh}


@router.get("")
async def list_cards(status: str = "pending", category: Optional[str] = None, limit: int = 20, offset: int = 0) -> JSONResponse:
    filters = {"pending": {"verified": "eq.false", "rejected": "eq.false"}, "approved": {"verified": "eq.true"}, "rejected": {"rejected": "eq.true"}}
    if status not in filters:
        raise HTTPException(status_code=400, detail="status must be pending, approved or rejected.")
    params = {"select": "*", "order": "category.asc,created_at.asc", "limit": str(min(limit, 50)), "offset": str(offset), **filters[status]}
    if category:
        params["category"] = f"eq.{category}"
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(_sb_url("evidence_cards"), headers=_sb_headers(), params=params)
        resp.raise_for_status()
        cards = resp.json() or []
        sources: dict[str, dict] = {}
        if cards:
            ids = ",".join(c["id"] for c in cards)
            src = await client.get(_sb_url("evidence_sources"), headers=_sb_headers(), params={"card_id": f"in.({ids})", "select": "*"})
            src.raise_for_status()
            sources = {s["card_id"]: s for s in src.json() or []}
    for card in cards:
        source = sources.get(card["id"], {})
        checks = source.get("checks") or {}
        card["source"] = {"pubmed_title": source.get("pubmed_title"), "abstract": source.get("abstract"), "checks": checks, "drafted_by": source.get("drafted_by")}
        card["can_approve"] = can_approve(checks)
        card["blocking_problems"] = blocking_problems(checks)
    return JSONResponse(content={"cards": cards})


@router.get("/stats")
async def stats() -> JSONResponse:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(_sb_url("evidence_cards"), headers=_sb_headers(), params={"select": "category,verified,rejected", "limit": "5000"})
        resp.raise_for_status()
        rows = resp.json() or []
    table = {c: {"approved": 0, "pending": 0, "rejected": 0} for c in CATEGORY_KEYS}
    for r in rows:
        bucket = table.setdefault(r["category"], {"approved": 0, "pending": 0, "rejected": 0})
        bucket["approved" if r["verified"] else "rejected" if r["rejected"] else "pending"] += 1
    totals = {k: sum(v[k] for v in table.values()) for k in ("approved", "pending", "rejected")}
    return JSONResponse(content={"by_category": table, "totals": totals, "seed": evidence_seed.STATUS.as_dict()})


class EditBody(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    plain_summary: Optional[str] = Field(default=None, max_length=1200)
    finding: Optional[str] = Field(default=None, max_length=800)
    population: Optional[str] = Field(default=None, max_length=300)
    caution_notes: Optional[str] = Field(default=None, max_length=800)
    experiment_label: Optional[str] = Field(default=None, max_length=200)
    category: Optional[str] = None
    sample_size: Optional[int] = Field(default=None, ge=1)
    weight_related: Optional[bool] = None
    metric_tags: Optional[list[str]] = None


@router.patch("/{card_id}")
async def edit_card(card_id: str, body: EditBody) -> JSONResponse:
    dump = body.model_dump if hasattr(body, "model_dump") else body.dict  # pydantic 2 or 1
    changes = {k: v for k, v in dump(exclude_unset=True).items() if k in EDITABLE}
    if "category" in changes and changes["category"] not in CATEGORY_KEYS:
        raise HTTPException(status_code=400, detail="Unknown category.")
    async with httpx.AsyncClient(timeout=20) as client:
        card, source = await _get_card_with_source(client, card_id)
        if card.get("verified"):
            raise HTTPException(status_code=409, detail="Unapprove the card before editing it.")
        card.update(changes)
        checks = _recheck(card, source)
        if changes:
            resp = await client.patch(_sb_url("evidence_cards"), headers=_sb_headers("return=representation"), params={"id": f"eq.{card_id}"}, json=changes)
            resp.raise_for_status()
        await client.patch(_sb_url("evidence_sources"), headers=_sb_headers("return=minimal"), params={"card_id": f"eq.{card_id}"}, json={"checks": checks})
    return JSONResponse(content={"checks": checks, "can_approve": can_approve(checks), "blocking_problems": blocking_problems(checks)})


@router.post("/{card_id}/approve")
async def approve(card_id: str) -> JSONResponse:
    async with httpx.AsyncClient(timeout=20) as client:
        card, source = await _get_card_with_source(client, card_id)
        checks = _recheck(card, source)
        if not can_approve(checks):
            return JSONResponse(status_code=409, content={"detail": "This card didn't pass the automatic checks.", "blocking_problems": blocking_problems(checks)})
        resp = await client.patch(
            _sb_url("evidence_cards"), headers=_sb_headers("return=minimal"), params={"id": f"eq.{card_id}"},
            json={"verified": True, "rejected": False, "verified_at": datetime.now(timezone.utc).isoformat()},
        )
        resp.raise_for_status()
        await client.patch(_sb_url("evidence_sources"), headers=_sb_headers("return=minimal"), params={"card_id": f"eq.{card_id}"}, json={"checks": checks})
    return JSONResponse(content={"approved": True})


@router.post("/{card_id}/reject")
async def reject(card_id: str) -> JSONResponse:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.patch(_sb_url("evidence_cards"), headers=_sb_headers("return=minimal"), params={"id": f"eq.{card_id}"}, json={"verified": False, "verified_at": None, "rejected": True})
        resp.raise_for_status()
    return JSONResponse(content={"rejected": True})


@router.post("/{card_id}/unapprove")
async def unapprove(card_id: str) -> JSONResponse:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.patch(_sb_url("evidence_cards"), headers=_sb_headers("return=minimal"), params={"id": f"eq.{card_id}"}, json={"verified": False, "verified_at": None})
        resp.raise_for_status()
    return JSONResponse(content={"unapproved": True})


class SeedBody(BaseModel):
    categories: Optional[list[str]] = None
    per_topic: int = Field(default=2, ge=1, le=4)


@router.post("/seed")
async def start_seed(body: SeedBody) -> JSONResponse:
    if evidence_seed.STATUS.running:
        raise HTTPException(status_code=409, detail="A collection is already running.")
    if body.categories and any(c not in CATEGORY_KEYS for c in body.categories):
        raise HTTPException(status_code=400, detail="Unknown category.")
    if not os.getenv("ANTHROPIC_API_KEY", "").strip():
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY isn't set on the server.")
    topics = topics_for(body.categories)
    task = asyncio.create_task(evidence_seed.run_seed(topics, body.per_topic))
    _TASKS.add(task)  # keep a reference so the task isn't garbage collected mid-run
    task.add_done_callback(_TASKS.discard)
    return JSONResponse(content={"started": True, "topics": len(topics)})


@router.get("/seed/status")
async def seed_status() -> JSONResponse:
    return JSONResponse(content=evidence_seed.STATUS.as_dict())

"""
Reading the research library for display. The one rule: only approved cards are
ever returned. Every read goes through here so that rule lives in one place.
"""

from __future__ import annotations

import os
from typing import Optional

import httpx

# What the app may show of a card. The abstract and check results are never included.
PUBLIC_FIELDS = (
    "id,category,title,plain_summary,finding,metric_tags,study_type,sample_size,population,year,journal,"
    "doi,pubmed_id,url,caution_notes,experiment_label,experiment_days,weight_related"
)

DISCLAIMER = "General information from published research, not medical advice. Talk to your doctor before starting supplements or changing medication."


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers() -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def verified_params(extra: Optional[dict] = None) -> dict:
    """Query parameters that restrict a read of evidence_cards to approved, unrejected cards."""
    return {"select": PUBLIC_FIELDS, "verified": "eq.true", "rejected": "eq.false", **(extra or {})}


async def get_verified_card(card_id: str) -> Optional[dict]:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(_sb_url("evidence_cards"), headers=_sb_headers(), params=verified_params({"id": f"eq.{card_id}", "limit": "1"}))
        resp.raise_for_status()
        rows = resp.json() or []
        return rows[0] if rows else None


async def list_verified_cards(tags: Optional[list[str]] = None, category: Optional[str] = None, limit: int = 100) -> list[dict]:
    extra: dict = {"limit": str(limit)}
    if tags:
        extra["metric_tags"] = "ov.{" + ",".join(tags) + "}"
    if category:
        extra["category"] = f"eq.{category}"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(_sb_url("evidence_cards"), headers=_sb_headers(), params=verified_params(extra))
        resp.raise_for_status()
        return resp.json() or []

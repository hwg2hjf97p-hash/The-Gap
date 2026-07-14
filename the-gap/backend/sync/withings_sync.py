"""
Withings data sync — pulls sleep, weight, and heart-rate data.
Uses stored OAuth tokens from Supabase user_connections table.

Withings' API has a genuinely different shape from Whoop/Oura: every call
(including refresh) goes through the same /v2/oauth2 endpoint with an
`action` param, and errors come back as HTTP 200 with a `status` field
in the body rather than a real HTTP error code. Handled explicitly below
rather than trying to force it through the same pattern as other providers.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

WITHINGS_TOKEN_URL = "https://wbsapi.withings.net/v2/oauth2"
WITHINGS_API_BASE = "https://wbsapi.withings.net"


async def refresh_withings_token(refresh_token: str, client_id: str, client_secret: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            WITHINGS_TOKEN_URL,
            data={
                "action": "requesttoken",
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
            },
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("status") != 0:
            raise RuntimeError(f"Withings token refresh failed: {body.get('error')}")
        return body["body"]


async def _withings_post(client: httpx.AsyncClient, path: str, access_token: str, data: dict) -> Optional[dict]:
    """
    POST to a Withings data endpoint. Returns None on failure (logged, not
    raised) so one endpoint failing doesn't discard data from the others —
    same fault-tolerance pattern used for Whoop and Oura.
    """
    try:
        resp = await client.post(
            f"{WITHINGS_API_BASE}{path}",
            headers={"Authorization": f"Bearer {access_token}"},
            data=data,
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("status") != 0:
            logger.warning("Withings %s returned status=%s (continuing without it)", path, body.get("status"))
            return None
        return body.get("body")
    except Exception as exc:
        logger.warning("Withings %s failed (continuing without it): %s", path, exc)
        return None


async def fetch_withings_data(access_token: str, days_back: int = 90) -> pd.DataFrame:
    """
    Fetch Withings sleep and weight data for the last N days.
    Returns a DataFrame with The Gap column names.

    NOTE: Withings' exact sleep-summary field names are documented
    inconsistently across their own materials — this uses the commonly
    documented shape (total_sleep_time, hr_average, etc). If early real
    connections show different field names in practice, that's expected
    the first time (same as happened with Whoop/Oura) and quick to fix
    once we see actual logged responses.
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days_back)
    rows: dict[str, dict] = {}

    async with httpx.AsyncClient(timeout=30) as client:
        sleep_body = await _withings_post(
            client, "/v2/sleep", access_token,
            {
                "action": "getsummary",
                "startdateymd": start.strftime("%Y-%m-%d"),
                "enddateymd": end.strftime("%Y-%m-%d"),
            },
        )
        if sleep_body:
            for entry in sleep_body.get("series", []):
                date = entry.get("date", entry.get("startdate", ""))[:10] if isinstance(entry.get("date"), str) else None
                data = entry.get("data", {})
                if not date:
                    # Some responses key by startdate as epoch seconds instead of a date string
                    raw_start = entry.get("startdate")
                    if raw_start:
                        date = datetime.fromtimestamp(raw_start, tz=timezone.utc).strftime("%Y-%m-%d")
                if not date:
                    continue
                rows.setdefault(date, {})
                total_sleep_sec = data.get("total_sleep_time")
                if total_sleep_sec is not None:
                    rows[date]["sleep_total_min"] = total_sleep_sec / 60
                if data.get("hr_average") is not None:
                    rows[date]["resting_hr"] = data.get("hr_average")

        weight_body = await _withings_post(
            client, "/measure", access_token,
            {
                "action": "getmeas",
                "meastypes": "1",  # 1 = weight
                "category": "1",
                "startdate": int(start.timestamp()),
                "enddate": int(end.timestamp()),
            },
        )
        if weight_body:
            for grp in weight_body.get("measuregrps", []):
                ts = grp.get("date")
                if not ts:
                    continue
                date = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
                for m in grp.get("measures", []):
                    if m.get("type") == 1:  # weight
                        value = m.get("value", 0) * (10 ** m.get("unit", 0))
                        rows.setdefault(date, {})["weight_kg"] = round(value, 1)

    df = pd.DataFrame.from_dict(rows, orient="index")
    if not df.empty:
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()

    logger.info("Withings sync: %d distinct days", len(df))
    return df

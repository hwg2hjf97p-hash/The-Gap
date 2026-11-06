"""
Garmin connection (Garmin Connect Developer Program, Health API 2.1 and the OAuth 2.0 PKCE specification).

How it works, in plain terms:
  * A person signs in at Garmin and agrees to share. We exchange the code for a login (access + refresh token) on THIS server,
    never on the phone, and note the person's Garmin user id so we can tell whose data arrives.
  * Garmin then PUSHES each day's numbers to web addresses we configure in Garmin's portal (dailies, sleeps, hrv), plus a
    notice when someone disconnects or changes what they share. We answer 200 at once and file the numbers afterwards.
  * Nothing is fetched on a schedule and no past data is requested (that needs Garmin's Enterprise access).

Licence rules this code is built around (Garmin Connect Developer Program Agreement, Rev H):
  * Section 15.11: Garmin data, and anything derived from it, may not be used to train or build any AI model or AI system unless
    Garmin agrees in writing. So Garmin numbers are kept in their own tables and reach the insights engine and Gappy ONLY when
    GARMIN_AI_ALLOWED is switched on in the environment (it is off unless set). See engine_allowed().
  * Disconnecting in the app, or deleting the account, must also remove the registration at Garmin: delete_registration().
  * Garmin data only arrives at an endpoint we own, and is never passed to anyone else.
  * Garmin's sleep-score wording (EXCELLENT, GOOD, FAIR, POOR) is shown as Garmin gives it.

This module is the logic (sign-in security, reading Garmin's records, calls to Garmin). The routes are in routers/garmin.py and
the sign-in hand-off is in routers/connect.py.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

AUTH_URL = "https://connect.garmin.com/oauth2Confirm"
TOKEN_URL = "https://diauth.garmin.com/di-oauth2-service/oauth/token"
API_BASE = "https://apis.garmin.com/partner-gateway/rest"

# The summaries we keep. Garmin can send many more (epochs, stress details...); anything else is accepted and ignored,
# so only these need switching on in the portal.
KEPT_SUMMARIES = ("dailies", "sleeps", "hrv")
# What a push address in the portal may end with (the three above, plus Garmin's two notices).
PUSH_KINDS = KEPT_SUMMARIES + ("deregistrations", "permissions")

DEFAULT_CAP = 1000  # the approval was for 1,000 users; GARMIN_USER_CAP in the environment overrides it
REQUIRED_PERMISSION = "HEALTH_EXPORT"


# ── Settings from the environment ─────────────────────────────────────────────

def credentials() -> tuple[str, str]:
    return os.getenv("GARMIN_CLIENT_ID", "").strip(), os.getenv("GARMIN_CLIENT_SECRET", "").strip()


def configured() -> bool:
    client_id, secret = credentials()
    return bool(client_id and secret)


def engine_allowed() -> bool:
    """True only when GARMIN_AI_ALLOWED is set to true/1/yes. Until then Garmin numbers never reach the engine or Gappy."""
    return os.getenv("GARMIN_AI_ALLOWED", "").strip().lower() in ("1", "true", "yes")


# ── PKCE and the address Garmin pushes to ─────────────────────────────────────

def pkce_verifier(secret: bytes, nonce: str) -> str:
    """The secret half of PKCE, worked out from a server secret and a one-off value carried in the sign-in state. Whoever sees the
    state (it is in the browser address) still can't work it out. 64 characters from 0-9 a-f, inside Garmin's 43-128 rule."""
    return hmac.new(secret, ("garmin-pkce:" + nonce).encode(), hashlib.sha256).hexdigest()


def pkce_challenge(verifier: str) -> str:
    """base64url(sha256(verifier)) without padding: the public half sent to Garmin."""
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


MIN_PUSH_TOKEN = 24


def push_token() -> str:
    """A secret part of the push address (GARMIN_PUSH_TOKEN in the environment, at least 24 characters). Garmin's pushes carry no
    signature, so this keeps anyone who doesn't know the address from sending us made-up data. Empty (so every push is refused) if
    it isn't set properly."""
    value = os.getenv("GARMIN_PUSH_TOKEN", "").strip()
    return value if len(value) >= MIN_PUSH_TOKEN and value.replace("-", "").replace("_", "").isalnum() else ""


def push_token_ok(given: str) -> bool:
    expected = push_token()
    return bool(expected) and hmac.compare_digest(expected, given or "")


def push_url(base_url: str, kind: str) -> str:
    """The address to paste into Garmin's endpoint settings for one kind of push."""
    return f"{base_url.rstrip('/')}/garmin/push/{push_token()}/{kind}"


# ── Reading Garmin's records ──────────────────────────────────────────────────

def _int(value) -> Optional[int]:
    try:
        if value is None or isinstance(value, bool):
            return None
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _date(value) -> Optional[str]:
    """Garmin's calendarDate as YYYY-MM-DD, or None if it isn't one."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if len(text) == 10 and text[4] == "-" and text[7] == "-" and text.replace("-", "").isdigit():
        return text
    return None


def _minutes(seconds) -> Optional[float]:
    n = _int(seconds)
    return None if n is None or n < 0 else round(n / 60, 1)


def ingest(summary: str, record: dict) -> Optional[tuple[str, str, dict]]:
    """
    One record from Garmin as (garmin user id, local date, what to file). None if it isn't one we keep or is unusable.
    Only fields we use are kept; nothing else from Garmin is stored.
    """
    if summary not in KEPT_SUMMARIES or not isinstance(record, dict):
        return None
    user = record.get("userId")
    day = _date(record.get("calendarDate"))
    if not isinstance(user, str) or not user or day is None:
        return None

    if summary == "dailies":
        patch = {
            "steps": _int(record.get("steps")),
            "resting_hr": _int(record.get("restingHeartRateInBeatsPerMinute")),
            "active_energy": _int(record.get("activeKilocalories")),
            "stress_avg": _int(record.get("averageStressLevel")),
            "body_battery_charged": _int(record.get("bodyBatteryChargedValue")),
        }
        # a stress average of -1 means Garmin did not have enough to work one out
        if patch["stress_avg"] is not None and patch["stress_avg"] < 0:
            patch["stress_avg"] = None
        return user, day, {k: v for k, v in patch.items() if v is not None}

    if summary == "hrv":
        value = _int(record.get("lastNightAvg"))
        return user, day, ({"hrv": value} if value is not None else {})

    # sleeps: a night can have more than one record (a nap, a split night), each updated in place under its own id
    sid = record.get("summaryId")
    if not isinstance(sid, str) or not sid:
        return None
    raw_score = record.get("overallSleepScore")
    score: dict = raw_score if isinstance(raw_score, dict) else {}
    qualifier = score.get("qualifierKey")
    entry = {
        "total_min": _minutes(record.get("durationInSeconds")),  # Garmin's duration leaves out time awake
        "deep_min": _minutes(record.get("deepSleepDurationInSeconds")),
        "light_min": _minutes(record.get("lightSleepDurationInSeconds")),
        "rem_min": _minutes(record.get("remSleepInSeconds")),
        "awake_min": _minutes(record.get("awakeDurationInSeconds")),
        "score": _int(score.get("value")),
        "score_label": qualifier if qualifier in ("EXCELLENT", "GOOD", "FAIR", "POOR") else None,
    }
    return user, day, {"sleeps": {sid[:80]: {k: v for k, v in entry.items() if v is not None}}}


def merge_day(existing: Optional[dict], patch: dict) -> dict:
    """File a record into a day. A newer record replaces an older one for the same thing (Garmin sends updates in full); sleeps are
    kept side by side under their own ids."""
    day = dict(existing or {})
    for key, value in patch.items():
        if key == "sleeps":
            sleeps = dict(day.get("sleeps") or {})
            sleeps.update(value)
            day["sleeps"] = sleeps
        else:
            day[key] = value
    return day


def main_sleep(day: dict) -> Optional[dict]:
    """The night's main sleep: the longest record for that date (naps and fragments are shorter)."""
    sleeps = [s for s in (day.get("sleeps") or {}).values() if isinstance(s, dict) and s.get("total_min")]
    return max(sleeps, key=lambda s: s["total_min"]) if sleeps else None


def day_view(local_date: str, day: dict) -> dict:
    """One day as the app shows it (Garmin's own wording for the sleep score is kept)."""
    sleep = main_sleep(day)
    return {
        "date": local_date,
        "steps": day.get("steps"),
        "resting_hr": day.get("resting_hr"),
        "active_energy": day.get("active_energy"),
        "stress_avg": day.get("stress_avg"),
        "body_battery_charged": day.get("body_battery_charged"),
        "hrv": day.get("hrv"),
        "sleep": sleep,
    }


def frame_rows(rows: list[dict]) -> dict[str, dict]:
    """Stored days as the engine's standard daily columns, keyed by date. Only used when engine_allowed()."""
    out: dict[str, dict] = {}
    for row in rows:
        day = row.get("data") or {}
        local_date = row.get("local_date")
        if not local_date or not isinstance(day, dict):
            continue
        sleep = main_sleep(day)
        cols = {
            "steps": day.get("steps"),
            "resting_hr": day.get("resting_hr"),
            "active_energy": day.get("active_energy"),
            "hrv": day.get("hrv"),
            "sleep_total_min": sleep.get("total_min") if sleep else None,
            "sleep_deep_min": sleep.get("deep_min") if sleep else None,
            "sleep_score": sleep.get("score") if sleep else None,
        }
        cols = {k: v for k, v in cols.items() if v is not None}
        if cols:
            out[str(local_date)] = cols
    return out


# ── Calls to Garmin ───────────────────────────────────────────────────────────

async def _token_request(data: dict) -> dict:
    """The token call. Garmin's document lists the client id and secret as form fields but shows them as a Basic header in its
    examples, so the first is tried and, if Garmin refuses the client, the second."""
    client_id, secret = credentials()
    headers = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(TOKEN_URL, data={**data, "client_id": client_id, "client_secret": secret}, headers=headers)
        if resp.status_code in (400, 401):
            logger.info("Garmin token call with form credentials answered %s; trying a Basic header", resp.status_code)
            resp = await client.post(TOKEN_URL, data=data, headers=headers, auth=(client_id, secret))
        resp.raise_for_status()
        return resp.json()


async def exchange_code(code: str, verifier: str, redirect_uri: str) -> dict:
    return await _token_request({"grant_type": "authorization_code", "code": code, "code_verifier": verifier, "redirect_uri": redirect_uri})


async def refresh_tokens(refresh_token: str) -> dict:
    """A new access token. Garmin also returns a NEW refresh token every time (valid three months), which must replace the old one."""
    return await _token_request({"grant_type": "refresh_token", "refresh_token": refresh_token})


async def _api(method: str, path: str, access_token: str) -> httpx.Response:
    async with httpx.AsyncClient(timeout=20) as client:
        return await client.request(method, f"{API_BASE}/{path}", headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"})


async def fetch_user_id(access_token: str) -> Optional[str]:
    resp = await _api("GET", "user/id", access_token)
    resp.raise_for_status()
    value = (resp.json() or {}).get("userId")
    return value if isinstance(value, str) and value else None


async def fetch_permissions(access_token: str) -> list[str]:
    resp = await _api("GET", "user/permissions", access_token)
    resp.raise_for_status()
    perms = (resp.json() or {}).get("permissions")
    return [p for p in perms if isinstance(p, str)] if isinstance(perms, list) else []


async def delete_registration(access_token: str) -> bool:
    """Tells Garmin this person is no longer connected (required when The Gap lets someone disconnect or delete their account)."""
    try:
        resp = await _api("DELETE", "user/registration", access_token)
        return resp.status_code in (200, 204, 404)
    except Exception as exc:
        logger.warning("Garmin registration delete failed: %s", exc)
        return False


# ── Reading a whole push ──────────────────────────────────────────────────────

def parse_push(summary: str, payload) -> list[tuple[str, str, dict]]:
    """Every usable record in a push for one summary type, as (garmin user id, local date, what to file)."""
    if summary not in KEPT_SUMMARIES or not isinstance(payload, dict):
        return []
    records = payload.get(summary)
    if not isinstance(records, list):
        return []
    out = []
    for record in records[:500]:
        item = ingest(summary, record)
        if item is not None and item[2]:
            out.append(item)
    return out


def parse_deregistrations(payload) -> list[str]:
    """Garmin user ids that have disconnected (from Garmin's side, or because we asked)."""
    rows = payload.get("deregistrations") if isinstance(payload, dict) else None
    return [r["userId"] for r in rows[:500] if isinstance(r, dict) and isinstance(r.get("userId"), str) and r["userId"]] if isinstance(rows, list) else []


def parse_permission_changes(payload) -> list[tuple[str, list[str]]]:
    """(garmin user id, what they now share) for each person whose sharing choices changed."""
    rows = payload.get("userPermissionsChange") if isinstance(payload, dict) else None
    out = []
    if isinstance(rows, list):
        for r in rows[:500]:
            if isinstance(r, dict) and isinstance(r.get("userId"), str) and r["userId"]:
                perms = r.get("permissions")
                out.append((r["userId"], [p for p in perms if isinstance(p, str)] if isinstance(perms, list) else []))
    return out

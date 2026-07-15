"""
Polar data sync — pulls sleep, Nightly Recharge (Polar's recovery metric),
and continuous heart rate via the AccessLink API.

Polar's data model is structurally different from every other provider
here: instead of a date-range GET, you open a transaction, list the URLs
it exposes, fetch each one, then commit the transaction to mark it
delivered. A fetch failure partway through is safe — nothing is lost,
it just reappears next sync — but a successful fetch that isn't
committed will be re-delivered (not duplicated) next time.

Polar access tokens do not expire, so there is no refresh_polar_token —
by design, this provider isn't in daily_sync.py's REFRESH_FUNCS at all.

Polar also requires a polar_user_id (returned as x_user_id at OAuth time)
to build every data URL — something no other provider here needs. Since
Polar tokens never expire, the refresh_token column in user_connections
is otherwise unused for this provider, so we store polar_user_id there
instead rather than adding a new database column. See daily_sync.py for
where that gets read back out.
"""

from __future__ import annotations

import logging

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

POLAR_BASE = "https://www.polaraccesslink.com/v3"


async def _run_transaction(
    client: httpx.AsyncClient,
    user_id: str,
    access_token: str,
    resource_path: str,
    list_key: str,
) -> list[dict]:
    """
    Full lifecycle for one Polar resource type: open transaction, list the
    resource URLs it contains, fetch each one, commit, return the raw
    payloads. Returns [] on any failure or if there's simply no new data
    (204) — never raises, so one resource type failing doesn't take down
    the others (same fault-tolerance pattern as every other provider here).
    """
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    try:
        open_resp = await client.post(
            f"{POLAR_BASE}/users/{user_id}/{resource_path}", headers=headers
        )
        if open_resp.status_code == 204:
            return []  # no new data since last sync — normal, not an error
        open_resp.raise_for_status()
        transaction_id = open_resp.json().get("transaction-id")
        if not transaction_id:
            return []

        list_resp = await client.get(
            f"{POLAR_BASE}/users/{user_id}/{resource_path}/{transaction_id}", headers=headers
        )
        list_resp.raise_for_status()
        urls = list_resp.json().get(list_key, [])

        payloads = []
        for url in urls:
            try:
                item_resp = await client.get(url, headers=headers)
                item_resp.raise_for_status()
                payloads.append(item_resp.json())
            except Exception as exc:
                logger.warning("Polar %s item fetch failed (skipping this one): %s", resource_path, exc)

        # Commit marks this batch delivered — do this even if some
        # individual items failed above, otherwise Polar will keep
        # re-sending the ones that *did* succeed too.
        await client.put(
            f"{POLAR_BASE}/users/{user_id}/{resource_path}/{transaction_id}", headers=headers
        )
        return payloads
    except Exception as exc:
        logger.warning("Polar %s transaction failed (continuing without it): %s", resource_path, exc)
        return []


async def fetch_polar_data(access_token: str, polar_user_id: str) -> pd.DataFrame:
    """
    Fetch Polar sleep, Nightly Recharge, and continuous heart rate data.

    Note the signature differs from every other fetch_*_data function in
    this codebase (access_token, polar_user_id) instead of just
    (access_token, days_back) — Polar's transaction model needs the user
    id to build URLs, and only ever returns data since the last commit
    rather than an arbitrary historical window. daily_sync.py calls this
    one directly rather than through the standard FETCH_FUNCS dispatch.

    NOTE: exact response field names for each resource are best-effort
    from Polar's documented shapes. Same as every other provider built
    this session, the realistic expectation is one log-driven field-name
    correction after the first live connection, not zero.
    """
    rows: dict[str, dict] = {}

    async with httpx.AsyncClient(timeout=30) as client:
        sleep_payloads = await _run_transaction(
            client, polar_user_id, access_token, "sleep-transactions", "sleep"
        )
        for s in sleep_payloads:
            date = s.get("date")
            if not date:
                continue
            rows.setdefault(date, {})
            total_sleep_sec = s.get("total_sleep_time") or s.get("total_sleep_duration")
            if total_sleep_sec is not None:
                rows[date]["sleep_total_min"] = total_sleep_sec / 60
            if s.get("sleep_score") is not None:
                rows[date]["sleep_score"] = s.get("sleep_score")

        recharge_payloads = await _run_transaction(
            client, polar_user_id, access_token, "nightly-recharge-transactions", "nightly-recharge"
        )
        for r in recharge_payloads:
            date = r.get("date")
            if not date:
                continue
            rows.setdefault(date, {})
            # Nightly Recharge's ANS Charge (roughly -4 to +5) is Polar's
            # closest analog to a recovery score — rescaled to a 0-100-ish
            # range so it's at least roughly comparable to Whoop/Oura
            # recovery scores on the same dashboard. This is a rough
            # rescaling for display consistency, not a claim the two
            # providers' scores mean exactly the same thing.
            if r.get("ans_charge") is not None:
                rows[date]["recovery_score"] = round((r["ans_charge"] + 5) / 10 * 100, 1)
            if r.get("heart_rate_avg") is not None:
                rows[date]["resting_hr"] = r.get("heart_rate_avg")

        hr_payloads = await _run_transaction(
            client, polar_user_id, access_token, "continuous-heart-rate-transactions", "heart-rate-data"
        )
        for h in hr_payloads:
            date = h.get("date")
            samples = h.get("heart_rates") or h.get("samples") or []
            if not date or not samples:
                continue
            values = [v for v in samples if isinstance(v, (int, float)) and v > 0]
            if values:
                rows.setdefault(date, {})
                # Overnight low as a rough resting-HR proxy, only if
                # Nightly Recharge above didn't already give us one.
                rows[date].setdefault("resting_hr", min(values))

    df = pd.DataFrame.from_dict(rows, orient="index")
    if not df.empty:
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()

    logger.info("Polar sync: %d distinct days", len(df))
    return df

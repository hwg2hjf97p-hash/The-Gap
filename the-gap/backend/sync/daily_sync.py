"""
Daily sync job — runs for all connected users, fetches fresh data,
runs causal engine, stores updated results in Supabase.

Called via POST /sync/run (protected by SYNC_SECRET env var).
Can also be triggered manually or via a cron job (Railway cron or external).
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

import httpx
import pandas as pd
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse

from auth import get_current_user_id
from db.supabase_client import save_results, get_latest_results
from routers.experiments import get_user_hypotheses
from utils.push import send_push
from utils.nudges import check_proactive_nudge
from routers.interventions import get_active_hypothesis_ids, check_intervention_followups
from sync.whoop_sync import fetch_whoop_data, refresh_whoop_token
from sync.oura_sync import fetch_oura_data, refresh_oura_token
from sync.withings_sync import fetch_withings_data, refresh_withings_token
from sync.polar_sync import fetch_polar_data
from utils.data_cleaning import clean_dataframe
from utils.snapshot import build_snapshot, METRIC_DISPLAY
from causal.engine import run_all_hypotheses, get_experiments_in_progress
from routers.checkin import get_checkin_dataframe
from routers.journal import get_journal_dataframe
from routers.workouts import get_workout_dataframe
from routers.nutrition import get_nutrition_dataframe
from utils.assistant_signals import get_assistant_signal_dataframe
from sync.apple_health_store import get_apple_health_dataframe
from sync.device_calendar_store import get_device_calendar_dataframe
from sync.environment_store import get_environment_dataframe

# Optional imports — don't crash if these aren't ready yet
try:
    from sync.google_sync import fetch_google_calendar_data, refresh_google_token
except ImportError:
    fetch_google_calendar_data = None  # type: ignore
    refresh_google_token = None  # type: ignore

try:
    from sync.strava_sync import fetch_strava_data, refresh_strava_token
except ImportError:
    fetch_strava_data = None  # type: ignore
    refresh_strava_token = None  # type: ignore

try:
    from parsers.google_calendar import merge_calendar_into_health
except ImportError:
    merge_calendar_into_health = None  # type: ignore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sync")

SYNC_SECRET = os.getenv("SYNC_SECRET", "")

REFRESH_FUNCS = {
    "whoop": refresh_whoop_token,
    "oura": refresh_oura_token,
    "google": refresh_google_token,
    "strava": refresh_strava_token,
    "withings": refresh_withings_token,
}

FETCH_FUNCS = {
    "whoop": fetch_whoop_data,
    "oura": fetch_oura_data,
    "strava": fetch_strava_data,
    "withings": fetch_withings_data,
}

CLIENT_ID_ENVS = {
    "whoop": "WHOOP_CLIENT_ID",
    "oura": "OURA_CLIENT_ID",
    "google": "GOOGLE_CLIENT_ID",
    "strava": "STRAVA_CLIENT_ID",
    "withings": "WITHINGS_CLIENT_ID",
}
CLIENT_SECRET_ENVS = {
    "whoop": "WHOOP_CLIENT_SECRET",
    "oura": "OURA_CLIENT_SECRET",
    "google": "GOOGLE_CLIENT_SECRET",
    "strava": "STRAVA_CLIENT_SECRET",
    "withings": "WITHINGS_CLIENT_SECRET",
}


# ── Supabase REST helpers ─────────────────────────────────────────────────────

def _supabase_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _supabase_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


async def _supabase_get(table: str, params: dict) -> list[dict]:
    """Generic async GET for Supabase REST."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            _supabase_url(table),
            headers=_supabase_headers(),
            params=params,
        )
        resp.raise_for_status()
        return resp.json() or []


async def _persist_metric_history(user_id: str, df: pd.DataFrame) -> None:
    """
    Best-effort — persists each METRIC_DISPLAY column's daily values so the
    app can show a real "since you started" chart per metric (see
    routers/metric_history.py), not just the last 7 days kept in the
    snapshot. Runs every sync; upserts are idempotent so re-sending
    already-seen dates is harmless, just slightly wasteful — fine at
    current scale, worth trimming to only-new-dates if this ever gets
    expensive. Never raises — a failure here must never break the actual
    insight computation that follows it.
    """
    # Beyond the METRIC_DISPLAY columns (shown as cards), also persist
    # sleep_deep_min: it's an outcome column several hypotheses use, but
    # has no display card of its own — without this, an "I'll try this"
    # intervention tracking a sleep_deep_min outcome would have no history
    # to compute a baseline/current comparison from (see
    # routers/interventions.py's base_metric()).
    history_columns = list(METRIC_DISPLAY) + ["sleep_deep_min"]

    try:
        records = []
        for col in history_columns:
            if col not in df.columns:
                continue
            for date, value in df[col].dropna().items():
                records.append({
                    "user_id": user_id,
                    "date": date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)[:10],
                    "metric": col,
                    "value": float(value),
                })
        if not records:
            return
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                _supabase_url("metric_history"),
                headers={**_supabase_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                params={"on_conflict": "user_id,date,metric"},
                json=records,
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("Persisting metric history failed for %s (continuing anyway): %s", user_id[:8], exc)


async def _supabase_patch(table: str, params: dict, payload: dict) -> None:
    """Generic async PATCH for Supabase REST."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.patch(
            _supabase_url(table),
            headers=_supabase_headers(prefer="return=minimal"),
            params=params,
            json=payload,
        )
        resp.raise_for_status()


# ── Sync routes ───────────────────────────────────────────────────────────────

@router.post("/run")
async def run_sync(x_sync_secret: str = Header(default="")):
    """
    Run the daily sync for all connected users.
    Protected by X-Sync-Secret header.
    """
    if SYNC_SECRET and x_sync_secret != SYNC_SECRET:
        raise HTTPException(status_code=403, detail="Invalid sync secret.")

    # Get all active connections via REST (not supabase-py)
    try:
        connections = await _supabase_get(
            "user_connections",
            {"is_active": "eq.true", "select": "*"},
        )
    except Exception as exc:
        logger.error("Failed to fetch connections: %s", exc)
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}")

    logger.info("Daily sync: %d active connections", len(connections))

    results = []
    # Group by user_id
    users: dict[str, list[dict]] = {}
    for conn in connections:
        users.setdefault(conn["user_id"], []).append(conn)

    for user_id, user_connections in users.items():
        result = await _sync_user(user_id, user_connections)
        results.append(result)

    return JSONResponse(content={
        "synced_users": len(results),
        "results": results,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


async def _sync_user(user_id: str, connections: list[dict]) -> dict:
    """Sync one user — fetch all their data, run causal engine, save results."""
    t0 = time.perf_counter()
    health_df = None
    calendar_df = None
    providers_synced = []

    for conn in connections:
        provider = conn["provider"]
        access_token = conn.get("access_token", "").strip()
        refresh_token = conn.get("refresh_token", "").strip()
        expires_at = conn.get("expires_at") or 0

        logger.info("SYNC_USER provider=%s user=%s token_len=%d expires_at=%s",
                    provider, user_id[:8], len(access_token), expires_at)

        # Only refresh if token is actually expired (not just 0)
        # expires_at=0 means we don't know — try with existing token first
        token_expired = expires_at > 0 and time.time() > (expires_at - 300)
        if token_expired:
            logger.info("TOKEN_EXPIRED refreshing %s/%s", user_id[:8], provider)
            refresh_func = REFRESH_FUNCS.get(provider)
            if refresh_func and refresh_token:
                try:
                    client_id = os.getenv(CLIENT_ID_ENVS.get(provider, ""), "")
                    client_secret = os.getenv(CLIENT_SECRET_ENVS.get(provider, ""), "")
                    new_tokens = await refresh_func(refresh_token, client_id, client_secret)
                    access_token = new_tokens.get("access_token", access_token)
                    # Whoop's OAuth (Ory Hydra) issues single-use refresh tokens:
                    # every refresh returns a NEW refresh_token and immediately
                    # invalidates the old one. Not saving it here meant the very
                    # next refresh attempt (even a background/cron one) would
                    # permanently kill the connection — matching exactly what
                    # was happening before this fix.
                    new_refresh_token = new_tokens.get("refresh_token", refresh_token)
                    await _supabase_patch(
                        "user_connections",
                        {"user_id": f"eq.{user_id}", "provider": f"eq.{provider}"},
                        {
                            "access_token": access_token,
                            "refresh_token": new_refresh_token,
                            "expires_at": int(time.time()) + new_tokens.get("expires_in", 3600),
                        },
                    )
                    logger.info("TOKEN_REFRESHED %s/%s", user_id[:8], provider)
                except Exception as exc:
                    logger.error("TOKEN_REFRESH_FAILED %s/%s: %s — continuing with old token",
                                 user_id[:8], provider, exc)
                    # Don't skip — try with the existing token anyway

        # Fetch data
        try:
            logger.info("FETCH_START provider=%s user=%s", provider, user_id[:8])
            if provider == "google" and fetch_google_calendar_data is not None:
                calendar_df = await fetch_google_calendar_data(access_token)
                logger.info("FETCH_DONE provider=google rows=%s",
                            len(calendar_df) if calendar_df is not None else 0)
            elif provider == "whoop":
                fetched = await fetch_whoop_data(access_token)
                logger.info("FETCH_DONE provider=whoop rows=%d", len(fetched) if fetched is not None else 0)
                if fetched is not None and not fetched.empty:
                    health_df = fetched if health_df is None else health_df.combine_first(fetched)
                    providers_synced.append(provider)
            elif provider == "oura":
                fetched = await fetch_oura_data(access_token)
                logger.info("FETCH_DONE provider=oura rows=%d", len(fetched) if fetched is not None else 0)
                if fetched is not None and not fetched.empty:
                    health_df = fetched if health_df is None else health_df.combine_first(fetched)
                    providers_synced.append(provider)
            elif provider == "strava" and fetch_strava_data is not None:
                fetched = await fetch_strava_data(access_token)
                logger.info("FETCH_DONE provider=strava rows=%d", len(fetched) if fetched is not None else 0)
                if fetched is not None and not fetched.empty:
                    health_df = fetched if health_df is None else health_df.combine_first(fetched)
                    providers_synced.append(provider)
            elif provider == "withings":
                fetched = await fetch_withings_data(access_token)
                logger.info("FETCH_DONE provider=withings rows=%d", len(fetched) if fetched is not None else 0)
                if fetched is not None and not fetched.empty:
                    health_df = fetched if health_df is None else health_df.combine_first(fetched)
                    providers_synced.append(provider)
            elif provider == "polar":
                # Polar's user_id was stashed in refresh_token at connect time
                # (see routers/connect.py) since Polar tokens never expire and
                # that field would otherwise go unused for this provider.
                polar_user_id = refresh_token
                if not polar_user_id:
                    logger.error("Polar connection missing polar_user_id — skipping this sync")
                else:
                    fetched = await fetch_polar_data(access_token, polar_user_id)
                    logger.info("FETCH_DONE provider=polar rows=%d", len(fetched) if fetched is not None else 0)
                    if fetched is not None and not fetched.empty:
                        health_df = fetched if health_df is None else health_df.combine_first(fetched)
                        providers_synced.append(provider)

            # Update last_synced_at
            await _supabase_patch(
                "user_connections",
                {"user_id": f"eq.{user_id}", "provider": f"eq.{provider}"},
                {"last_synced_at": datetime.now(timezone.utc).isoformat()},
            )

        except Exception as exc:
            logger.error("FETCH_FAILED provider=%s user=%s error=%s", provider, user_id[:8], exc)

    logger.info("SYNC_DATA_COLLECTED user=%s health_df_rows=%s providers=%s elapsed=%.1fs",
                user_id[:8],
                len(health_df) if health_df is not None else 0,
                providers_synced,
                time.perf_counter() - t0)

    # Merge Apple Health — stored persistently (see sync/apple_health_store.py)
    # specifically so it survives across syncs regardless of which data
    # source triggered this particular run, rather than being silently
    # overwritten every time a different source syncs most recently.
    try:
        apple_df = await get_apple_health_dataframe(user_id)
        if apple_df is not None and not apple_df.empty:
            apple_df.index = pd.to_datetime(apple_df.index)
            if health_df is None:
                health_df = apple_df
            else:
                health_df.index = pd.to_datetime(health_df.index)
                health_df = health_df.combine_first(apple_df)
            if "apple_health" not in providers_synced:
                providers_synced.append("apple_health")
    except Exception as exc:
        logger.warning("Apple Health merge failed (continuing without it): %s", exc)

    # Merge weather/commute data — same pattern as Apple Health above.
    # A user with only environment data and no health data yet still
    # shouldn't hit this merge (weather alone can't produce insights),
    # but if any health_df already exists, this fills in additional
    # columns for it.
    try:
        env_df = await get_environment_dataframe(user_id)
        if env_df is not None and not env_df.empty and health_df is not None:
            env_df.index = pd.to_datetime(env_df.index)
            health_df.index = pd.to_datetime(health_df.index)
            health_df = health_df.combine_first(env_df)
            if "environment" not in providers_synced:
                providers_synced.append("environment")
    except Exception as exc:
        logger.warning("Environment data merge failed (continuing without it): %s", exc)

    if health_df is None or health_df.empty:
        return {"user_id": user_id, "status": "no_data", "elapsed": round(time.perf_counter() - t0, 1)}

    # Merge in on-device Calendar (EventKit) data — fills gaps for users
    # who never completed Google's OAuth verification/test-user flow, or
    # who only use calendars added at the iOS system level. Google
    # Calendar keeps priority for any day it already has data for;
    # device data only fills in what Google doesn't have.
    try:
        device_cal_df = await get_device_calendar_dataframe(user_id)
        if device_cal_df is not None and not device_cal_df.empty:
            device_cal_df.index = pd.to_datetime(device_cal_df.index)
            if calendar_df is None or calendar_df.empty:
                calendar_df = device_cal_df
            else:
                calendar_df.index = pd.to_datetime(calendar_df.index)
                calendar_df = calendar_df.combine_first(device_cal_df)
            if "device_calendar" not in providers_synced:
                providers_synced.append("device_calendar")
    except Exception as exc:
        logger.warning("Device calendar merge failed (continuing without it): %s", exc)

    # Merge calendar if available
    if calendar_df is not None and not calendar_df.empty and merge_calendar_into_health is not None:
        health_df = merge_calendar_into_health(health_df, calendar_df)

    # Merge daily check-ins (alcohol, caffeine, stress score) — this was
    # collected all along but never actually reached the causal engine
    # until now, so hypotheses like alcohol_hrv had no data to run against.
    try:
        health_df.index = pd.to_datetime(health_df.index)
        checkin_df = get_checkin_dataframe(user_id)
        if checkin_df is not None and not checkin_df.empty:
            checkin_df.index = pd.to_datetime(checkin_df.index)
            # REAL BUG FIXED HERE: "left" join meant a Quick Entry logged
            # on a day with no wearable data at all (no Whoop/Apple
            # Health/etc that day) was silently dropped from the entire
            # analysis — not deprioritized, just invisible, since
            # health_df's own date index determined which days could
            # exist at all. "outer" keeps every date from either side.
            health_df = health_df.join(checkin_df, how="outer")
    except Exception as exc:
        logger.warning("Check-in merge failed (continuing without it): %s", exc)

    # Merge planned/logged workouts (workout_completed_flag) — same outer-join
    # pattern as check-ins, new column name so no collision risk.
    try:
        workout_df = get_workout_dataframe(user_id)
        if workout_df is not None and not workout_df.empty:
            workout_df.index = pd.to_datetime(workout_df.index)
            health_df = health_df.join(workout_df, how="outer")
    except Exception as exc:
        logger.warning("Workout merge failed (continuing without it): %s", exc)

    # Merge in-app food/water logs. They share column names with Apple
    # Health nutrition (dietary_energy, protein_g, carbs_g, fat_g), so
    # combine_first with the in-app frame FIRST means a day logged in the app
    # wins over Apple Health's number for that same day (no double counting
    # for people who log in both places) while Apple Health still fills any
    # day with no in-app log. water_ml and last_meal_hour are new columns.
    try:
        nutrition_df = get_nutrition_dataframe(user_id)
        if nutrition_df is not None and not nutrition_df.empty:
            nutrition_df.index = pd.to_datetime(nutrition_df.index)
            health_df = nutrition_df.combine_first(health_df)
    except Exception as exc:
        logger.warning("Nutrition merge failed (continuing without it): %s", exc)

    # Merge Quick Entry signals (mood, stress, travel, illness, conflict)
    try:
        journal_df = await get_journal_dataframe(user_id)
        if journal_df is not None and not journal_df.empty:
            journal_df.index = pd.to_datetime(journal_df.index)
            # Same fix as checkin_df above — outer join so a journal
            # entry on a wearable-free day still makes it into analysis.
            health_df = health_df.join(journal_df, how="outer")
    except Exception as exc:
        logger.warning("Journal merge failed (continuing without it): %s", exc)

    # Merge assistant-question signals (same columns as journal_df above —
    # mood_score, stress_event, etc.) using combine_first rather than
    # .join(), since .join() raises on overlapping column names. This
    # fills in a day only where the journal didn't already cover it: an
    # offhand question someone asked Gappy is a weaker signal than a
    # deliberate journal entry, so it only acts as a gap-filler, never an
    # override, for the exact same existing hypotheses.
    try:
        assistant_df = await get_assistant_signal_dataframe(user_id)
        if assistant_df is not None and not assistant_df.empty:
            assistant_df.index = pd.to_datetime(assistant_df.index)
            health_df = health_df.combine_first(assistant_df)
    except Exception as exc:
        logger.warning("Assistant signal merge failed (continuing without it): %s", exc)

    # REAL BUG FIXED HERE: outer joins (checkin/journal/calendar above)
    # don't guarantee the resulting index stays sorted by date — a new
    # date introduced by one of those joins can land anywhere in the
    # frame, not necessarily at the end. build_snapshot's "latest
    # reading" for each metric relies on the *last row by position*
    # (clean.iloc[-1]) actually being the most recent date — if the
    # frame isn't sorted, that can silently pull from the wrong day
    # entirely. Sorting once here, right before anything downstream
    # depends on row order, fixes it regardless of which merge caused
    # the disorder.
    health_df = health_df.sort_index()

    # Run causal engine
    try:
        logger.info("ENGINE_START user=%s days=%d", user_id[:8], len(health_df))
        df = clean_dataframe(health_df)
        await _persist_metric_history(user_id, df)
        extra_hypotheses = await get_user_hypotheses(user_id)
        insights = run_all_hypotheses(df, extra_hypotheses)
        insights_dicts = [i.to_dict() for i in insights]
        snapshot = build_snapshot(df)
        experiments = get_experiments_in_progress(df, extra_hypotheses)
        logger.info("ENGINE_DONE user=%s insights=%d experiments_in_progress=%d elapsed=%.1fs",
                    user_id[:8], len(insights_dicts), len(experiments), time.perf_counter() - t0)

        # Diff against the previous run's insights *before* overwriting them,
        # so a discovery push notification only fires for a hypothesis that
        # is genuinely newly confirmed this run — not one that was already
        # confirmed last time and simply reappears.
        try:
            previous = get_latest_results(user_id)
            # Only previously CONFIRMED insights count as already-known: a
            # hypothesis that was an early signal last time and has now
            # graduated to confirmed is exactly what should trigger a push.
            previous_ids = {
                i["hypothesis_id"]
                for i in (previous or {}).get("insights") or []
                if i.get("confidence") != "weak"
            }
        except Exception as exc:
            logger.warning("Could not load previous results for discovery diff (%s): %s", user_id[:8], exc)
            previous_ids = set()

        # Early signals (confidence "weak") are never pushed — with this many
        # hypotheses running, announcing every faint hint would be mostly noise.
        newly_confirmed = [
            i for i in insights_dicts
            if i["hypothesis_id"] not in previous_ids and i.get("confidence") != "weak"
        ]

        session_id = save_results(
            user_id=user_id,
            data_source=",".join(providers_synced),
            data_period_days=len(df),
            insights=insights_dicts,
            snapshot=snapshot,
            experiments=experiments,
        )

        # The push deliberately doesn't say WHAT was found: a new discovery
        # arrives sealed and the finding is revealed when it's opened in the
        # app. One push for the batch, however many were found this run.
        if newly_confirmed:
            count = len(newly_confirmed)
            await send_push(
                user_id,
                title="You've unlocked a discovery" if count == 1 else f"You've unlocked {count} discoveries",
                body="Something new about your body is waiting. Tap to open it.",
                data={"kind": "discovery", "hypothesis_id": newly_confirmed[0]["hypothesis_id"], "session_id": session_id},
            )

        # Best-effort — proactive "expect this today" nudges and intervention
        # follow-ups. Neither should ever be able to fail this sync run.
        try:
            active_ids = await get_active_hypothesis_ids(user_id)
            await check_proactive_nudge(user_id, df, insights_dicts, active_ids)
        except Exception as exc:
            logger.warning("Proactive nudge step failed for %s: %s", user_id[:8], exc)

        try:
            await check_intervention_followups(user_id)
        except Exception as exc:
            logger.warning("Intervention follow-up step failed for %s: %s", user_id[:8], exc)

        return {
            "user_id": user_id,
            "status": "success",
            "insights": len(insights_dicts),
            "days": len(df),
            "session_id": session_id,
            "elapsed": round(time.perf_counter() - t0, 1),
        }
    except Exception as exc:
        logger.error("ENGINE_FAILED user=%s error=%s", user_id[:8], exc)
        return {"user_id": user_id, "status": "engine_error", "error": str(exc)}


@router.post("/user")
async def sync_single_user(user_id: str = Depends(get_current_user_id)):
    """
    Immediately fetch data + run causal engine for one user.
    Called by the frontend "Run analysis now" button right after OAuth connect,
    and by the onboarding flow after connecting a provider.
    """
    logger.info("Manual sync triggered for user: %s", user_id)

    # Fetch all active connections for this user
    try:
        connections = await _supabase_get(
            "user_connections",
            {
                "user_id": f"eq.{user_id}",
                "is_active": "eq.true",
                "select": "*",
            },
        )
    except Exception as exc:
        logger.error("Could not fetch connections for %s: %s", user_id, exc)
        raise HTTPException(status_code=503, detail="Database unavailable — please try again.")

    if not connections:
        raise HTTPException(
            status_code=404,
            detail="No connected devices found. Please connect Whoop or Oura first.",
        )

    result = await _sync_user(user_id, connections)

    if result.get("status") == "no_data":
        raise HTTPException(
            status_code=422,
            detail="Connected but no data retrieved yet. Your device may need a sync — open Whoop/Oura app and wait a minute, then try again.",
        )

    if result.get("status") == "engine_error":
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {result.get('error', 'unknown error')}",
        )

    return JSONResponse(content={
        "session_id": result.get("session_id"),
        "insights": result.get("insights", 0),
        "days": result.get("days", 0),
        "status": result.get("status"),
    })

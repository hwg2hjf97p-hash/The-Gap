"""
Readiness — "how hard should I train today?", answered from the user's own
recovery data compared with their own recent baseline (never a population
average). Reads the metric_history table every sync already fills.

Deliberately simple and transparent rather than a black-box score: if the
wearable gives a recovery score (Whoop's 0-100), its own bands decide the
level; otherwise it's today's HRV and resting heart rate against this
person's 30-day normal. Short sleep can pull a "high" down a notch. The
reasons behind the level are always returned so the app can show them.
This is general guidance, not medical advice.
"""

from __future__ import annotations

import logging
import math
import os
from datetime import date, datetime, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from auth import get_current_user_id
from utils.weekday_baseline import weekday_baseline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/readiness", tags=["readiness"])

BASELINE_DAYS = 30
MIN_BASELINE_POINTS = 10
MAX_STALE_DAYS = 2  # a reading older than this isn't "today's" any more

SUGGESTIONS = {
    "high": "Good day to push. If you've got a hard session planned, this is the day for it.",
    "moderate": "Train as planned, but keep it controlled — leave a rep or two in reserve.",
    "low": "Take it easy today: mobility, a walk, or a light session. Save the hard work for when your recovery bounces back.",
}


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers() -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _latest_vs_baseline(series: list[tuple[date, float]], today: date) -> dict | None:
    """Latest reading (if recent enough) plus the mean/sd of the prior 30 days."""
    if not series:
        return None
    latest_date, latest = series[-1]
    if (today - latest_date).days > MAX_STALE_DAYS:
        return None
    prior = [v for d, v in series[:-1] if 0 < (latest_date - d).days <= BASELINE_DAYS]
    info = {"date": latest_date, "latest": latest, "n": len(prior), "mean": None, "sd": None, "weekday": None}
    # Prefer "your usual for this weekday": someone who sleeps in on Sundays and
    # works on Mondays shouldn't look low every Monday. Needs a few earlier
    # same-weekday readings; otherwise the 30-day average is used as before.
    same_day = weekday_baseline(series[:-1], latest_date)
    if same_day:
        mean, sd = same_day["mean"], same_day["sd"]
        info["weekday"] = same_day["weekday"]
        info["mean"], info["sd"] = mean, max(sd, abs(mean) * 0.05, 1e-6)
    elif len(prior) >= MIN_BASELINE_POINTS:
        mean = sum(prior) / len(prior)
        sd = math.sqrt(sum((v - mean) ** 2 for v in prior) / (len(prior) - 1))
        # A very steady baseline would make a tiny wobble look dramatic;
        # never let the spread fall below 5% of the mean.
        info["mean"], info["sd"] = mean, max(sd, abs(mean) * 0.05, 1e-6)
    return info


def _baseline_name(info: dict) -> str:
    return f"usual {info['weekday']}" if info.get("weekday") else "30-day average"


async def compute_readiness(user_id: str, today: date) -> dict:
    """Readiness for `today` (the user's own local date). Shared by the
    Readiness card endpoint and the overall health suggestion
    (routers/health_plan.py). Always returns a dict; level is "unknown" when
    there isn't enough data. `signals` holds the raw comparisons (percent
    above/below this person's normal) so callers can reason about them
    without parsing the reason strings."""
    since = (today - timedelta(days=70)).isoformat()  # 8 weeks, for the same-weekday comparison
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                _sb_url("metric_history"),
                headers=_sb_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "metric": "in.(hrv,resting_hr,recovery_score,sleep_total_min)",
                    "date": f"gte.{since}",
                    "select": "date,metric,value",
                    "order": "date.asc",
                    "limit": "2000",
                },
            )
            resp.raise_for_status()
            rows = resp.json() or []
    except Exception as exc:
        logger.error("Readiness fetch failed for %s: %s", user_id[:8], exc)
        return {"level": "unknown", "reasons": [], "suggestion": None, "signals": {}, "message": "Couldn't check your readiness right now."}

    series: dict[str, list[tuple[date, float]]] = {}
    for r in rows:
        series.setdefault(r["metric"], []).append((datetime.strptime(r["date"], "%Y-%m-%d").date(), float(r["value"])))

    hrv = _latest_vs_baseline(series.get("hrv", []), today)
    rhr = _latest_vs_baseline(series.get("resting_hr", []), today)
    recovery = _latest_vs_baseline(series.get("recovery_score", []), today)
    sleep = _latest_vs_baseline(series.get("sleep_total_min", []), today)

    reasons: list[str] = []
    z_scores: list[float] = []
    signals: dict = {}
    if hrv and hrv["mean"] is not None:
        z_scores.append((hrv["latest"] - hrv["mean"]) / hrv["sd"])
        pct = round((hrv["latest"] - hrv["mean"]) / hrv["mean"] * 100)
        signals["hrv_pct"] = pct
        reasons.append(f"HRV {abs(pct)}% {'above' if pct >= 0 else 'below'} your {_baseline_name(hrv)}")
    if rhr and rhr["mean"] is not None:
        z_scores.append(-(rhr["latest"] - rhr["mean"]) / rhr["sd"])  # lower resting HR is better
        diff = round(rhr["latest"] - rhr["mean"])
        signals["rhr_diff"] = diff
        reasons.append(f"Resting heart rate {abs(diff)} bpm {'above' if diff >= 0 else 'below'} your usual")

    level = None
    score = None
    if recovery:
        score = round(recovery["latest"])
        signals["recovery_score"] = score
        level = "high" if score >= 67 else "moderate" if score >= 34 else "low"
        reasons.insert(0, f"Recovery score {score}%")
    elif z_scores:
        z_avg = sum(z_scores) / len(z_scores)
        level = "high" if z_avg >= 0.3 else "low" if z_avg <= -0.7 else "moderate"

    if level is None:
        return {
            "level": "unknown",
            "reasons": [],
            "suggestion": None,
            "signals": signals,
            "message": "Not enough recent data yet — about two weeks of readings lets us compare today with your normal.",
        }

    if sleep:
        hours = sleep["latest"] / 60
        signals["sleep_hours"] = round(hours, 1)
        if sleep["mean"] is not None and sleep["mean"] > 0:
            signals["sleep_pct"] = round((sleep["latest"] - sleep["mean"]) / sleep["mean"] * 100)
        reasons.append(f"Slept {hours:.1f} h")
        if hours < 6 and level == "high":
            level = "moderate"

    return {
        "level": level,
        "score": score,
        "reasons": reasons[:4],
        "signals": signals,
        "suggestion": SUGGESTIONS[level],
        "as_of": (recovery or hrv or rhr)["date"].isoformat() if (recovery or hrv or rhr) else None,
    }


@router.get("/today")
async def readiness_today(user_id: str = Depends(get_current_user_id), local_date: Optional[str] = None) -> JSONResponse:
    # The phone's own calendar date when given: the server's clock is UTC,
    # which is a day behind for part of every day in Queensland.
    today = date.today()
    if local_date:
        try:
            today = datetime.strptime(local_date, "%Y-%m-%d").date()
        except ValueError:
            pass
    return JSONResponse(content=await compute_readiness(user_id, today))

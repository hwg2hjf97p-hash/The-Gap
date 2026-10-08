"""
"Test it on yourself": a 14-day personal test started from a research card.

The person tries one everyday habit for 14 days. Afterwards their reading
(for example sleep) over those 14 days is compared with the 14 days before.

This is deliberately modest. Two 14-day windows cannot show that the habit
caused a change: the season, a busy week or a cold can move a reading too. So
the result is described only as a clear change, a possible small change or no
clear change, judged against how much that reading normally varies for the
person, and it always says it is a hint and not proof. The full causal engine
needs about 30 days of readings, so it is not used here.
"""

from __future__ import annotations

import logging
import math
import os
from datetime import date, timedelta
from typing import Optional

import httpx

from utils.goal_catalog import GoalMetric, get_metric
from utils.goals import fetch_points, fmt
from utils.local_time import user_today

logger = logging.getLogger(__name__)

BASELINE_DAYS = 14
MIN_BEFORE = 5
MIN_AFTER = 7
CLEAR_T = 2.0
POSSIBLE_T = 1.3
CLEAR_SD_FRACTION = 0.5   # a clear change is also at least this fraction of the person's usual day-to-day spread

CAVEAT = "A single 14-day test can't rule out other things changing at the same time, so treat it as a hint, not proof."


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _sd(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def classify_change(before: list[float], after: list[float]) -> dict:
    """
    Compares the two windows. state is one of:
      not_enough_data | clear | possible | none
    """
    out = {"state": "not_enough_data", "before_mean": None, "after_mean": None, "difference": None, "t": None, "n_before": len(before), "n_after": len(after)}
    if len(before) < MIN_BEFORE or len(after) < MIN_AFTER:
        return out
    m1, m2 = _mean(before), _mean(after)
    s1, s2 = _sd(before), _sd(after)
    diff = m2 - m1
    se = math.sqrt(s1 ** 2 / len(before) + s2 ** 2 / len(after))
    out.update({"before_mean": m1, "after_mean": m2, "difference": diff})
    if se <= 1e-9:
        out["state"] = "clear" if abs(diff) > 1e-9 else "none"
        return out
    t = diff / se
    out["t"] = round(t, 2)
    if abs(t) >= CLEAR_T and abs(diff) >= CLEAR_SD_FRACTION * s1:
        out["state"] = "clear"
    elif abs(t) >= POSSIBLE_T:
        out["state"] = "possible"
    else:
        out["state"] = "none"
    return out


def _display(value: float, metric: GoalMetric) -> float:
    v = value * (7 if metric.per_week else 1)
    return v / metric.scale


def _unit(metric: GoalMetric) -> str:
    return metric.unit if metric.unit.startswith("/") else f" {metric.unit}"


def result_text(treatment: str, metric: GoalMetric, result: dict, days: int = 14) -> str:
    """The result in plain words, in the metric's own units."""
    if result["state"] == "not_enough_data":
        return (
            f"We couldn't say how {treatment.lower()} went: there weren't enough days of {metric.label.lower()} "
            f"({result['n_after']} in the test, {result['n_before']} before). " + CAVEAT
        )
    before = fmt(_display(result["before_mean"], metric), metric.decimals)
    after = fmt(_display(result["after_mean"], metric), metric.decimals)
    unit = _unit(metric)
    rose = result["difference"] > 0
    move = "higher" if rose else "lower"
    base = f"Over the {days} days, your {metric.label.lower()} averaged {after}{unit}, compared with {before}{unit} in the {BASELINE_DAYS} days before."
    if result["state"] == "clear":
        verdict = f" That is a clear change ({move}) compared with how much it normally varies for you."
    elif result["state"] == "possible":
        verdict = f" That is a possible small change ({move}), close to how much it normally varies for you."
    else:
        verdict = " That is no clear change compared with how much it normally varies for you."
    return base + verdict + " " + CAVEAT


async def evaluate_experiment(user_id: str, metric_key: str, started: date, days: int) -> dict:
    """Fetches the readings and compares the days of the test with the days before it."""
    points = await fetch_points(user_id, metric_key, started - timedelta(days=BASELINE_DAYS))
    before = [v for d, v in points if started - timedelta(days=BASELINE_DAYS) <= d < started]
    after = [v for d, v in points if started <= d < started + timedelta(days=days)]
    return classify_change(before, after)


async def check_card_experiments(user_id: str) -> list[dict]:
    """
    Finishes any "test it on yourself" experiment whose days are up: works out
    the result, marks it followed up and posts it to the feed. Never raises.
    """
    from utils.feed import create_feed_item

    finished: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                _sb_url("active_interventions"),
                headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "status": "eq.active", "hypothesis_id": "like.card:*", "select": "*"},
            )
            resp.raise_for_status()
            active = resp.json() or []
        if not active:
            return []
        today = await user_today(user_id)
        for iv in active:
            try:
                started = date.fromisoformat(str(iv["started_date"])[:10])
                days = int(iv.get("follow_up_days") or 14)
                if today < started + timedelta(days=days):
                    continue
                metric = get_metric(iv["outcome_col"])
                if metric is None:
                    continue
                result = await evaluate_experiment(user_id, metric.key, started, days)
                improved: Optional[bool] = None
                if result["state"] in ("clear", "possible") and metric.default_direction in ("increase", "decrease"):
                    improved = (result["difference"] > 0) == (metric.default_direction == "increase")
                async with httpx.AsyncClient(timeout=15) as client:
                    moved = await client.patch(
                        _sb_url("active_interventions"),
                        headers=_sb_headers("return=representation"),
                        params={"id": f"eq.{iv['id']}", "status": "eq.active"},
                        json={
                            "status": "followed_up",
                            "result_value": None if result["after_mean"] is None else round(_display(result["after_mean"], metric), 3),
                            "result_improved": improved,
                        },
                    )
                    moved.raise_for_status()
                    if not (moved.json() or []):
                        continue  # another check already finished it
                text = result_text(iv["treatment_label"], metric, result, days)
                await create_feed_item(
                    user_id,
                    kind="experiment_result",
                    title=f"Your {days}-day test: {iv['treatment_label']}",
                    body=text,
                    card_id=iv.get("card_id"),
                    local_date=today,
                    payload={"metric_key": metric.key, "state": result["state"], "difference": result["difference"], "intervention_id": iv["id"]},
                )
                finished.append(iv)
                logger.info("CARD_EXPERIMENT_DONE user=%s metric=%s state=%s", user_id[:8], metric.key, result["state"])
            except Exception as exc:
                logger.warning("Card experiment follow-up failed for %s/%s: %s", user_id[:8], iv.get("id"), exc)
    except Exception as exc:
        logger.warning("Card experiment check failed for %s: %s", user_id[:8], exc)
    return finished

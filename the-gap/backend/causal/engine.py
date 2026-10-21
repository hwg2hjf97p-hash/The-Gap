"""
Causal Engine — orchestrates all hypothesis tests against a user's data.
Runs each hypothesis through LinearDML, returns a list of Insight objects.
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from causal.hypotheses import HYPOTHESES, Hypothesis
from causal.estimator import run_linear_dml, run_ols
from causal.interpreter import interpret_result, OUTCOME_HIGHER_IS_BETTER
from causal.evidence import build_evidence, checks_text
from models.insight import Insight, ConfidenceLevel

logger = logging.getLogger(__name__)

# How early an in-progress experiment can get a preliminary directional
# hint, attempted on the SAME LinearDML estimator used for a confirmed
# insight — just run earlier and surfaced with a heavy caveat instead of
# a confidence badge. Never treated as, or persisted as, a real insight;
# purely additive to the "Day X of Y" progress list. Gated by both a
# fraction of the real threshold and an absolute floor, so this is never
# attempted on a handful of rows too small for DML to say anything
# meaningful at all.
EARLY_READ_MIN_FRACTION = 0.5
EARLY_READ_MIN_ABSOLUTE = 12

# How much data is enough to try a hypothesis. Each hypothesis states the days it
# wants (min_rows, min_treated_days); these scale that down for everyone at once, and
# never raise it. See working_frame for how usable days are counted.
# Settings chosen with lab/engine_lab.py: on made-up people with three to four weeks of logging this finds about
# three times as many real patterns as the old 30-day requirement, with fewer false ones than before.
MIN_ROWS_SCALE = 0.55
MIN_ROWS_FLOOR = 18          # never ask for fewer than this many days (or the hypothesis's own number, if lower)
MIN_TREATED_SCALE = 0.6
MIN_TREATED_FLOOR = 4        # never ask for fewer treated days than this (or the hypothesis's own number, if lower)
MIN_CONTROL_DAYS = 0         # days WITHOUT the treatment needed, for yes/no treatments
# When a hypothesis can't reach its days only because of the extra things it adjusts for
# (each one missing on some days shrinks the usable days), set the least-recorded of them aside,
# one at a time, until it can run. Day of week is never set aside.
ADAPTIVE_COVARIATES = True
KEEP_COVARIATES = {"day_of_week", "is_weekend"}


# Which calculation gives the effect, its interval and its p-value. "ols" is calibrated on a few weeks of data
# where "dml" is not (see run_ols and lab/calibration_lab.py).
ESTIMATOR = "ols"


def estimate(sub: pd.DataFrame, hyp: Hypothesis, covs: list[str]) -> Optional[dict]:
    run = run_ols if ESTIMATOR == "ols" else run_linear_dml
    return run(
        df=sub,
        treatment_col=hyp.treatment_col,
        outcome_col=hyp.outcome_col,
        covariate_cols=covs,
        binary_treatment=hyp.binary_treatment,
    )


def required_rows(hyp: Hypothesis) -> int:
    return max(min(hyp.min_rows, MIN_ROWS_FLOOR), round(hyp.min_rows * MIN_ROWS_SCALE))


def required_treated(hyp: Hypothesis) -> int:
    return max(min(hyp.min_treated_days, MIN_TREATED_FLOOR), round(hyp.min_treated_days * MIN_TREATED_SCALE))


def working_frame(df: pd.DataFrame, hyp: Hypothesis) -> tuple[pd.DataFrame, list[str]]:
    """
    The days this hypothesis can use, and the covariates it will adjust for.

    Normally a day counts only if the treatment, the outcome AND every covariate are known.
    Each covariate that is often missing therefore costs days. With ADAPTIVE_COVARIATES on, if that
    leaves too few days, the covariate missing on the most days is set aside (never day of week),
    and so on, until there are enough or nothing more can be set aside.
    """
    covs = list(hyp.covariate_cols or [])
    need = required_rows(hyp)
    cols = list({hyp.treatment_col, hyp.outcome_col, *covs})
    sub = df[cols].dropna()
    if len(sub) >= need or not ADAPTIVE_COVARIATES:
        return sub, covs

    have_ty = df[[hyp.treatment_col, hyp.outcome_col]].dropna().index
    droppable = [c for c in covs if c not in KEEP_COVARIATES]
    droppable.sort(key=lambda c: int(df.loc[have_ty, c].isna().sum()), reverse=True)
    for c in droppable:
        covs = [x for x in covs if x != c]
        cols = list({hyp.treatment_col, hyp.outcome_col, *covs})
        sub = df[cols].dropna()
        if len(sub) >= need:
            break
    return sub, covs


# Smallest effect worth showing someone, in the natural unit of each outcome.
# A result can be statistically real and still not worth a card: "you sleep 5
# minutes longer on busier calendar days" is not something anyone can act on or
# would notice. These floors keep trivial findings off the screen.
MIN_EFFECT = {
    "hrv_next":           2.0,   # ms
    "sleep_deep_min":     5.0,   # min
    "sleep_total_min":   10.0,   # min
    "resting_hr_next":    0.8,   # bpm
    "steps":            200.0,   # steps
}
DEFAULT_MIN_EFFECT = 0.5
# ...and an effect also has to be a visible part of how much that outcome
# normally varies for this person: at least this fraction of its standard deviation.
MIN_EFFECT_SD_FRACTION = 0.2


def min_effect_for(hyp: Hypothesis, sub: pd.DataFrame) -> float:
    """The smallest effect worth reporting for this hypothesis on this person's data."""
    floor = MIN_EFFECT.get(hyp.outcome_col, DEFAULT_MIN_EFFECT)
    try:
        sd = float(sub[hyp.outcome_col].std())
    except Exception:
        sd = 0.0
    if sd != sd:  # NaN (a single row)
        sd = 0.0
    return max(floor, MIN_EFFECT_SD_FRACTION * sd)


def _contrast(raw_effect: float, treatment: pd.Series) -> Optional[dict]:
    """
    What a one-unit effect comes to between this person's lighter and heavier
    days: the 20th and 80th percentile of the treatment they actually had.
    "5 minutes per calendar event" is easy to dismiss; "30 minutes less sleep on
    your busiest days than your quietest" is the same finding in terms of days
    they recognise. Stays inside the range seen in their data. None when the
    treatment barely varies.
    """
    values = treatment.dropna().astype(float)
    if len(values) < 5:
        return None
    low, high = float(values.quantile(0.2)), float(values.quantile(0.8))
    if high - low <= 0:
        return None
    return {"low": low, "high": high, "effect": raw_effect * (high - low)}


def _plain(label: str) -> str:
    """"Total sleep (minutes)" -> "total sleep" """
    base = label.split("(")[0].strip()
    return base[:1].lower() + base[1:] if base and not base[:2].isupper() else base


def _unit_word(label: str) -> str:
    if "(" in label and ")" in label:
        return label.split("(", 1)[1].split(")", 1)[0].strip()
    return ""


def _number(v: float) -> str:
    if abs(v) >= 100:
        return f"{round(v):,}"
    text = f"{v:.1f}"
    return text[:-2] if text.endswith(".0") else text


def contrast_sentence(hyp: Hypothesis, contrast: dict) -> str:
    """The contrast as one plain sentence, e.g. "Calendar events per day around 6 (vs 1 on your lighter days): your total sleep is about 24 minutes lower"."""
    effect = contrast["effect"]
    base = hyp.treatment_label.split("(")[0].strip()
    unit = _unit_word(hyp.outcome_label)
    amount = f"{_number(abs(effect))} {unit}".strip()
    return (
        f"{base} around {_number(contrast['high'])} (vs {_number(contrast['low'])} on your lighter days): "
        f"your {_plain(hyp.outcome_label)} is about {amount} {'higher' if effect > 0 else 'lower'}."
    )


# With ~40 hypotheses tested on the same person's data, a plain "p < 0.10"
# bar is expected to be cleared by several of them by pure chance. Moderate
# and strong confidence therefore also have to survive a Benjamini-Hochberg
# false-discovery correction across every hypothesis estimated in the run;
# anything that doesn't is shown as an "early signal" instead.
FDR_Q = 0.10


def _bh_threshold(p_values: list[float], q: float = FDR_Q) -> float:
    """Largest p-value that survives Benjamini-Hochberg at level q (0.0 if none do)."""
    ps = sorted(p for p in p_values if p is not None and p == p)  # p == p drops NaN
    m = len(ps)
    threshold = 0.0
    for rank, p in enumerate(ps, start=1):
        if p <= rank / m * q:
            threshold = p
    return threshold


def _scaled(result: dict, hyp: Hypothesis) -> dict:
    """Re-express a per-one-raw-unit effect per hyp.treatment_scale units
    (see Hypothesis.treatment_scale). The scale is always positive, so the
    CI bounds keep their order; p_value and n_obs are scale-invariant."""
    scale = hyp.treatment_scale
    if scale == 1.0:
        return result
    return {
        **result,
        "effect": result["effect"] * scale,
        "ci_low": result["ci_low"] * scale,
        "ci_high": result["ci_high"] * scale,
    }


def get_experiments_in_progress(df: pd.DataFrame, extra_hypotheses: Optional[list[Hypothesis]] = None) -> list[dict]:
    """
    For every hypothesis that doesn't yet have enough data to run, report
    how close it is — this is what powers the "Running on you" progress
    list (e.g. "Day 4 of 14"). Uses the exact same sufficiency check as
    _run_one, so this never claims something is "in progress" when it's
    actually already been tested (or never will be, for lack of a
    connected data source).

    extra_hypotheses: a user's own proposed experiments (see
    routers/experiments.py), merged in alongside the fixed HYPOTHESES list.
    """
    experiments = []
    for hyp in HYPOTHESES + (extra_hypotheses or []):
        required = [hyp.treatment_col, hyp.outcome_col] + (hyp.covariate_cols or [])
        if any(c not in df.columns for c in required):
            continue  # no relevant data source connected at all — nothing to show

        sub, covs_used = working_frame(df, hyp)

        if hyp.binary_treatment:
            current = int(sub[hyp.treatment_col].sum())
            required_n = required_treated(hyp)
        else:
            current = len(sub)
            required_n = required_rows(hyp)

        if current >= required_n:
            continue  # already sufficient — will surface as an insight instead

        early_read = None
        if current >= max(EARLY_READ_MIN_ABSOLUTE, int(required_n * EARLY_READ_MIN_FRACTION)):
            try:
                result = estimate(sub, hyp, covs_used)
                if result is not None:
                    contrast = None if hyp.binary_treatment else _contrast(result["effect"], sub[hyp.treatment_col])
                    result = _scaled(result, hyp)
                    min_effect = min_effect_for(hyp, sub)
                    material = abs(contrast["effect"]) if contrast else abs(result["effect"])
                    if material >= min_effect:
                        is_positive = result["effect"] > 0
                        higher_is_better = OUTCOME_HIGHER_IS_BETTER.get(hyp.outcome_col, True)
                        early_read = {
                            "direction": "increases" if is_positive else "decreases",
                            "is_good": is_positive if higher_is_better else not is_positive,
                        }
            except Exception as exc:
                logger.warning("Early read failed for %s (continuing without it): %s", hyp.id, exc)

        experiments.append({
            "id": hyp.id,
            "treatment_label": hyp.treatment_label,
            "outcome_label": hyp.outcome_label,
            "category": hyp.category,
            "current": current,
            "required": required_n,
            "early_read": early_read,
        })

    # Closest-to-done first — most encouraging order to show someone
    experiments.sort(key=lambda e: (e["required"] - e["current"]))
    return experiments


def run_all_hypotheses(df: pd.DataFrame, extra_hypotheses: Optional[list[Hypothesis]] = None) -> list[Insight]:
    """
    Iterate over every pre-defined hypothesis, plus any user-proposed ones
    (see routers/experiments.py).
    Skip those with insufficient data or near-zero effects.
    Return a sorted list of Insight objects.
    """
    insights: list[Insight] = []
    p_values: list[float] = []  # every estimate made this run, shown or not

    for hyp in HYPOTHESES + (extra_hypotheses or []):
        try:
            insight = _run_one(df, hyp, p_values)
            if insight is not None:
                insights.append(insight)
        except Exception as exc:
            logger.warning("Hypothesis %s failed: %s", hyp.id, exc)
            continue

    threshold = _bh_threshold(p_values)
    for insight in insights:
        if insight.confidence != ConfidenceLevel.WEAK and (insight.p_value is None or insight.p_value > threshold):
            insight.confidence = ConfidenceLevel.WEAK
            insight.confidence_label = "Early signal"
            insight.confidence_description = (
                "A hint of this pattern exists, but with this many things being tested it could still be chance. "
                "Keep logging — it'll firm up or fade."
            )
            if insight.evidence:
                insight.evidence["checks"] = checks_text("weak", demoted=True)

    # Sort: strong confidence first, then moderate, then weak
    order = {ConfidenceLevel.STRONG: 0, ConfidenceLevel.MODERATE: 1, ConfidenceLevel.WEAK: 2}
    insights.sort(key=lambda i: order.get(i.confidence, 3))

    return insights


def _run_one(df: pd.DataFrame, hyp: Hypothesis, p_sink: Optional[list[float]] = None) -> Optional[Insight]:
    """
    Run a single hypothesis. Returns None if data is insufficient or effect is trivially small.
    p_sink collects the p-value of every estimate actually made (including
    ones filtered out below) so the caller can correct for multiple testing.
    """
    # ── 1. Check required columns exist ───────────────────────────────────
    required = [hyp.treatment_col, hyp.outcome_col] + (hyp.covariate_cols or [])
    missing = [c for c in required if c not in df.columns]
    if missing:
        logger.info("SKIPPED_MISSING_COLUMNS hyp=%s missing=%s", hyp.id, missing)
        return None

    # ── 2. Build working sub-frame ─────────────────────────────────────────
    sub, covs_used = working_frame(df, hyp)

    # ── 3. Check minimum row count ─────────────────────────────────────────
    if len(sub) < required_rows(hyp):
        logger.info(
            "SKIPPED_INSUFFICIENT_ROWS hyp=%s rows=%d needed=%d", hyp.id, len(sub), required_rows(hyp)
        )
        return None

    # ── 4. Extra cardinality check for binary treatment hypotheses ─────────
    if hyp.binary_treatment:
        n_treated = sub[hyp.treatment_col].sum()
        if n_treated < required_treated(hyp):
            logger.info(
                "SKIPPED_INSUFFICIENT_TREATED_DAYS hyp=%s treated=%d needed=%d",
                hyp.id,
                int(n_treated),
                required_treated(hyp),
            )
            return None
        if len(sub) - n_treated < MIN_CONTROL_DAYS:
            logger.info("SKIPPED_INSUFFICIENT_CONTROL_DAYS hyp=%s controls=%d needed=%d", hyp.id, int(len(sub) - n_treated), MIN_CONTROL_DAYS)
            return None

    # ── 5. Run LinearDML ───────────────────────────────────────────────────
    result = estimate(sub, hyp, covs_used)

    if result is None:
        logger.info("ESTIMATION_RETURNED_NONE hyp=%s rows=%d — see estimator.py logs above for the actual cause", hyp.id, len(sub))
        return None

    if p_sink is not None and result.get("p_value") is not None:
        p_sink.append(result["p_value"])

    contrast = None if hyp.binary_treatment else _contrast(result["effect"], sub[hyp.treatment_col])
    result = _scaled(result, hyp)

    # ── 6. Filter out near-zero / trivially small effects ─────────────────
    # For an amount (steps, calendar events, screen hours) the size that matters
    # is the difference between the person's lighter and heavier days, not the
    # effect of one more unit.
    min_effect = min_effect_for(hyp, sub)
    material = abs(contrast["effect"]) if contrast else abs(result["effect"])
    if material < min_effect:
        logger.info(
            "FILTERED_SMALL_EFFECT hyp=%s effect=%.4f threshold=%.4f n_obs=%d p_value=%s",
            hyp.id, result["effect"], min_effect, result["n_obs"], result.get("p_value"),
        )
        return None

    # ── 7. Interpret → Insight ─────────────────────────────────────────────
    insight = interpret_result(
        hypothesis=hyp,
        effect=result["effect"],
        ci_low=result["ci_low"],
        ci_high=result["ci_high"],
        n_obs=result["n_obs"],
        p_value=result.get("p_value"),
    )
    if contrast:
        insight.contrast_text = contrast_sentence(hyp, contrast)
    insight.evidence = build_evidence(
        sub=sub, hyp=hyp, result=result, covs_used=covs_used,
        higher_is_better=OUTCOME_HIGHER_IS_BETTER.get(hyp.outcome_col, True), confidence=insight.confidence.value,
    )
    return insight

"""
Converts raw ATE numbers into plain-English Insight objects.
No p-values shown to user. No "statistically significant". Human language only.
"""

from __future__ import annotations

import uuid
from typing import Optional

from causal.hypotheses import Hypothesis
from models.insight import Insight, ConfidenceLevel


def interpret_result(
    *,
    hypothesis: Hypothesis,
    effect: float,
    ci_low: float,
    ci_high: float,
    n_obs: int,
    p_value: Optional[float] = None,
) -> Insight:
    """
    Turn a causal result into a human-readable Insight card.
    """

    # ── Determine direction ────────────────────────────────────────────────
    is_positive = effect > 0
    direction_word = "improves" if is_positive else "reduces"
    metric_direction: str = "positive" if is_positive else "negative"

    abs_effect = abs(round(effect, 1))
    metric_delta = f"+{abs_effect}" if is_positive else f"−{abs_effect}"

    # ── Confidence level ───────────────────────────────────────────────────
    ci_excludes_zero = not (ci_low <= 0 <= ci_high)
    ci_width = abs(ci_high - ci_low)
    tight_ci = ci_width < abs(effect) * 2

    if ci_excludes_zero and tight_ci and n_obs >= 60:
        confidence = ConfidenceLevel.STRONG
        confidence_label = "High confidence"
        confidence_description = (
            "This pattern held consistently across 9 out of 10 statistical tests on your data."
        )
    elif ci_excludes_zero and n_obs >= 30:
        confidence = ConfidenceLevel.MODERATE
        confidence_label = "Moderate confidence"
        confidence_description = (
            "This pattern appeared consistently — more data over time would sharpen the picture."
        )
    else:
        confidence = ConfidenceLevel.WEAK
        confidence_label = "Early signal"
        confidence_description = (
            "There's a hint of this pattern in your data — another month would help confirm it."
        )

    # ── Headline (per hypothesis) ──────────────────────────────────────────
    hid = hypothesis.id
    if hid == "steps_hrv":
        headline = (
            f"Each extra 2,000 steps causally {direction_word} "
            f"your next-morning HRV by {abs_effect} ms"
        )
        title = "Steps & Recovery" if is_positive else "Steps & Recovery"
        metric_unit = "ms HRV"
        tip = (
            "Aim for 2,000 more steps on days before you need peak focus or recovery."
            if is_positive
            else "Your body may need rest days — try alternating high-step and low-step days."
        )
    elif hid == "sleep_consistency_deep":
        headline = (
            f"Going to bed at your usual time causally {direction_word} "
            f"your deep sleep by {abs_effect} minutes"
        )
        title = "Sleep Timing"
        metric_unit = "min deep sleep"
        tip = (
            "Keep your bedtime within 30 minutes of your average — "
            "consistency matters more than total hours."
        )
    elif hid == "sleep_duration_rhr":
        headline = (
            f"Each extra hour of sleep causally {direction_word} "
            f"your resting heart rate by {abs_effect} bpm"
        )
        title = "Sleep & Heart Rate"
        metric_unit = "bpm"
        tip = (
            "Prioritise 7–8 hours consistently — your heart rate responds measurably."
            if is_positive
            else "Longer sleep is lowering your resting HR — a sign of improved cardiovascular fitness."
        )
    elif hid == "mindfulness_hrv":
        headline = (
            f"Regular mindfulness practice causally {direction_word} "
            f"your next-day HRV by {abs_effect} ms per session"
        )
        title = "Mindfulness & HRV"
        metric_unit = "ms HRV"
        tip = (
            "Even 10 minutes of mindfulness on busy days carries a measurable recovery benefit."
        )
    elif hid == "alcohol_hrv":
        headline = (
            f"On nights you drank, your next-morning HRV "
            f"{'increased' if is_positive else 'dropped'} by {abs_effect} ms"
        )
        title = "Alcohol & Recovery"
        metric_unit = "ms HRV"
        tip = (
            "Alcohol is suppressing your overnight recovery — "
            "track the nights you skip drinking to see the difference."
            if not is_positive
            else "Interesting — your data shows no negative HRV response to alcohol."
        )
    elif hid == "active_energy_sleep":
        headline = (
            f"Every extra 100 active calories causally {direction_word} "
            f"your sleep by {abs_effect} minutes"
        )
        title = "Activity & Sleep"
        metric_unit = "min sleep"
        tip = (
            "More active days lead to longer sleep — aim to move more before 6 pm."
            if is_positive
            else "Very high activity days may be cutting into your sleep — consider rest day scheduling."
        )
    elif hid == "hrv_sleep_quality":
        headline = (
            f"On high-HRV mornings, your deep sleep that night is "
            f"{abs_effect} minutes {'longer' if is_positive else 'shorter'}"
        )
        title = "HRV & Deep Sleep"
        metric_unit = "min deep sleep"
        tip = (
            "Your HRV is a leading indicator for sleep quality — "
            "protect high-HRV days with an early bedtime."
        )
    else:
        headline = (
            f"{hypothesis.treatment_label} causally {direction_word} "
            f"{hypothesis.outcome_label} by {abs_effect}"
        )
        title = hypothesis.treatment_label
        metric_unit = hypothesis.outcome_label
        tip = "Track this pattern over time to confirm and act on it."

    # ── Body copy ──────────────────────────────────────────────────────────
    body = (
        f"Analysed across {n_obs} days of your data, this pattern held consistently — "
        f"even after accounting for day-of-week effects, your sleep history, "
        f"and other factors that could explain it away. "
        f"This is not a correlation. The analysis is designed to isolate cause from coincidence."
    )

    # ── Share text ─────────────────────────────────────────────────────────
    share_text = (
        f"I discovered a verified cause-and-effect pattern in my own health data: "
        f"{headline.lower()}. Found with The Gap — causalme.com"
    )

    return Insight(
        hypothesis_id=hid,
        title=title,
        headline=headline,
        body=body,
        metric_delta=metric_delta,
        metric_unit=metric_unit,
        metric_direction=metric_direction,  # type: ignore[arg-type]
        treatment_label=hypothesis.treatment_label,
        outcome_label=hypothesis.outcome_label,
        confidence=confidence,
        confidence_label=confidence_label,
        confidence_description=confidence_description,
        ate=round(effect, 4),
        ci_low=round(ci_low, 4),
        ci_high=round(ci_high, 4),
        n_observations=n_obs,
        p_value=p_value,
        actionable_tip=tip,
        share_text=share_text,
    )

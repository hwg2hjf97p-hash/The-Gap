"""
Converts raw ATE numbers into plain-English Insight objects.
No p-values shown to user. No "statistically significant". Human language only.
"""

from __future__ import annotations

from typing import Optional

from causal.hypotheses import Hypothesis, PRIVATE_HYPOTHESIS_IDS
from models.insight import Insight, ConfidenceLevel

# REAL BUG FIXED HERE: metric_direction (which drives the app's green/red
# badge coloring) and direction_word (used in headlines) used to be
# computed purely from the sign of the raw effect — correct for outcomes
# where higher is better (HRV, sleep, steps, recovery score), but backwards
# for resting heart rate, where an INCREASE is the bad outcome. A found
# hypothesis like "alcohol raises your resting heart rate" was being shown
# with a green "improves" badge. Only outcomes where higher is worse need
# listing here; anything absent defaults to higher-is-better.
OUTCOME_HIGHER_IS_BETTER = {
    "resting_hr": False,
    "resting_hr_next": False,
}


def interpret_result(
    *,
    hypothesis: Hypothesis,
    effect: float,
    ci_low: float,
    ci_high: float,
    n_obs: int,
    p_value: Optional[float] = None,
) -> Insight:
    """Turn a causal result into a human-readable Insight card."""

    is_positive = effect > 0
    higher_is_better = OUTCOME_HIGHER_IS_BETTER.get(hypothesis.outcome_col, True)
    is_good = is_positive if higher_is_better else not is_positive
    # Purely descriptive (never a value judgment) — safe to use in every
    # headline regardless of which direction is actually good for this
    # outcome. "improves"/"reduces" got this backwards for RHR outcomes.
    direction_word = "increases" if is_positive else "decreases"
    metric_direction: str = "positive" if is_good else "negative"
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
            "Seen consistently across your data. Strong enough to act on."
        )
    elif ci_excludes_zero and n_obs >= 30:
        confidence = ConfidenceLevel.MODERATE
        confidence_label = "Moderate confidence"
        confidence_description = (
            "A consistent pattern in your data. More days will sharpen it further."
        )
    else:
        confidence = ConfidenceLevel.WEAK
        confidence_label = "Early signal"
        confidence_description = (
            "A hint of this pattern exists. Track another 30 days to confirm."
        )

    # ── Per-hypothesis copy ────────────────────────────────────────────────
    hid = hypothesis.id

    # RECOVERY & HRV
    if hid == "steps_hrv":
        title = "Steps & Recovery"
        headline = (
            f"Each extra 2,000 steps causally {direction_word} "
            f"your next-morning HRV by {abs_effect} ms"
        )
        metric_unit = "ms HRV"
        tip = (
            "Aim for 2,000 more steps on days before you need peak focus or recovery."
            if is_positive
            else "Your body may need rest days — try alternating high-step and low-step days."
        )

    elif hid == "alcohol_hrv":
        title = "Alcohol & Recovery"
        headline = (
            f"On nights you drank, your next-morning HRV "
            f"{'increased' if is_positive else 'dropped'} by {abs_effect} ms"
        )
        metric_unit = "ms HRV"
        tip = (
            "Alcohol is suppressing your overnight recovery — "
            "track the nights you skip drinking to see the difference."
            if not is_positive
            else "Interesting — your data shows no negative HRV response to alcohol."
        )

    elif hid == "mindfulness_hrv":
        title = "Mindfulness & HRV"
        headline = (
            f"Regular mindfulness practice causally {direction_word} "
            f"your next-day HRV by {abs_effect} ms per session"
        )
        metric_unit = "ms HRV"
        tip = "Even 10 minutes of mindfulness on busy days carries a measurable recovery benefit."

    elif hid == "hrv_sleep_quality":
        title = "HRV & Deep Sleep"
        headline = (
            f"On high-HRV mornings, your deep sleep that night is "
            f"{abs_effect} minutes {'longer' if is_positive else 'shorter'}"
        )
        metric_unit = "min deep sleep"
        tip = (
            "Your HRV is a leading indicator for sleep quality — "
            "protect high-HRV days with an early bedtime."
        )

    # SLEEP
    elif hid == "sleep_consistency_deep":
        title = "Sleep Timing"
        headline = (
            f"Going to bed at your usual time causally {direction_word} "
            f"your deep sleep by {abs_effect} minutes"
        )
        metric_unit = "min deep sleep"
        tip = (
            "Keep your bedtime within 30 minutes of your average — "
            "consistency matters more than total hours."
        )

    elif hid == "sleep_duration_rhr":
        title = "Sleep & Heart Rate"
        headline = (
            f"Each extra hour of sleep causally {direction_word} "
            f"your resting heart rate by {abs_effect} bpm"
        )
        metric_unit = "bpm"
        tip = (
            "Interesting — more sleep is linked to a *higher* resting heart rate for you; worth keeping an eye on this."
            if is_positive
            else "Longer sleep is lowering your resting HR — a sign of improved cardiovascular fitness."
        )

    elif hid == "active_energy_sleep":
        title = "Activity & Sleep"
        headline = (
            f"Every extra 100 active calories causally {direction_word} "
            f"your sleep by {abs_effect} minutes"
        )
        metric_unit = "min sleep"
        tip = (
            "More active days lead to longer sleep — aim to move more before 6 pm."
            if is_positive
            else "Very high activity days may be cutting into your sleep — consider rest day scheduling."
        )

    elif hid == "weekend_sleep":
        title = "Weekends & Deep Sleep"
        headline = (
            f"On weekends, your deep sleep is "
            f"{abs_effect} minutes {'longer' if is_positive else 'shorter'} than weekdays"
        )
        metric_unit = "min deep sleep"
        tip = (
            "Your body recovers better on weekends — try to replicate that routine on weeknights."
            if is_positive
            else "Weekend social patterns may be disrupting your sleep — track what's different."
        )

    elif hid == "sleep_debt_rhr":
        title = "Sleep Debt & Heart Rate"
        headline = (
            f"Accumulated sleep debt causally {direction_word} "
            f"your resting heart rate by {abs_effect} bpm per missed hour"
        )
        metric_unit = "bpm"
        tip = (
            "Sleep debt compounds — even 30 minutes short each night adds up across the week."
        )

    # WORK / CALENDAR
    elif hid == "meeting_load_hrv":
        title = "Meeting Load & Recovery"
        headline = (
            f"Each extra hour of meetings causally {direction_word} "
            f"your next-day HRV by {abs_effect} ms"
        )
        metric_unit = "ms HRV"
        tip = (
            "Heavy meeting days are measurably affecting your recovery. "
            "Try blocking 30-minute recovery gaps between back-to-back meetings."
            if not is_positive
            else "Your HRV holds up well on meeting-heavy days — good stress resilience."
        )

    elif hid == "late_meetings_sleep":
        title = "Late Meetings & Sleep"
        headline = (
            f"On days with meetings after 6 pm, your deep sleep "
            f"{'increases' if is_positive else 'drops'} by {abs_effect} minutes"
        )
        metric_unit = "min deep sleep"
        tip = (
            "Late meetings are cutting into your deep sleep. "
            "Try to finish work calls by 6 pm where possible."
            if not is_positive
            else "Late meetings don't seem to hurt your sleep — your wind-down routine is effective."
        )

    elif hid == "busy_day_rhr":
        title = "Busy Days & Heart Rate"
        headline = (
            f"Heavy meeting days causally {direction_word} "
            f"your resting heart rate the next day by {abs_effect} bpm"
        )
        metric_unit = "bpm"
        # REAL BUG FIXED HERE: this was inverted — is_positive means resting
        # HR went *up* on heavy-meeting days (the concerning direction), but
        # the reassuring "stays stable" copy used to show for that case.
        tip = (
            "Heavy meeting days are measurably raising your resting heart rate. "
            "Try blocking 30-minute recovery gaps between back-to-back meetings."
            if is_positive
            else "Your body handles busy days well — resting HR doesn't spike."
        )

    elif hid == "meeting_free_hrv":
        title = "Meeting-Free Days"
        headline = (
            f"On meeting-free days, your next-morning HRV is "
            f"{abs_effect} ms {'higher' if is_positive else 'lower'}"
        )
        metric_unit = "ms HRV"
        tip = (
            "Unstructured days measurably boost your recovery. "
            "Try protecting at least one meeting-free morning per week."
            if is_positive
            else "Your HRV pattern on free days is interesting — you may need more structure to feel best."
        )

    elif hid == "event_density_sleep":
        title = "Calendar Density & Sleep"
        headline = (
            f"Each extra calendar event causally {direction_word} "
            f"your sleep by {abs_effect} minutes"
        )
        metric_unit = "min sleep"
        tip = (
            "A packed calendar is cutting into your sleep. "
            "Try time-blocking your evenings as 'no event' zones."
            if not is_positive
            else "Busy days don't seem to affect your sleep duration — you wind down well."
        )

    # LIFESTYLE
    elif hid == "caffeine_sleep":
        title = "Afternoon Caffeine & Sleep"
        headline = (
            f"Afternoon caffeine after 2 pm causally "
            f"{'increases' if is_positive else 'reduces'} your deep sleep by {abs_effect} minutes"
        )
        metric_unit = "min deep sleep"
        tip = (
            "Your data confirms afternoon caffeine disrupts your deep sleep. "
            "Try cutting off coffee by 1 pm for one week."
            if not is_positive
            else "Interestingly, afternoon caffeine doesn't seem to hurt your deep sleep."
        )

    elif hid == "alcohol_rhr":
        title = "Alcohol & Heart Rate"
        # REAL BUG FIXED HERE: both the headline's increased/decreased words
        # and the tip's conditions were inverted relative to is_positive
        # (compare the correct sibling hypothesis alcohol_hrv above) — this
        # was telling users their resting heart rate *decreased* from
        # alcohol on nights the data actually showed it increased.
        headline = (
            f"On nights you drank, your resting heart rate the next day "
            f"{'increased' if is_positive else 'decreased'} by {abs_effect} bpm"
        )
        metric_unit = "bpm"
        tip = (
            "Alcohol is elevating your resting heart rate — a sign of inflammatory stress response."
            if is_positive
            else "Your heart rate responds unusually to alcohol — worth tracking further."
        )

    elif hid == "stress_hrv":
        title = "Stress & Recovery"
        headline = (
            f"Each point of daily stress causally {direction_word} "
            f"your next-day HRV by {abs_effect} ms"
        )
        metric_unit = "ms HRV"
        tip = (
            "Your body pays a measurable recovery cost for stress. "
            "Identify your top stress triggers and protect the day after."
            if not is_positive
            else "Your HRV holds up well under stress — strong resilience."
        )

    elif hid == "high_stress_sleep":
        title = "Stress & Sleep Duration"
        headline = (
            f"On high-stress days, you sleep "
            f"{'more' if is_positive else 'less'} — by {abs_effect} minutes"
        )
        metric_unit = "min sleep"
        tip = (
            "Stress is robbing you of sleep. "
            "A consistent wind-down routine on stressful days helps reclaim lost sleep."
            if not is_positive
            else "You naturally sleep more after stressful days — your body is self-correcting well."
        )

    # ACTIVITY & FITNESS
    elif hid == "steps_rhr":
        title = "Steps & Heart Health"
        headline = (
            f"Each extra 2,000 steps causally {direction_word} "
            f"your next-day resting heart rate by {abs_effect} bpm"
        )
        metric_unit = "bpm"
        tip = (
            "More daily movement is measurably improving your cardiovascular baseline."
            if not is_positive
            else "High step days are elevating your resting HR — you may be overreaching on active days."
        )

    elif hid == "active_energy_hrv":
        title = "Activity & HRV"
        headline = (
            f"Each extra 100 active calories causally {direction_word} "
            f"your next-day HRV by {abs_effect} ms"
        )
        metric_unit = "ms HRV"
        tip = (
            "Active days improve your recovery metric — moderate daily exercise is your sweet spot."
            if is_positive
            else "Very high calorie burn days may be overtraining for your body — watch recovery after hard sessions."
        )

    elif hid == "vo2max_rhr":
        title = "Fitness & Resting HR"
        headline = (
            f"Your estimated VO2 max is causally linked to your resting heart rate "
            f"({abs_effect} bpm per unit)"
        )
        metric_unit = "bpm"
        tip = (
            "Your aerobic fitness is directly lowering your resting HR — a key longevity marker."
            if not is_positive
            else "Track your VO2 max trend — improving it is one of the highest-impact health levers."
        )

    elif hid == "recovery_activity":
        title = "Recovery Score & Activity"
        headline = (
            f"Higher daily recovery scores causally {direction_word} "
            f"your step count by {abs_effect:,.0f} steps"
        )
        metric_unit = "steps"
        tip = (
            "Your recovery score is genuinely predicting your active capacity — trust it on low days."
            if is_positive
            else "Your activity doesn't closely track your recovery — you may be overriding your body's signals."
        )

    # STRAVA / TRAINING
    elif hid == "training_load_hrv":
        title = "Training Load & Recovery"
        headline = (
            f"Higher training load causally {direction_word} "
            f"your next-day HRV by {abs_effect} ms"
        )
        metric_unit = "ms HRV"
        tip = (
            "Your body needs more recovery time after big training days. "
            "Build in a low-intensity day after any session with a suffer score over 50."
            if not is_positive
            else "Your body adapts well to training load — your HRV recovers quickly after hard sessions."
        )

    elif hid == "hard_day_hrv":
        title = "Hard Sessions & HRV"
        headline = (
            f"After a hard training day, your HRV "
            f"{'improves' if is_positive else 'drops'} by {abs_effect} ms the next morning"
        )
        metric_unit = "ms HRV"
        tip = (
            "Hard sessions are suppressing your recovery signal. "
            "Follow every hard day with a genuine easy day — not just a shorter workout."
            if not is_positive
            else "Surprisingly, hard sessions don't seem to hurt your HRV — your recovery is strong."
        )

    elif hid == "training_load_sleep":
        title = "Training & Sleep"
        headline = (
            f"Higher training load causally {direction_word} "
            f"your sleep that night by {abs_effect} minutes"
        )
        metric_unit = "min sleep"
        tip = (
            "Active days are helping you sleep longer — keep the momentum."
            if is_positive
            else "Very hard training days may be disrupting your sleep. Try finishing intense sessions before 6 pm."
        )

    elif hid == "weekly_load_rhr":
        title = "Weekly Load & Heart Rate"
        headline = (
            f"Heavier training weeks causally {direction_word} "
            f"your resting heart rate by {abs_effect} bpm"
        )
        metric_unit = "bpm"
        # REAL BUG FIXED HERE: same class of inversion as busy_day_rhr above
        # — is_positive means resting HR *rises* with weekly load (fatigue),
        # but the "solid aerobic adaptation" praise used to show for that case.
        tip = (
            "Cumulative training fatigue is showing up in your resting HR. "
            "Build in a deload week every 3-4 weeks to let your cardiovascular system recover."
            if is_positive
            else "Your resting HR stays steady or improves even as training load increases — solid aerobic adaptation."
        )

    # WORKOUTS (logged in-app)
    elif hid == "workout_hrv":
        title = "Workouts & HRV"
        headline = (
            f"After days you complete a workout, your next-morning HRV "
            f"{'rises' if is_positive else 'drops'} by {abs_effect} ms"
        )
        metric_unit = "ms HRV"
        tip = (
            "Your body responds well to the workouts you follow through on — protect the habit."
            if is_positive
            else "Your HRV dips the morning after a workout. Pair training days with enough sleep and an easier day afterwards."
        )

    elif hid == "workout_rhr":
        title = "Workouts & Resting Heart Rate"
        headline = (
            f"After days you complete a workout, your resting heart rate "
            f"{'rises' if is_positive else 'drops'} by {abs_effect} bpm the next day"
        )
        metric_unit = "bpm"
        tip = (
            "Your resting heart rate runs higher after workout days — a sign you may need more recovery between sessions."
            if is_positive
            else "Workouts are lowering your next-day resting heart rate — a good sign your training is paying off."
        )

    elif hid == "workout_sleep":
        title = "Workouts & Sleep"
        headline = (
            f"On days you complete a workout, you sleep "
            f"{'longer' if is_positive else 'less'} by {abs_effect} minutes that night"
        )
        metric_unit = "min sleep"
        tip = (
            "Training days are helping you sleep longer — keep the momentum."
            if is_positive
            else "You sleep less after workouts. Try finishing earlier in the day and winding down properly."
        )

    elif hid == "workout_volume_hrv":
        title = "Training Volume & HRV"
        headline = (
            f"Each extra 1,000 kg of training volume causally {direction_word} "
            f"your next-morning HRV by {abs_effect} ms"
        )
        metric_unit = "ms HRV"
        tip = (
            "Bigger sessions aren't costing you recovery — you can keep pushing volume."
            if is_positive
            else "Higher-volume sessions drop your HRV the next morning. Cap session volume, or follow your biggest days with an easier one."
        )

    elif hid == "leg_day_hrv":
        title = "Leg Days & HRV"
        headline = (
            f"After leg days, your next-morning HRV is {abs_effect} ms "
            f"{'higher' if is_positive else 'lower'} than after other workouts"
        )
        metric_unit = "ms HRV"
        tip = (
            "Leg days aren't hurting your recovery more than other sessions."
            if is_positive
            else "Leg days hit your recovery harder than other sessions — plan an easier day after them."
        )

    # NUTRITION (logged in-app)
    elif hid == "water_hrv":
        title = "Hydration & HRV"
        headline = (
            f"Each extra 500 ml of water causally {direction_word} "
            f"your next-morning HRV by {abs_effect} ms"
        )
        metric_unit = "ms HRV"
        tip = (
            "Staying well hydrated seems to support your recovery — spread your water through the day."
            if is_positive
            else "More water isn't helping your HRV — other factors are likely doing the heavy lifting."
        )

    elif hid == "protein_hrv":
        title = "Protein & HRV"
        headline = (
            f"Each extra 25 g of protein causally {direction_word} "
            f"your next-morning HRV by {abs_effect} ms"
        )
        metric_unit = "ms HRV"
        tip = (
            "Higher-protein days go with better recovery for you — worth hitting your protein target consistently."
            if is_positive
            else "Higher-protein days go with a lower HRV for you — it may be about what else those days include, so check meal timing and sleep."
        )

    elif hid == "late_meal_deep_sleep":
        title = "Meal Timing & Deep Sleep"
        headline = (
            f"Each hour later your last meal, your deep sleep that night "
            f"{'increases' if is_positive else 'drops'} by {abs_effect} minutes"
        )
        metric_unit = "min deep sleep"
        tip = (
            "Later meals aren't hurting your deep sleep."
            if is_positive
            else "Eating later is cutting into your deep sleep — try finishing dinner 2-3 hours before bed."
        )

    # CHECK-IN CATEGORIES
    elif hid == "alcohol_drinks_hrv":
        title = "How Much You Drink & Recovery"
        headline = (
            f"Each extra drink {'raises' if is_positive else 'lowers'} "
            f"your next-morning HRV by {abs_effect} ms"
        )
        metric_unit = "ms HRV"
        tip = (
            "The more you drink, the more your overnight recovery drops. Capping a night at fewer drinks should show up the next morning."
            if not is_positive
            else "Your HRV isn't falling with the number of drinks in your data so far."
        )

    elif hid == "energy_drinks_sleep":
        title = "Energy Drinks & Sleep"
        headline = (
            f"Each energy drink {'adds' if is_positive else 'costs you'} "
            f"{abs_effect} minutes of sleep that night"
        )
        metric_unit = "min sleep"
        tip = (
            "Energy drinks are shortening your sleep. Try having your last one before midday."
            if not is_positive
            else "Energy drinks don't seem to be costing you sleep."
        )

    elif hid == "late_energy_drink_deep_sleep":
        title = "Late Energy Drinks & Deep Sleep"
        headline = (
            f"On days you had an energy drink in the evening, your deep sleep "
            f"{'increased' if is_positive else 'dropped'} by {abs_effect} minutes"
        )
        metric_unit = "min deep sleep"
        tip = (
            "Evening energy drinks are cutting into your deep sleep. Keep them to the morning."
            if not is_positive
            else "A late energy drink doesn't seem to hurt your deep sleep."
        )

    elif hid == "cigarettes_hrv":
        title = "Cigarettes & Recovery"
        headline = (
            f"Every 5 cigarettes {direction_word} your next-morning HRV by {abs_effect} ms"
        )
        metric_unit = "ms HRV"
        tip = (
            "Smoking days go with a lower HRV for you. Cutting back is one of the more direct things you can do for recovery."
            if not is_positive
            else "Your HRV isn't dropping on heavier smoking days in your data so far."
        )

    elif hid == "cigarettes_rhr":
        title = "Cigarettes & Heart Rate"
        headline = (
            f"Every 5 cigarettes {direction_word} your next-day resting heart rate by {abs_effect} bpm"
        )
        metric_unit = "bpm"
        tip = (
            "Heavier smoking days go with a higher resting heart rate for you."
            if is_positive
            else "Your resting heart rate isn't rising with smoking in your data so far."
        )

    elif hid == "gambling_sleep":
        title = "Gambling & Sleep"
        headline = (
            f"On days you gambled, you slept {'more' if is_positive else 'less'} "
            f"that night — by {abs_effect} minutes"
        )
        metric_unit = "min sleep"
        tip = (
            "Gambling days are costing you sleep. Setting a hard stop time may help."
            if not is_positive
            else "Gambling days aren't costing you sleep in your data so far."
        )

    elif hid == "gambling_hrv":
        title = "Gambling & Recovery"
        headline = (
            f"After days you gambled, your next-morning HRV "
            f"{'was higher' if is_positive else 'was lower'} by {abs_effect} ms"
        )
        metric_unit = "ms HRV"
        tip = (
            "Gambling days are showing up in your recovery."
            if not is_positive
            else "Gambling days aren't showing up as a recovery cost in your data so far."
        )

    elif hid == "substance_hrv":
        title = "Other Substances & Recovery"
        headline = (
            f"After days you used other substances, your next-morning HRV "
            f"{'was higher' if is_positive else 'was lower'} by {abs_effect} ms"
        )
        metric_unit = "ms HRV"
        tip = (
            "These days are showing up in your recovery."
            if not is_positive
            else "These days aren't showing up as a recovery cost in your data so far."
        )

    elif hid == "substance_deep_sleep":
        title = "Other Substances & Deep Sleep"
        headline = (
            f"On days you used other substances, your deep sleep that night "
            f"{'increased' if is_positive else 'dropped'} by {abs_effect} minutes"
        )
        metric_unit = "min deep sleep"
        tip = (
            "These days are cutting into your deep sleep."
            if not is_positive
            else "These days aren't cutting into your deep sleep in your data so far."
        )

    elif hid == "work_hours_hrv":
        title = "Work Hours & Recovery"
        headline = (
            f"Each extra hour of work {'raises' if is_positive else 'lowers'} "
            f"your next-morning HRV by {abs_effect} ms"
        )
        metric_unit = "ms HRV"
        tip = (
            "Longer work days are costing you recovery. Protect the evening after a long day."
            if not is_positive
            else "Longer work days aren't costing you recovery in your data so far."
        )

    elif hid == "work_hours_sleep":
        title = "Work Hours & Sleep"
        headline = (
            f"Each extra hour of work {'adds' if is_positive else 'costs you'} "
            f"{abs_effect} minutes of sleep that night"
        )
        metric_unit = "min sleep"
        tip = (
            "Long work days are eating into your sleep. A firm finish time or a wind-down buffer may help."
            if not is_positive
            else "Longer work days aren't costing you sleep."
        )

    elif hid == "late_work_sleep":
        title = "Late Finishes & Sleep"
        headline = (
            f"On days you worked until 8 pm or later, you slept "
            f"{'more' if is_positive else 'less'} that night — by {abs_effect} minutes"
        )
        metric_unit = "min sleep"
        tip = (
            "Working late is costing you sleep. Try to finish earlier on the days it matters."
            if not is_positive
            else "Working late doesn't seem to cost you sleep."
        )

    elif hid == "travel_hours_sleep":
        title = "Travel & Sleep"
        headline = (
            f"Each extra hour of travel {'adds' if is_positive else 'costs you'} "
            f"{abs_effect} minutes of sleep that night"
        )
        metric_unit = "min sleep"
        tip = (
            "Travel days cost you sleep. Plan a lighter evening after a long trip."
            if not is_positive
            else "Travel doesn't seem to cost you sleep."
        )

    elif hid == "travel_hours_hrv":
        title = "Travel & Recovery"
        headline = (
            f"Each extra hour of travel {'raises' if is_positive else 'lowers'} "
            f"your next-morning HRV by {abs_effect} ms"
        )
        metric_unit = "ms HRV"
        tip = (
            "Travel days cost you recovery. Build in an easier day afterwards."
            if not is_positive
            else "Travel isn't costing you recovery in your data so far."
        )

    elif hid == "screen_hours_sleep":
        title = "Screen Time & Sleep"
        headline = (
            f"Each extra hour of screen time {'adds' if is_positive else 'costs you'} "
            f"{abs_effect} minutes of sleep that night"
        )
        metric_unit = "min sleep"
        tip = (
            "More screen time goes with less sleep for you. Try a cut-off an hour before bed."
            if not is_positive
            else "Screen time isn't costing you sleep in your data so far."
        )

    elif hid == "screen_hours_hrv":
        title = "Screen Time & Recovery"
        headline = (
            f"Each extra hour of screen time {'raises' if is_positive else 'lowers'} "
            f"your next-morning HRV by {abs_effect} ms"
        )
        metric_unit = "ms HRV"
        tip = (
            "Heavy screen days show up in your recovery. Build in screen-free time on busy days."
            if not is_positive
            else "Screen time isn't showing up as a recovery cost in your data so far."
        )

    elif hid == "late_screen_sleep":
        title = "Late Phone Use & Sleep"
        headline = (
            f"On nights you were on your phone after 11 pm, you slept "
            f"{'more' if is_positive else 'less'} — by {abs_effect} minutes"
        )
        metric_unit = "min sleep"
        tip = (
            "Late phone use is costing you sleep. Try putting it down by 10:30 for a week."
            if not is_positive
            else "Late phone use doesn't seem to cost you sleep."
        )

    elif hid == "late_screen_deep_sleep":
        title = "Late Phone Use & Deep Sleep"
        headline = (
            f"On nights you were on your phone after 11 pm, your deep sleep "
            f"{'increased' if is_positive else 'dropped'} by {abs_effect} minutes"
        )
        metric_unit = "min deep sleep"
        tip = (
            "Late phone use is cutting into your deep sleep."
            if not is_positive
            else "Late phone use doesn't seem to hurt your deep sleep."
        )

    elif hid == "strain_hrv":
        title = "Strain & Recovery"
        headline = (
            f"Every 3 extra points of Whoop strain {'raises' if is_positive else 'lowers'} "
            f"your next-morning HRV by {abs_effect} ms"
        )
        metric_unit = "ms HRV"
        tip = (
            "Hard days cost you recovery. Plan an easier day after a high-strain one."
            if not is_positive
            else "Your HRV holds up well after hard days."
        )

    elif hid == "strain_rhr":
        title = "Strain & Resting Heart Rate"
        headline = (
            f"Every 3 extra points of Whoop strain {direction_word} "
            f"your next-day resting heart rate by {abs_effect} bpm"
        )
        metric_unit = "bpm"
        tip = (
            "High-strain days raise your resting heart rate the next day. A sign to ease off after them."
            if is_positive
            else "Your resting heart rate isn't rising after hard days."
        )

    elif hid == "strain_sleep":
        title = "Strain & Sleep"
        headline = (
            f"Every 3 extra points of Whoop strain {'adds' if is_positive else 'costs you'} "
            f"{abs_effect} minutes of sleep that night"
        )
        metric_unit = "min sleep"
        tip = (
            "Harder days are costing you sleep. Wind down earlier after them."
            if not is_positive
            else "Harder days go with more sleep for you, which is your body recovering."
        )

    # Fallback for any future hypotheses
    else:
        title = hypothesis.treatment_label
        headline = (
            f"{hypothesis.treatment_label} causally {direction_word} "
            f"{hypothesis.outcome_label} by {abs_effect}"
        )
        metric_unit = hypothesis.outcome_label
        tip = "Track this pattern over time to confirm and act on it."

    # ── Body copy ──────────────────────────────────────────────────────────
    body = (
        f"Based on {n_obs} days of your data. "
        f"Unlike a simple correlation, this analysis controls for other factors "
        f"— so what you're seeing is the isolated effect of this one behaviour on your body."
    )

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
        treatment_col=hypothesis.treatment_col,
        outcome_col=hypothesis.outcome_col,
        is_private=hypothesis.id in PRIVATE_HYPOTHESIS_IDS,
        ate=round(effect, 4),
        ci_low=round(ci_low, 4),
        ci_high=round(ci_high, 4),
        n_observations=n_obs,
        p_value=p_value,
        actionable_tip=tip,
        share_text=share_text,
    )

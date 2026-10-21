"""
Suggested targets: so nobody has to type a protein or water goal they pulled from nowhere.

Each suggestion is a RANGE with a one-line reason from published guidance, never a single "you must". The person can take
the middle of the range with one tap, type their own, or switch suggestions off.

Safeguards, on purpose:
  - Adults only (the app is 18+; a known age under 18 gets nothing).
  - Nothing at all when the person has switched suggestions off, which the app offers for pregnancy, breastfeeding, a medical
    reason to limit protein or fluids, or simply preferring to set their own.
  - Nothing weight-based for a BMI under 18.5; the app doesn't set targets there.
  - For a BMI over 30 protein is worked out from a healthy-weight figure for the person's height, because protein needs follow
    lean mass more than total weight and bodyweight rules overshoot at high weights.
  - No calorie targets and no weight-loss rates, ever (the app's standing rule). Protein, water, steps, sleep and workout
    days only.
  - Whatever is shown is described as general guidance, not medical or dietitian advice.

The ranges are from published reviews and guidelines but were written by a developer, not a dietitian: have an accredited
practising dietitian check them before launch.
"""

from __future__ import annotations

from typing import Optional

DISCLAIMER = (
    "General guidance from published research and health guidelines. It isn't medical or dietitian advice. "
    "For targets that suit you personally, ask a doctor or dietitian."
)

MIN_BMI = 18.5
HIGH_BMI = 30.0
PROTEIN_ROUND = 5
WATER_ROUND = 250
WATER_PER_KG = (30.0, 40.0)
WATER_BOUNDS = (1500, 4500)


def _round(value: float, step: float) -> int:
    return int(round(value / step) * step)


def _bmi(weight_kg: float, height_cm: Optional[float]) -> Optional[float]:
    if not height_cm or height_cm <= 0:
        return None
    return weight_kg / ((height_cm / 100.0) ** 2)


def weight_to_use(weight_kg: Optional[float], height_cm: Optional[float]) -> tuple[Optional[float], str]:
    """(kilograms to base protein on, a short note), or (None, why not) when no weight-based figure should be given."""
    if not weight_kg or weight_kg <= 0:
        return None, "needs_weight"
    bmi = _bmi(weight_kg, height_cm)
    if bmi is not None and bmi < MIN_BMI:
        return None, "low_bmi"
    if bmi is not None and bmi > HIGH_BMI:
        return round(HIGH_BMI * (height_cm / 100.0) ** 2, 1), "adjusted"  # type: ignore[operator]
    return float(weight_kg), ""


def protein_group(diet_goal: Optional[str], training_goal: Optional[str]) -> tuple[str, float, float, str]:
    """(group, low g/kg, high g/kg, the sentence that explains the range)."""
    if training_goal == "muscle" or diet_goal == "gain":
        return "muscle", 1.6, 2.2, "Reviews of studies on people who train to build muscle commonly land between 1.6 and 2.2 g of protein per kg of bodyweight a day."
    if training_goal == "fat_loss" or diet_goal == "lose":
        return "keep_muscle", 1.6, 2.2, "Higher protein is commonly advised for people who train and want to keep their muscle: about 1.6 to 2.2 g per kg of bodyweight a day."
    if training_goal == "endurance":
        return "endurance", 1.2, 1.6, "Endurance athletes are commonly advised about 1.2 to 1.6 g of protein per kg of bodyweight a day."
    return "general", 0.8, 1.2, "The standard minimum for adults is 0.8 g of protein per kg of bodyweight a day, and many people do well at up to about 1.2 g."


def protein(weight_kg: Optional[float], height_cm: Optional[float], diet_goal: Optional[str], training_goal: Optional[str]) -> dict:
    used, note = weight_to_use(weight_kg, height_cm)
    base = {"key": "protein_g", "label": "Protein", "unit": "g a day"}
    if used is None:
        if note == "low_bmi":
            return {**base, "needs": None, "unavailable": "For a personal protein target, a dietitian is the right person to ask."}
        return {**base, "needs": "weight"}
    _, per_kg_low, per_kg_high, why = protein_group(diet_goal, training_goal)
    low, high = _round(used * per_kg_low, PROTEIN_ROUND), _round(used * per_kg_high, PROTEIN_ROUND)
    suggested = _round((low + high) / 2, PROTEIN_ROUND)
    text = f"{why} For you that's about {low} to {high} g."
    if note == "adjusted":
        text += f" This is worked out from {used:.0f} kg, a healthy-weight figure for your height, because protein needs follow lean mass more than total weight."
    return {**base, "low": low, "high": high, "suggested": suggested, "why": text}


def water(weight_kg: Optional[float]) -> dict:
    base = {"key": "water_ml", "label": "Water", "unit": "ml a day"}
    if not weight_kg or weight_kg <= 0:
        return {**base, "needs": "weight"}
    low = max(WATER_BOUNDS[0], _round(weight_kg * WATER_PER_KG[0], WATER_ROUND))
    high = min(WATER_BOUNDS[1], _round(weight_kg * WATER_PER_KG[1], WATER_ROUND))
    suggested = _round((low + high) / 2, WATER_ROUND)
    why = (
        f"A common rule of thumb is 30 to 40 ml of fluid per kg of bodyweight a day, so about {low} to {high} ml for you. "
        "Food and every drink count. You may need more when it's hot or you sweat a lot, and thirst and pale urine are good checks. "
        "If a doctor has set a fluid limit for you, follow that instead."
    )
    return {**base, "low": low, "high": high, "suggested": suggested, "why": why}


def steps(current: Optional[float]) -> dict:
    out = {
        "key": "steps", "label": "Daily steps", "unit": "steps", "low": 7000, "high": 10000, "suggested": 8000,
        "why": "Studies of adults link about 7,000 or more steps a day with better long-term health, with most of the benefit by 8,000 to 10,000.",
    }
    if current is not None and current < 7000:
        step = max(500, _round(current + 1000, 500))
        out["next_step"] = {"value": step, "why": f"You average about {_round(current, 100):,} a day. Adding about 1,000 at a time is easier to keep up than jumping straight to 8,000."}
    return out


def sleep(current_hours: Optional[float]) -> dict:
    out = {
        "key": "sleep_total_min", "label": "Sleep per night", "unit": "hrs", "low": 7.0, "high": 9.0, "suggested": 8.0,
        "why": "Sleep societies recommend at least 7 hours a night for adults. Needs vary from person to person, and more than 9 hours isn't usually needed.",
    }
    if current_hours is not None and current_hours < 7.0:
        value = round(round((current_hours + 0.5) * 4) / 4, 2)
        out["next_step"] = {"value": value, "why": f"You average about {current_hours:.1f} hours. Adding half an hour is a realistic first step."}
    return out


def workout_days(training_goal: Optional[str], current_per_week: Optional[float]) -> dict:
    ranges = {"muscle": (3, 5, 4), "fat_loss": (3, 5, 4), "endurance": (4, 6, 5), "general": (3, 4, 3)}
    low, high, suggested = ranges.get(training_goal or "general", ranges["general"])
    out = {
        "key": "workout_completed_flag", "label": "Workout days per week", "unit": "days", "low": low, "high": high, "suggested": suggested,
        "why": "Health guidelines suggest about 150 minutes of moderate activity a week plus two days of strength work. "
        f"{low} to {high} sessions a week is a common range for your goal.",
    }
    if current_per_week is not None and current_per_week < low:
        out["next_step"] = {"value": int(round(current_per_week)) + 1, "why": f"You're averaging about {current_per_week:.1f} a week. One more day than now is a good next step."}
    return out


def build(
    *,
    weight_kg: Optional[float],
    height_cm: Optional[float],
    age: Optional[int],
    diet_goal: Optional[str],
    training_goal: Optional[str],
    coach_off: bool,
    current_steps: Optional[float] = None,
    current_sleep_hours: Optional[float] = None,
    current_workouts: Optional[float] = None,
) -> dict:
    """What to show: {"off": bool, "suggestions": [...], "disclaimer": str}. Empty when suggestions shouldn't be shown."""
    if coach_off:
        return {"off": True, "suggestions": [], "disclaimer": DISCLAIMER}
    if age is not None and age < 18:
        return {"off": False, "suggestions": [], "disclaimer": DISCLAIMER}
    suggestions = [
        protein(weight_kg, height_cm, diet_goal, training_goal),
        water(weight_kg),
        steps(current_steps),
        sleep(current_sleep_hours),
        workout_days(training_goal, current_workouts),
    ]
    return {"off": False, "suggestions": suggestions, "disclaimer": DISCLAIMER}

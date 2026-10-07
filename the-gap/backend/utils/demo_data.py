"""
Sample data for trying the app without a wearable (and for App Review, whose
test phones have no health history).

Twelve weeks of made-up daily readings and check-ins for an imaginary person.
Real relationships are built in, so the normal analysis finds real-looking
patterns in it:

  - a drink the evening before lowers next-day HRV and raises resting heart rate
  - more steps lift next-day HRV
  - afternoon caffeine cuts deep sleep
  - more screen time, and phone use after 11 pm, shorten sleep
  - a stressful day lowers next-day HRV
  - weekends bring longer sleep

Nothing here is random per run: the same seed gives the same twelve weeks, so
what a reviewer sees is stable.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np

DAYS = 84
SEED = 20261007

SCREEN_LAST_USE = ("before_9pm", "9_11pm", "11pm_1am", "after_1am")


def generate_demo_data(last_day: date, days: int = DAYS) -> tuple[dict[str, dict[str, float]], list[dict]]:
    """
    Returns (health_rows, checkin_rows) for the `days` days ending on `last_day`.

    health_rows maps an ISO date to the Apple Health style values the app
    stores per day; checkin_rows are daily_checkins rows without a user id.
    """
    rng = np.random.default_rng(SEED)
    start = last_day - timedelta(days=days - 1)

    health: dict[str, dict[str, float]] = {}
    checkins: list[dict] = []

    prev_hrv = 58.0
    prev_alcohol = 0
    prev_steps = 8200.0
    prev_stress = 4

    for i in range(days):
        day = start + timedelta(days=i)
        weekday = day.weekday()  # Monday = 0
        weekend = weekday >= 5

        # ── the person's day (the things they log) ───────────────────────────
        alcohol = int(rng.random() < (0.55 if weekday in (4, 5) else 0.18))
        drinks = int(rng.integers(2, 5)) if alcohol else 0
        caffeine = int(rng.random() < 0.35)
        stress = int(np.clip(round(rng.normal(4.2, 1.7)), 1, 9))
        screen = float(np.clip(round(rng.normal(4.6 + (1.0 if weekend else 0.0), 1.6) * 2) / 2, 0.5, 10.0))
        late_screen = int(rng.random() < min(0.8, 0.1 + 0.07 * screen))
        if late_screen:
            screen_last = str(rng.choice(["11pm_1am", "after_1am"], p=[0.75, 0.25]))
        else:
            screen_last = str(rng.choice(["before_9pm", "9_11pm"], p=[0.4, 0.6]))
        work = 0.0 if weekend else float(np.clip(round(rng.normal(8.2, 1.3) * 2) / 2, 4.0, 12.0))
        steps = float(np.clip(rng.normal(8200 + (1600 if weekend else 0), 2300), 1800, 18000))
        active = float(max(120.0, steps * 0.045 + rng.normal(0, 45)))

        # ── what the body did overnight (this morning's readings) ────────────
        hrv = (
            58.0
            + 0.30 * (prev_hrv - 58.0)
            - 9.0 * prev_alcohol
            + 1.6 * (prev_steps - 8200.0) / 2000.0
            - 1.1 * (prev_stress - 4)
            + rng.normal(0, 3.0)
        )
        hrv = float(np.clip(hrv, 25.0, 110.0))
        sleep = float(
            np.clip(
                432.0
                + (42.0 if weekend else 0.0)
                - 20.0 * (screen - 4.6)
                - 38.0 * late_screen
                + rng.normal(0, 24.0),
                240.0,
                600.0,
            )
        )
        deep = float(np.clip(0.18 * sleep - 11.0 * caffeine + rng.normal(0, 5.0), 20.0, 140.0))
        resting = float(np.clip(54.0 + 3.8 * prev_alcohol - 0.05 * (hrv - 58.0) + rng.normal(0, 1.1), 40.0, 90.0))
        vo2 = float(np.clip(44.0 + 0.02 * i + rng.normal(0, 0.25), 30.0, 70.0))

        energy = float(np.clip(rng.normal(2300, 260), 1400, 3600))
        protein = float(np.clip(rng.normal(122, 18), 50, 220))
        carbs = float(np.clip((energy * 0.42) / 4.0 + rng.normal(0, 20), 100, 500))
        fat = float(np.clip((energy * 0.30) / 9.0 + rng.normal(0, 8), 30, 160))

        iso = day.isoformat()
        health[iso] = {
            "hrv": round(hrv, 1),
            "resting_hr": round(resting, 1),
            "steps": round(steps),
            "sleep_total_min": round(sleep),
            "sleep_deep_min": round(deep),
            "active_energy": round(active),
            "vo2max": round(vo2, 1),
            "dietary_energy": round(energy),
            "protein_g": round(protein),
            "carbs_g": round(carbs),
            "fat_g": round(fat),
        }
        checkins.append(
            {
                "date": iso,
                "alcohol": bool(alcohol),
                "alcohol_drinks": drinks,
                "afternoon_caffeine": bool(caffeine),
                "stress_score": stress,
                "work_hours": work,
                "screen_hours": screen,
                "screen_last_use": screen_last,
            }
        )

        prev_hrv, prev_alcohol, prev_steps, prev_stress = hrv, alcohol, steps, stress

    return health, checkins

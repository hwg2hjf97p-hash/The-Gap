"""
What the research library is built from: one PubMed search per topic, grouped
by the same categories as the Goals tab. `tags` are goal metric keys
(utils/goal_catalog.py), so a card can be matched to the goals it speaks to.

Chosen to be everyday habits people can act on. Deliberately left out: drugs
and medicines, extreme diets, anything about losing weight quickly. A few
well-studied supplements are included, flagged so their cards carry an extra
caution and never offer a "test it on yourself" experiment.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Topic:
    category: str                    # sleep | body | fitness | recovery | stress_mood | habits
    query: str                       # PubMed search terms
    tags: tuple[str, ...]            # goal metrics this speaks to
    supplement: bool = False         # a supplement: extra caution, no self-experiment
    weight_related: bool = False     # about body weight: only shown to people it is safe for


def T(category: str, query: str, *tags: str, supplement: bool = False, weight_related: bool = False) -> Topic:
    return Topic(category, query, tuple(tags), supplement, weight_related)


TOPICS: list[Topic] = [
    # ── Sleep ────────────────────────────────────────────────────────────────
    T("sleep", '"sleep hygiene" AND "sleep quality"', "sleep_total_min", "sleep_score"),
    T("sleep", '"screen" AND "bedtime" AND sleep', "sleep_total_min", "screen_hours"),
    T("sleep", 'caffeine AND "sleep"', "sleep_total_min", "sleep_deep_min", "afternoon_caffeine"),
    T("sleep", 'alcohol AND "sleep architecture"', "sleep_deep_min", "alcohol_drinks"),
    T("sleep", 'exercise AND "sleep quality"', "sleep_score", "sleep_total_min"),
    T("sleep", '"sleep regularity" OR "sleep consistency"', "sleep_total_min", "sleep_score"),
    T("sleep", '"bright light" AND "sleep"', "sleep_total_min", "sleep_score"),
    T("sleep", '"cognitive behavioral therapy for insomnia"', "sleep_total_min", "sleep_score"),
    T("sleep", '"bedroom temperature" OR "ambient temperature" AND sleep', "sleep_deep_min", "sleep_score"),
    T("sleep", '"short sleep" AND "health outcomes"', "sleep_total_min"),
    T("sleep", "melatonin AND sleep", "sleep_total_min", supplement=True),
    T("sleep", "magnesium AND sleep", "sleep_total_min", "sleep_score", supplement=True),
    # ── Body ─────────────────────────────────────────────────────────────────
    T("body", '"resistance training" AND "lean body mass"', "weight_kg"),
    T("body", "protein AND \"muscle mass\" AND \"resistance training\"", "weight_kg"),
    T("body", '"daily steps" AND "weight maintenance"', "weight_kg", "steps", weight_related=True),
    T("body", '"sleep duration" AND "body weight"', "weight_kg", "sleep_total_min", weight_related=True),
    T("body", '"physical activity" AND "weight regain"', "weight_kg", weight_related=True),
    # ── Fitness ──────────────────────────────────────────────────────────────
    T("fitness", '"step count" AND mortality', "steps"),
    T("fitness", '"daily steps" AND "cardiovascular"', "steps"),
    T("fitness", '"high-intensity interval training" AND "VO2max"', "vo2max"),
    T("fitness", '"aerobic exercise" AND "cardiorespiratory fitness"', "vo2max", "workout_completed_flag"),
    T("fitness", '"resistance training" AND "muscular strength"', "workout_completed_flag"),
    T("fitness", '"exercise snacks" OR "short bouts of vigorous activity"', "active_energy", "workout_completed_flag"),
    T("fitness", '"breaking up sedentary time"', "steps", "active_energy"),
    T("fitness", '"walking" AND "postprandial glucose"', "steps"),
    T("fitness", '"weekend warrior" OR "physical activity pattern" AND mortality', "workout_completed_flag"),
    T("fitness", '"Zone 2" OR "moderate-intensity" AND "mitochondrial"', "vo2max"),
    T("fitness", "creatine AND \"muscular strength\"", "workout_completed_flag", supplement=True),
    T("fitness", '"warm-up" AND "injury prevention"', "workout_completed_flag"),
    # ── Recovery ─────────────────────────────────────────────────────────────
    T("recovery", '"heart rate variability biofeedback"', "hrv"),
    T("recovery", '"aerobic exercise" AND "heart rate variability"', "hrv", "resting_hr"),
    T("recovery", "meditation AND \"heart rate variability\"", "hrv"),
    T("recovery", '"sleep deprivation" AND "heart rate variability"', "hrv", "sleep_total_min"),
    T("recovery", 'alcohol AND "heart rate variability"', "hrv", "alcohol_drinks"),
    T("recovery", '"exercise training" AND "resting heart rate"', "resting_hr"),
    T("recovery", '"slow breathing" AND "heart rate variability"', "hrv"),
    T("recovery", '"cold water immersion" AND recovery', "recovery_score"),
    T("recovery", '"active recovery" AND "exercise"', "recovery_score"),
    T("recovery", '"omega-3" AND "heart rate variability"', "hrv", supplement=True),
    # ── Stress & mood ────────────────────────────────────────────────────────
    T("stress_mood", '"mindfulness" AND "perceived stress"', "stress_score"),
    T("stress_mood", 'exercise AND anxiety', "stress_score"),
    T("stress_mood", '"nature exposure" AND stress', "stress_score"),
    T("stress_mood", 'yoga AND "perceived stress"', "stress_score"),
    T("stress_mood", '"slow breathing" AND anxiety', "stress_score"),
    T("stress_mood", '"gratitude" OR "expressive writing" AND "well-being"', "stress_score"),
    T("stress_mood", '"physical activity" AND "depressive symptoms"', "stress_score", "steps"),
    T("stress_mood", '"walking" AND "mood"', "stress_score", "steps"),
    T("stress_mood", '"sleep" AND "emotional" AND "regulation"', "stress_score", "sleep_total_min"),
    T("stress_mood", '"social media" AND "well-being"', "stress_score", "screen_hours"),
    # ── Habits ───────────────────────────────────────────────────────────────
    T("habits", '"water intake" AND "cognitive performance"', "water_ml"),
    T("habits", '"hydration" AND "mood"', "water_ml"),
    T("habits", '"screen time" AND "sleep" AND adults', "screen_hours", "sleep_total_min"),
    T("habits", '"reducing alcohol" AND "health"', "alcohol_drinks"),
    T("habits", '"alcohol" AND "sleep"', "alcohol_drinks", "sleep_total_min"),
    T("habits", '"caffeine timing" OR "afternoon caffeine"', "afternoon_caffeine", "sleep_total_min"),
    T("habits", '"habit formation" AND "time to automaticity"', "workout_completed_flag"),
    T("habits", '"implementation intentions" AND "physical activity"', "workout_completed_flag", "steps"),
    T("habits", '"time-restricted eating" AND "sleep"', "sleep_total_min"),
    T("habits", '"standing desk" OR "sit-stand desk" AND sedentary', "steps"),
    T("habits", '"evening light" OR "blue light" AND "sleep"', "screen_hours", "sleep_total_min"),
    T("habits", '"smartphone use" AND "stress"', "screen_hours", "stress_score"),
]

CATEGORY_KEYS = ("sleep", "body", "fitness", "recovery", "stress_mood", "habits")


def topics_for(categories: list[str] | None) -> list[Topic]:
    if not categories:
        return list(TOPICS)
    wanted = set(categories)
    return [t for t in TOPICS if t.category in wanted]

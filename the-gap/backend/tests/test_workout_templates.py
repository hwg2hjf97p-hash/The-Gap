import asyncio

import pytest
from fastapi import HTTPException

from routers import workout_templates as wt
from routers import workouts


def _ex(**over):
    base = {
        "exercise_id": "Pullups",
        "name": "Pullups",
        "sets": [
            {
                "reps": 21, "weight_kg": 0, "duration_min": None, "done": True,
                "actual_reps": 19, "actual_weight_kg": 0, "started_at": "2026-10-20T01:00:00Z",
                "ended_at": "2026-10-20T01:02:00Z", "hr_avg": 150, "hr_peak": 171, "tip": "Nice pace",
            }
        ],
    }
    base.update(over)
    return workouts.ExerciseModel(**base)


def test_template_keeps_the_plan_and_drops_what_happened_on_the_day():
    body = wt.TemplateBody(name="  My Fran  ", exercises=[_ex()])
    row = wt.template_row(body, "u1")
    assert row["name"] == "My Fran"
    sets = row["exercises"][0]["sets"]
    assert sets == [{"reps": 21, "weight_kg": 0, "duration_min": None}]


def test_template_format_keeps_style_and_cap_but_never_a_result():
    fmt = workouts.FormatModel(style="amrap", cap_min=20, rounds=7, seconds=999, split="custom", laps=[60, 130])
    row = wt.template_row(wt.TemplateBody(name="Cindy", exercises=[_ex()], format=fmt), "u1")
    assert row["format"] == {"style": "amrap", "cap_min": 20, "split": "custom"}


def test_template_without_format_stores_none():
    row = wt.template_row(wt.TemplateBody(name="Leg day", exercises=[_ex()]), "u1")
    assert row["format"] is None


def test_template_needs_an_exercise():
    with pytest.raises(HTTPException) as err:
        wt.template_row(wt.TemplateBody(name="Empty", exercises=[]), "u1")
    assert err.value.status_code == 400


def test_format_style_must_be_known():
    with pytest.raises(Exception):
        workouts.FormatModel(style="tabata")


def test_workout_row_only_carries_a_format_when_there_is_one():
    plain = workouts.WorkoutBody(workout_type="Strength", planned_date="2026-10-20", exercises=[])
    assert "format" not in workouts._row_from_body(plain, "u1")
    timed = workouts.WorkoutBody(
        workout_type="Strength", planned_date="2026-10-20", exercises=[], format=workouts.FormatModel(style="for_time", seconds=402)
    )
    assert workouts._row_from_body(timed, "u1")["format"]["seconds"] == 402


def test_workout_rejects_an_absurd_number_of_laps():
    body = workouts.WorkoutBody(
        workout_type="Strength", planned_date="2026-10-20", exercises=[],
        format=workouts.FormatModel(style="for_time", split="custom", laps=list(range(1, 300))),
    )
    with pytest.raises(HTTPException):
        workouts._row_from_body(body, "u1")


class _Resp:
    def __init__(self, status):
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")


def _run(statuses, payload):
    sent = []

    async def send(p):
        sent.append(dict(p))
        return _Resp(statuses[len(sent) - 1])

    resp = asyncio.run(workouts._write_with_format_fallback(send, payload))
    return resp, sent


def test_save_works_first_time_when_the_format_column_exists():
    resp, sent = _run([201], {"name": "x", "format": {"style": "for_time"}})
    assert len(sent) == 1 and "format" in sent[0]


def test_save_retries_without_format_when_the_column_is_missing():
    resp, sent = _run([400, 201], {"name": "x", "format": {"style": "for_time"}})
    assert len(sent) == 2 and "format" not in sent[1] and sent[1]["name"] == "x"


def test_a_failure_without_a_format_is_not_retried():
    with pytest.raises(RuntimeError):
        _run([400], {"name": "x"})

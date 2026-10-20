import asyncio
import json

from routers import evidence, evidence_admin
from utils.agreement import agreement
from utils.supplements import decorate_card


def study(**extra):
    base = {
        "id": "c1", "title": "Caffeine and sleep", "plain_summary": "s", "finding": "f", "year": 2022, "study_type": "meta-analysis",
        "metric_tags": ["sleep_total_min", "sleep_deep_min", "afternoon_caffeine"], "caution_notes": "Averages only.",
        "effect_metric": "sleep_total_min", "effect_direction": "down",
    }
    base.update(extra)
    return decorate_card(base)


def test_a_finding_that_goes_the_same_way_as_the_study_agrees():
    assert agreement(study(), "afternoon_caffeine", "sleep_total_min", -20.0) == "agrees"


def test_a_finding_that_goes_the_other_way_is_said_to_differ():
    assert agreement(study(), "afternoon_caffeine", "sleep_total_min", 20.0) == "differs"


def test_several_coffees_count_as_the_same_habit():
    assert agreement(study(), "caffeine_drinks", "sleep_total_min", -5.0) == "agrees"


def test_it_only_compares_the_same_reading_and_the_same_habit():
    assert agreement(study(), "afternoon_caffeine", "hrv_next", -2.0) is None        # a different reading
    assert agreement(study(), "screen_hours", "sleep_total_min", -2.0) is None       # a different habit


def test_an_unmarked_study_or_a_flat_finding_is_not_compared():
    assert agreement(study(effect_metric=None, effect_direction=None), "afternoon_caffeine", "sleep_total_min", -20.0) is None
    assert agreement(study(effect_direction="sideways"), "afternoon_caffeine", "sleep_total_min", -20.0) is None
    assert agreement(study(), "afternoon_caffeine", "sleep_total_min", 0.0) is None
    assert agreement(study(), "afternoon_caffeine", "sleep_total_min", None) is None


def test_a_supplement_study_is_never_compared():
    marker = "Supplements can interact with medicines and aren't right for everyone."
    magnesium = study(title="Magnesium and sleep", caution_notes=marker, metric_tags=["sleep_total_min", "afternoon_caffeine"], effect_direction="up")
    assert magnesium["is_supplement"] is True
    assert agreement(magnesium, "afternoon_caffeine", "sleep_total_min", 20.0) is None


def test_the_related_research_reply_says_whether_each_study_agrees(monkeypatch):
    async def listing(tags=None, category=None, limit=100):
        return [study(effect_metric=None, effect_direction=None)]

    async def marks(ids):
        return {"c1": {"effect_metric": "sleep_total_min", "effect_direction": "down"}}

    async def prefs(user_id):
        return {"tz": "Australia/Brisbane"}

    import utils.push as push

    monkeypatch.setattr(evidence, "list_verified_cards", listing)
    monkeypatch.setattr(evidence, "_effect_marks", marks)
    monkeypatch.setattr(push, "get_prefs", prefs)
    out = asyncio.run(evidence.related_research(treatment_col="afternoon_caffeine", outcome_col="sleep_total_min", ate=-12.0, user_id="u1"))
    assert json.loads(out.body)["cards"][0]["agreement"] == "agrees"
    out = asyncio.run(evidence.related_research(treatment_col="afternoon_caffeine", outcome_col="sleep_total_min", ate=None, user_id="u1"))
    assert json.loads(out.body)["cards"][0]["agreement"] is None


def test_if_the_marking_columns_are_missing_the_cards_still_show(monkeypatch):
    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, *a, **k):
            raise RuntimeError("column does not exist")

    monkeypatch.setattr(evidence.httpx, "AsyncClient", lambda **kw: _Client())
    assert asyncio.run(evidence._effect_marks(["c1"])) == {}


def test_the_review_page_can_mark_a_study_even_after_it_is_approved():
    assert evidence_admin.EFFECT_FIELDS == {"effect_metric", "effect_direction"}
    assert set(evidence_admin.EFFECT_FIELDS) <= set(evidence_admin.EDITABLE)

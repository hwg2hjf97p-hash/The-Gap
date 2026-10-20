import asyncio
import json

import numpy as np

from causal.hypotheses import HYPOTHESES, SUPPLEMENT_HYPOTHESIS_IDS
from causal.interpreter import interpret_result
from routers import assistant, checkin, evidence, focus, improvement
from utils import supplements as sup
from utils.supplements import decorate_card, hidden_where_the_person_is, pick_related

MARKER_CAUTION = "Small trials. Supplements can interact with medicines and aren't right for everyone. Talk to a doctor or pharmacist before starting one."


def card(cid, title, tags, supplement=False, year=2020, study="RCT"):
    return {
        "id": cid, "title": title, "plain_summary": f"{title} summary", "finding": f"{title} finding", "metric_tags": tags,
        "study_type": study, "year": year, "caution_notes": MARKER_CAUTION if supplement else "Averages only.",
    }


# ── the log ──────────────────────────────────────────────────────────────────

def test_the_log_keeps_only_known_supplements_in_a_fixed_order():
    assert sup.clean_log("omega3, Magnesium ,nonsense") == "magnesium,omega3"
    assert sup.clean_log("") == ""          # answered: took none
    assert sup.clean_log(None) is None      # never asked
    assert sup.clean_log("creatine") == ""  # not one we compare, so not stored


def test_the_request_cleans_the_log():
    body = checkin.CheckInRequest(date="2026-10-01", supplements="melatonin,wat")
    assert body.supplements == "melatonin"


class _Resp:
    def __init__(self, rows):
        self._rows = rows

    def raise_for_status(self):
        pass

    def json(self):
        return self._rows


def test_the_log_becomes_took_columns_and_unasked_days_stay_missing(monkeypatch):
    rows = [
        {"date": "2026-10-01", "alcohol": False, "afternoon_caffeine": False, "stress_score": 3, "supplements": "magnesium,omega3"},
        {"date": "2026-10-02", "alcohol": False, "afternoon_caffeine": False, "stress_score": 3, "supplements": ""},
        {"date": "2026-10-03", "alcohol": False, "afternoon_caffeine": False, "stress_score": 3, "supplements": None},
    ]
    monkeypatch.setattr(checkin.httpx, "get", lambda *a, **k: _Resp(rows))
    df = checkin.get_checkin_dataframe("u1")
    first, second, third = df.iloc[0], df.iloc[1], df.iloc[2]
    assert first["took_magnesium"] == 1 and first["took_omega3"] == 1
    assert first["took_melatonin"] == 0
    assert second["took_magnesium"] == 0  # answered: none
    assert np.isnan(third["took_magnesium"])  # never asked: not a zero


def test_a_checkin_with_no_supplement_answers_adds_no_columns(monkeypatch):
    rows = [{"date": "2026-10-01", "alcohol": False, "afternoon_caffeine": False, "stress_score": 3}]
    monkeypatch.setattr(checkin.httpx, "get", lambda *a, **k: _Resp(rows))
    df = checkin.get_checkin_dataframe("u1")
    assert not any(c.startswith("took_") for c in df.columns)


# ── findings about a supplement ──────────────────────────────────────────────

def test_every_supplement_finding_is_a_real_binary_hypothesis_on_a_logged_column():
    by_id = {h.id: h for h in HYPOTHESES}
    assert SUPPLEMENT_HYPOTHESIS_IDS <= set(by_id)
    for hid in SUPPLEMENT_HYPOTHESIS_IDS:
        h = by_id[hid]
        assert h.binary_treatment and h.min_treated_days >= 10
        assert h.treatment_col.removeprefix("took_") in sup.CHECKIN_KEYS


def test_the_wording_describes_the_persons_own_days_and_never_advises():
    banned = ("causal", "isolated effect", "should", "try ", "boost", "improve", "works", "cure", "treat ", "prevent", "recommend")
    for h in HYPOTHESES:
        if h.id not in SUPPLEMENT_HYPOTHESIS_IDS:
            continue
        for effect, lo, hi in ((12.0, 4.0, 20.0), (-12.0, -20.0, -4.0)):
            insight = interpret_result(hypothesis=h, effect=effect, ci_low=lo, ci_high=hi, n_obs=60, p_value=0.01)
            assert insight.is_supplement and not insight.is_private
            assert insight.share_text == ""
            text = " ".join([insight.title, insight.headline, insight.body]).lower()
            assert "logged" in insight.headline.lower() and "didn't" in insight.headline.lower()
            for word in banned:
                assert word not in text, (h.id, word)
            # the tip says what the finding is not, and points to a doctor or pharmacist
            assert "doctor or pharmacist" in insight.actionable_tip and "isn't a reason to start" in insight.actionable_tip


def test_other_findings_are_not_marked_as_supplements():
    other = next(h for h in HYPOTHESES if h.id == "steps_hrv")
    assert interpret_result(hypothesis=other, effect=3.0, ci_low=1.0, ci_high=5.0, n_obs=60, p_value=0.01).is_supplement is False


def test_todays_one_thing_never_offers_a_supplement_finding(monkeypatch):
    insights = [
        {"hypothesis_id": "magnesium_sleep", "confidence": "strong", "is_supplement": True},
        {"hypothesis_id": "steps_hrv", "confidence": "strong"},
    ]

    async def has_checkin(user_id, today):
        return True

    async def active(user_id):
        return set()

    monkeypatch.setattr(focus, "_has_todays_checkin", has_checkin)
    monkeypatch.setattr(focus, "get_latest_results", lambda user_id: {"insights": insights})
    monkeypatch.setattr(focus, "get_active_hypothesis_ids", active)
    out = asyncio.run(focus.get_todays_focus(user_id="u1", local_date="2026-10-01"))
    assert b'"steps_hrv"' in out.body and b"magnesium" not in out.body


def test_no_improvement_plan_or_try_this_for_a_supplement():
    body = improvement.ImprovementPlanRequest(
        hypothesis_id="magnesium_sleep", treatment_label="x", outcome_label="y", headline="h", existing_tip="t", metric_direction="positive"
    )
    out = asyncio.run(improvement.get_improvement_plan(body, user_id="u1"))
    data = json.loads(out.body)
    assert data["story"] is None and data["plan_text"] is None and data["not_advice"] is True


# ── research cards ───────────────────────────────────────────────────────────

def test_a_supplement_card_is_flagged_and_gets_its_own_caution():
    flagged = decorate_card(card("c1", "Magnesium and sleep", ["sleep_total_min"], supplement=True))
    assert flagged["is_supplement"] and "kidney" in flagged["supplement_note"] and flagged["supplement_name"] == "Magnesium"
    plain = decorate_card(card("c2", "Screens and sleep", ["sleep_total_min"]))
    assert plain["is_supplement"] is False and "supplement_note" not in plain


def test_ashwagandha_and_omega3_are_recognised_by_their_names():
    assert sup.match("Ashwagandha root extract and stress").key == "ashwagandha"
    assert sup.match("Fish oil and heart rate variability").key == "omega3"
    assert sup.match("Withania somnifera in adults").key == "ashwagandha"
    assert sup.match("Walking and mood") is None


def test_melatonin_research_is_not_shown_to_people_in_australia():
    mel = decorate_card(card("m", "Melatonin and sleep", ["sleep_total_min"], supplement=True))
    mag = decorate_card(card("g", "Magnesium and sleep", ["sleep_total_min"], supplement=True))
    assert hidden_where_the_person_is(mel, "Australia/Brisbane") and not hidden_where_the_person_is(mel, "Europe/London")
    assert not hidden_where_the_person_is(mag, "Australia/Brisbane")


def test_a_finding_gets_habit_research_first_and_at_most_one_supplement():
    cards = [
        decorate_card(card("a", "Screens and sleep", ["sleep_total_min"], year=2022)),
        decorate_card(card("b", "Bedroom temperature", ["sleep_deep_min"], year=2021)),
        decorate_card(card("c", "Light and sleep", ["sleep_total_min", "sleep_score"], year=2019)),
        decorate_card(card("d", "Magnesium and sleep", ["sleep_total_min"], supplement=True, year=2023)),
        decorate_card(card("e", "Ashwagandha and sleep", ["sleep_total_min"], supplement=True, year=2024)),
        decorate_card(card("f", "Walking and steps", ["steps"], year=2024)),
    ]
    picked = pick_related(cards, [], ["sleep_total_min", "sleep_score"])
    assert len(picked) == 3
    assert [c["is_supplement"] for c in picked] == [False, False, True]
    assert "f" not in [c["id"] for c in picked]


def test_a_card_must_share_a_tag_with_the_finding():
    assert pick_related([decorate_card(card("f", "Walking", ["steps"]))], ["alcohol_drinks"], ["hrv"]) == []


def test_a_finding_about_a_logged_supplement_shows_research_on_that_one_only(monkeypatch):
    cards = [
        decorate_card(card("d", "Magnesium and sleep", ["sleep_total_min"], supplement=True)),
        decorate_card(card("e", "Ashwagandha and sleep", ["sleep_total_min"], supplement=True)),
        decorate_card(card("a", "Screens and sleep", ["sleep_total_min"])),
    ]

    async def listing(tags=None, category=None, limit=100):
        return cards

    async def prefs(user_id):
        return {"tz": "Europe/London"}

    monkeypatch.setattr(evidence, "list_verified_cards", listing)
    import utils.push as push

    monkeypatch.setattr(push, "get_prefs", prefs)
    out = asyncio.run(evidence.related_research(treatment_col="took_magnesium", outcome_col="sleep_total_min", user_id="u1"))
    ids = [c["id"] for c in json.loads(out.body)["cards"]]
    assert ids == ["a", "d"]


# ── the chat assistant ───────────────────────────────────────────────────────

def test_the_assistant_is_told_never_to_recommend_a_supplement():
    text = assistant.SYSTEM_PROMPT
    assert "Never recommend" in text and "dose" in text and "doctor or pharmacist" in text

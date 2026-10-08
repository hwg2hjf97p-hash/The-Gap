import asyncio
from datetime import date, timedelta

import pytest

from routers import evidence as evidence_router
from utils import experiments, feed, feed_intro, feed_selector
from utils.feed_selector import card_score, due_for_round, pick_cards
from utils.goal_catalog import GOAL_METRICS

TODAY = date(2026, 10, 8)
STEPS, SLEEP, HRV = GOAL_METRICS["steps"], GOAL_METRICS["sleep_total_min"], GOAL_METRICS["hrv"]


def _card(cid, tags, study="meta-analysis", year=2022, weight=False, **extra):
    return {"id": cid, "title": f"Card {cid}", "metric_tags": tags, "study_type": study, "year": year, "weight_related": weight, **extra}


def _goal(metric, gid=None):
    return {"id": gid or f"g-{metric}", "metric_col": metric, "direction": "increase", "target_value": 9000, "metric_label": metric}


# ── which cards are chosen ───────────────────────────────────────────────────

def test_a_card_must_match_a_goal():
    picks = pick_cards([_goal("steps")], [_card("a", ["sleep_total_min"]), _card("b", ["steps"])], set(), True, "s")
    assert [c["id"] for c, _ in picks] == ["b"]


def test_a_card_shown_in_the_last_60_days_is_never_chosen_again():
    cards = [_card("a", ["steps"]), _card("b", ["steps"])]
    picks = pick_cards([_goal("steps")], cards, {"a"}, True, "s")
    assert [c["id"] for c, _ in picks] == ["b"]
    assert pick_cards([_goal("steps")], cards, {"a", "b"}, True, "s") == []


def test_at_most_two_cards_and_one_per_goal_first():
    goals = [_goal("steps"), _goal("hrv"), _goal("sleep_total_min")]
    cards = [_card("s1", ["steps"]), _card("s2", ["steps"]), _card("h1", ["hrv"]), _card("z1", ["sleep_total_min"])]
    picks = pick_cards(goals, cards, set(), True, "s")
    assert len(picks) == 2
    assert len({g["metric_col"] for _, g in picks}) == 2  # two different goals, not two for steps


def test_a_second_card_for_a_goal_is_used_when_there_is_room():
    cards = [_card("s1", ["steps"]), _card("s2", ["steps"]), _card("s3", ["steps"])]
    picks = pick_cards([_goal("steps")], cards, set(), True, "s")
    assert len(picks) == 2 and len({c["id"] for c, _ in picks}) == 2


def test_weight_cards_are_held_back_unless_allowed():
    cards = [_card("w", ["steps"], weight=True), _card("n", ["steps"])]
    assert [c["id"] for c, _ in pick_cards([_goal("steps")], cards, set(), False, "s")] == ["n"]
    assert {c["id"] for c, _ in pick_cards([_goal("steps")], cards, set(), True, "s")} == {"w", "n"}


def test_meta_analyses_and_newer_work_rank_higher_and_exact_metric_matches_first():
    meta = _card("m", ["steps"], "meta-analysis", 2020)
    trial = _card("t", ["steps"], "RCT", 2025)
    assert card_score(meta, "steps", "s") > card_score(trial, "steps", "s")
    exact = _card("e", ["steps", "hrv"], "RCT", 2020)
    side = _card("x", ["hrv", "steps"], "RCT", 2020)
    assert card_score(exact, "steps", "s") > card_score(side, "steps", "s")


def test_people_with_the_same_goal_do_not_all_get_the_same_card_first():
    cards = [_card(str(i), ["steps"]) for i in range(12)]
    firsts = {pick_cards([_goal("steps")], cards, set(), True, f"user{n}")[0][0]["id"] for n in range(12)}
    assert len(firsts) > 1


def test_a_round_is_at_most_every_two_days():
    assert due_for_round([], TODAY, False)
    assert not due_for_round([TODAY - timedelta(days=1)], TODAY, False)
    assert due_for_round([TODAY - timedelta(days=2)], TODAY, False)
    assert not due_for_round([TODAY], TODAY, True, created_today=2)  # asking for more is limited to two a day
    assert due_for_round([TODAY], TODAY, True, created_today=0)


# ── the personal sentence ────────────────────────────────────────────────────

FACTS = feed_intro.facts_for(STEPS, "increase", 7200.0, 9000.0)


def test_the_plain_sentence_states_the_goal_and_where_they_are():
    text = feed_intro.template_intro(FACTS)
    assert "9,000" in text and "7,200" in text and "7-day average" in text
    assert "should" not in text and "research" not in text.lower()
    assert "hold" in feed_intro.template_intro(feed_intro.facts_for(STEPS, "maintain", 7200.0, 7000.0))
    assert "down to" in feed_intro.template_intro(feed_intro.facts_for(GOAL_METRICS["resting_hr"], "decrease", 60.0, 55.0))


@pytest.mark.parametrize(
    "text",
    [
        "You're working towards 9,000 steps a day and are averaging 7,200 now.",
        "Your 7-day average is 7,200 steps, and your target is 9,000.",
    ],
)
def test_sentences_that_stay_inside_the_facts_are_accepted(text):
    assert feed_intro.intro_is_valid(text, FACTS)


@pytest.mark.parametrize(
    "text",
    [
        "You should walk more to reach 9,000 steps.",                       # advice
        "Research shows 9,000 steps is ideal, and you're at 7,200.",        # a research claim
        "You're at 7,200 steps, 1,800 short of 9,000.",                     # a number it worked out
        "You're at 7,500 steps and aiming for 9,000.",                      # a wrong number
        "You're aiming for 9,000 steps! Keep going.",                       # exclamation, two sentences
        "Try a longer walk. You're at 7,200 of 9,000 steps.",               # two sentences, advice
        "",
    ],
)
def test_sentences_that_break_a_rule_are_rejected(text):
    assert not feed_intro.intro_is_valid(text, FACTS)


def test_a_sentence_is_too_long_when_it_runs_past_the_limit():
    assert not feed_intro.intro_is_valid("You are " + "really " * 40 + "at 7,200 of 9,000 steps.", FACTS)


def _intro_env(monkeypatch, *, allowed=True, cached=None, drafted=None):
    calls = {"haiku": 0, "put": []}

    async def ai_allowed(user_id):
        return allowed

    async def cache_get(key):
        return cached

    async def cache_put(key, text):
        calls["put"].append(text)

    async def haiku(facts):
        calls["haiku"] += 1
        return drafted

    monkeypatch.setattr(feed_intro, "ai_allowed", ai_allowed)
    monkeypatch.setattr(feed_intro, "_cache_get", cache_get)
    monkeypatch.setattr(feed_intro, "_cache_put", cache_put)
    monkeypatch.setattr(feed_intro, "_call_haiku", haiku)
    return calls


GOOD = "You're working towards 9,000 steps a day and are averaging 7,200 now."


def test_with_ai_switched_off_nothing_is_sent_and_the_plain_sentence_is_used(monkeypatch):
    calls = _intro_env(monkeypatch, allowed=False, drafted=GOOD)
    text = asyncio.run(feed_intro.make_intro("u1", STEPS, "increase", 7200.0, 9000.0))
    assert calls["haiku"] == 0 and text == feed_intro.template_intro(FACTS)


def test_a_good_ai_sentence_is_used_and_saved_for_next_time(monkeypatch):
    calls = _intro_env(monkeypatch, drafted=GOOD)
    assert asyncio.run(feed_intro.make_intro("u1", STEPS, "increase", 7200.0, 9000.0)) == GOOD
    assert calls["put"] == [GOOD]


def test_a_saved_sentence_is_reused_without_calling_the_ai(monkeypatch):
    calls = _intro_env(monkeypatch, cached=GOOD, drafted="should not be used")
    assert asyncio.run(feed_intro.make_intro("u1", STEPS, "increase", 7200.0, 9000.0)) == GOOD
    assert calls["haiku"] == 0


def test_a_bad_ai_sentence_falls_back_to_the_plain_one_and_is_not_saved(monkeypatch):
    calls = _intro_env(monkeypatch, drafted="You should walk 1,800 more steps.")
    text = asyncio.run(feed_intro.make_intro("u1", STEPS, "increase", 7200.0, 9000.0))
    assert text == feed_intro.template_intro(FACTS) and calls["put"] == []


def test_the_cache_key_holds_no_personal_information():
    key = feed_intro.cache_key(FACTS)
    assert len(key) == 40 and all(c in "0123456789abcdef" for c in key)
    assert key == feed_intro.cache_key(feed_intro.facts_for(STEPS, "increase", 7200.0, 9000.0))
    assert key != feed_intro.cache_key(feed_intro.facts_for(STEPS, "increase", 7300.0, 9000.0))


# ── only approved cards reach the feed ───────────────────────────────────────

def test_a_card_that_is_no_longer_approved_disappears_from_the_feed(monkeypatch):
    import utils.evidence as evidence_module
    import routers.interventions as interventions_module

    async def get_cards(ids):
        return {"c1": {"id": "c1", "title": "Still approved"}}  # c2 has been unapproved

    async def active(user_id):
        return {"card:c1"}

    monkeypatch.setattr(evidence_module, "get_verified_cards", get_cards)
    monkeypatch.setattr(interventions_module, "get_active_hypothesis_ids", active)
    items = [
        {"id": "i1", "kind": "check_this_out", "card_id": "c1"},
        {"id": "i2", "kind": "check_this_out", "card_id": "c2"},
        {"id": "i3", "kind": "goal_achieved"},
    ]
    out = asyncio.run(feed.attach_cards("u1", items))
    assert [i["id"] for i in out] == ["i1", "i3"]
    assert out[0]["card"]["title"] == "Still approved" and out[0]["experiment_active"] is True
    assert "not medical advice" in out[0]["disclaimer"] and "Talk to your doctor" in out[0]["disclaimer"]


# ── the 14-day test ──────────────────────────────────────────────────────────

BASE = [50, 52, 49, 51, 50, 53, 48, 52, 50, 51, 49, 52, 50, 51]


def test_a_big_steady_rise_is_a_clear_change():
    result = experiments.classify_change(BASE, [v + 8 for v in BASE])
    assert result["state"] == "clear" and result["difference"] == pytest.approx(8)


def test_a_small_wobble_is_not_a_change():
    after = [v + (1 if i % 2 else -1) * 0.5 for i, v in enumerate(BASE)]
    assert experiments.classify_change(BASE, after)["state"] == "none"


def test_a_modest_shift_is_only_a_possible_change():
    after = [v + 1.4 for v in BASE]
    assert experiments.classify_change(BASE, after)["state"] in ("possible", "clear")


def test_too_few_days_gives_no_verdict():
    assert experiments.classify_change([50, 51, 52], BASE)["state"] == "not_enough_data"
    assert experiments.classify_change(BASE, [50, 51, 52])["state"] == "not_enough_data"


def test_the_result_is_worded_as_a_hint_in_the_readings_own_units():
    result = experiments.classify_change([v * 60 for v in [6.4, 6.6, 6.5, 6.7, 6.4, 6.6, 6.5, 6.6]], [v * 60 for v in [7.6, 7.8, 7.7, 7.9, 7.6, 7.8, 7.7, 7.8, 7.7]])
    text = experiments.result_text("A screen-free hour before bed", SLEEP, result)
    assert "hrs" in text and "clear change" in text and "not proof" in text
    assert "caused" not in text.lower() and "causal" not in text.lower()


def test_not_enough_data_is_said_plainly():
    text = experiments.result_text("A walk after dinner", SLEEP, experiments.classify_change([1.0] * 3, [1.0] * 4))
    assert "couldn't say" in text and "not proof" in text


# ── starting a test from a card ──────────────────────────────────────────────

CARD = {"id": "c1", "experiment_label": "A screen-free hour before bed", "metric_tags": ["sleep_total_min"], "experiment_days": 14}


class _Resp:
    def __init__(self, rows):
        self._rows = rows

    def raise_for_status(self):
        pass

    def json(self):
        return self._rows


def _experiment_env(monkeypatch, *, card=CARD, active=frozenset(), points=None, posts=None):
    async def get_card(card_id):
        return card

    async def get_active(user_id):
        return set(active)

    async def user_today(user_id):
        return TODAY

    async def fetch_points(user_id, metric, since):
        return points if points is not None else [(TODAY - timedelta(days=i), 420.0) for i in range(1, 11)]

    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, json=None):
            (posts if posts is not None else []).append(json)
            return _Resp([json])

    monkeypatch.setattr(evidence_router, "get_verified_card", get_card)
    monkeypatch.setattr(evidence_router, "get_active_hypothesis_ids", get_active)
    monkeypatch.setattr(evidence_router, "user_today", user_today)
    monkeypatch.setattr(evidence_router, "fetch_points", fetch_points)
    monkeypatch.setattr(evidence_router.httpx, "AsyncClient", lambda **kw: _Client())


def _start(card_id="c1", metric="sleep_total_min"):
    return asyncio.run(evidence_router.start_experiment(evidence_router.ExperimentBody(card_id=card_id, metric_key=metric), user_id="u1"))


def test_a_test_starts_from_an_approved_card_with_a_behaviour(monkeypatch):
    posts = []
    _experiment_env(monkeypatch, posts=posts)
    response = _start()
    assert response.status_code == 200
    row = posts[0]
    assert row["hypothesis_id"] == "card:c1" and row["card_id"] == "c1" and row["follow_up_days"] == 14
    assert row["treatment_label"] == "A screen-free hour before bed" and row["outcome_col"] == "sleep_total_min"
    assert row["baseline_value"] == pytest.approx(7.0) and row["started_date"] == "2026-10-08"


def test_a_card_without_a_behaviour_cannot_be_tested(monkeypatch):
    _experiment_env(monkeypatch, card={**CARD, "experiment_label": None})
    assert _start().status_code == 400


def test_an_unapproved_or_missing_card_cannot_be_tested(monkeypatch):
    _experiment_env(monkeypatch, card=None)
    assert _start().status_code == 404


def test_the_reading_must_be_one_the_card_speaks_to(monkeypatch):
    _experiment_env(monkeypatch)
    assert _start(metric="steps").status_code == 400
    assert _start(metric="not_a_metric").status_code == 400


def test_the_same_test_cannot_run_twice(monkeypatch):
    _experiment_env(monkeypatch, active={"card:c1"})
    assert _start().status_code == 409


def test_a_test_needs_enough_recent_readings_to_compare_against(monkeypatch):
    _experiment_env(monkeypatch, points=[(TODAY - timedelta(days=1), 420.0)] * 2)
    response = _start()
    assert response.status_code == 422 and b"at least 5 days" in response.body


# ── finishing a test ─────────────────────────────────────────────────────────

def _finish_env(monkeypatch, *, started, patch_rows):
    out = {"patched": [], "feed": []}

    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None, params=None):
            return _Resp([{"id": "iv1", "hypothesis_id": "card:c1", "treatment_label": "A screen-free hour before bed", "outcome_col": "sleep_total_min", "started_date": started.isoformat(), "follow_up_days": 14, "card_id": "c1"}])

        async def patch(self, url, headers=None, params=None, json=None):
            out["patched"].append(json)
            return _Resp(patch_rows)

    async def user_today(user_id):
        return TODAY

    async def fetch_points(user_id, metric, since):
        before = [(started - timedelta(days=i), 6.5 * 60 + (i % 3) * 5) for i in range(1, 15)]
        after = [(started + timedelta(days=i), 7.7 * 60 + (i % 3) * 5) for i in range(0, 14)]
        return before + after

    async def create_feed_item(user_id, **kw):
        out["feed"].append(kw)

    monkeypatch.setattr(experiments.httpx, "AsyncClient", lambda **kw: _Client())
    monkeypatch.setattr(experiments, "user_today", user_today)
    monkeypatch.setattr(experiments, "fetch_points", fetch_points)
    monkeypatch.setattr(feed, "create_feed_item", create_feed_item)
    return out


def test_a_finished_test_is_marked_and_its_result_posted_once(monkeypatch):
    out = _finish_env(monkeypatch, started=TODAY - timedelta(days=14), patch_rows=[{"id": "iv1"}])
    done = asyncio.run(experiments.check_card_experiments("u1"))
    assert len(done) == 1
    assert out["patched"][0]["status"] == "followed_up" and out["patched"][0]["result_improved"] is True
    item = out["feed"][0]
    assert item["kind"] == "experiment_result" and "clear change" in item["body"] and item["card_id"] == "c1"


def test_a_test_that_is_not_due_is_left_alone(monkeypatch):
    out = _finish_env(monkeypatch, started=TODAY - timedelta(days=5), patch_rows=[{"id": "iv1"}])
    assert asyncio.run(experiments.check_card_experiments("u1")) == []
    assert out["patched"] == [] and out["feed"] == []


def test_a_test_another_check_already_finished_is_not_posted_twice(monkeypatch):
    out = _finish_env(monkeypatch, started=TODAY - timedelta(days=14), patch_rows=[])
    assert asyncio.run(experiments.check_card_experiments("u1")) == []
    assert out["feed"] == []

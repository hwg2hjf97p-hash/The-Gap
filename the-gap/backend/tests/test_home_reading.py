from datetime import datetime, timedelta, timezone

from routers.metric_insight import BRIEF_SUFFIX, brief_is_fresh
from utils.metric_personal_insight import BRIEF_SYSTEM_PROMPT, build_facts

NOW = datetime(2026, 10, 23, 9, 0, tzinfo=timezone.utc)


def saved(minutes_ago: float, reading=6.0) -> dict:
    return {"generated_at": (NOW - timedelta(minutes=minutes_ago)).isoformat(), "reading_value": reading, "insight_text": "x"}


# ── when the Home note is redone ─────────────────────────────────────────────
def test_a_fresh_note_is_kept_even_if_the_reading_moved():
    assert brief_is_fresh(saved(5, reading=6.0), 7.5, NOW)


def test_a_note_is_kept_within_the_hour_while_the_reading_is_the_same():
    assert brief_is_fresh(saved(40, reading=6.0), 6.0, NOW)


def test_a_note_is_redone_once_the_reading_has_moved():
    assert not brief_is_fresh(saved(40, reading=6.0), 7.5, NOW)


def test_a_note_older_than_an_hour_is_always_redone():
    assert not brief_is_fresh(saved(61, reading=6.0), 6.0, NOW)


def test_a_note_with_an_unreadable_time_is_redone():
    assert not brief_is_fresh({"generated_at": "not a time", "reading_value": 6.0}, 6.0, NOW)


def test_a_note_with_no_saved_reading_is_kept_within_the_hour():
    assert brief_is_fresh({"generated_at": saved(30)["generated_at"], "reading_value": None}, 6.0, NOW)


def test_the_home_note_has_its_own_cache_key():
    assert ("sleep_total_min" + BRIEF_SUFFIX) != "sleep_total_min"


# ── what the writer is told ──────────────────────────────────────────────────
def test_the_brief_note_sees_the_reading_and_how_it_compares_with_their_usual():
    facts = build_facts("Sleep Duration", "5.9", "hrs", "7-9 hours is recommended.", ["Sleep -> HRV"], {"age": 30}, brief=True, personal_context="0.8 hrs below your usual Thursday (6.7hrs)")
    assert "5.9 hrs" in facts
    assert "own usual: 0.8 hrs below your usual Thursday" in facts
    assert "7-9 hours" in facts


def test_the_brief_note_is_not_given_hypotheses_or_profile():
    facts = build_facts("HRV", "42", "ms", "20-80ms is common.", ["Alcohol -> HRV"], {"age": 30, "weight_kg": 80}, brief=True)
    assert "Alcohol" not in facts
    assert "age" not in facts and "weight" not in facts


def test_the_full_reading_still_gets_hypotheses_and_profile():
    facts = build_facts("HRV", "42", "ms", "20-80ms is common.", ["Alcohol -> HRV"], {"age": 30, "weight_kg": 80})
    assert "Alcohol -> HRV" in facts
    assert "age 30" in facts and "weight 80kg" in facts


def test_the_brief_note_says_none_yet_when_nothing_is_tested_for_the_full_reading():
    assert "none yet" in build_facts("Sleep Score", "80", "", "", [])


def test_no_personal_line_when_there_is_nothing_to_compare_with():
    assert "own usual" not in build_facts("HRV", "42", "ms", "range", [], brief=True, personal_context="  ")


def test_the_brief_prompt_keeps_it_short_and_never_advice():
    assert "35 words" in BRIEF_SYSTEM_PROMPT
    assert "never tell them what to do about their health" in BRIEF_SYSTEM_PROMPT


# ── the journal reader knows the wordings the new list uses ─────────────────
def test_the_journal_reader_counts_the_list_wordings():
    from utils.journal_extract import EXTRACTION_SYSTEM_PROMPT as prompt

    for words in ("bullied", "walked over", "don't get along with", "praise from a boss", "really nice meal out"):
        assert words in prompt

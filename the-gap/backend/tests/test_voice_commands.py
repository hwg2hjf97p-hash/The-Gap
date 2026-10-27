import pytest

from utils.log_router import parse_log
from utils.voice_commands import Problem, check_command, clean_phrase, describe

BIG = {"phrase": "big bottle", "kind": "water", "amount": 750}
PICK = {"phrase": "pick me up", "kind": "caffeine", "amount": 1}
SHAKE = {"phrase": "morning shake", "kind": "saved_food", "amount": 1, "ref_id": "f1", "ref_name": "Protein shake"}


def actions(text, custom):
    return parse_log(text, 12.0, None, None, custom).actions


# ── a phrase logs what the person chose ─────────────────────────────────────
def test_a_phrase_logs_its_amount_of_water():
    got = actions("drank my big bottle", [BIG])
    assert [(a.kind, a.amount) for a in got] == [("water", 750)]


def test_a_number_said_before_the_phrase_multiplies_it():
    got = actions("two big bottles", [BIG])
    assert [(a.kind, a.amount) for a in got] == [("water", 1500)]


def test_the_built_in_water_rule_does_not_count_the_same_drink_again():
    got = actions("drank my big bottle of water", [BIG])
    assert [(a.kind, a.amount) for a in got] == [("water", 750)]


def test_the_longer_phrase_wins_over_a_shorter_one_inside_it():
    got = actions("had a big bottle", [{"phrase": "bottle", "kind": "water", "amount": 330}, BIG])
    assert [(a.kind, a.amount) for a in got] == [("water", 750)]


def test_sentences_without_a_phrase_work_as_before():
    got = actions("just drank 300ml of water", [BIG])
    assert [(a.kind, a.amount) for a in got] == [("water", 300)]


def test_no_shortcuts_at_all_still_works():
    assert [(a.kind, a.amount) for a in parse_log("500ml of water", 12.0).actions] == [("water", 500)]


def test_a_count_phrase_logs_drinks_and_says_so():
    one = actions("need a pick me up", [PICK])
    assert [(a.kind, a.amount, a.label) for a in one] == [("caffeine", 1, "1 coffee")]
    two = actions("two pick me ups", [PICK])
    assert [(a.kind, a.amount, a.label) for a in two] == [("caffeine", 2, "2 coffees")]


def test_a_phrase_for_alcohol_logs_that_many_drinks():
    got = actions("had my sundowner", [{"phrase": "sundowner", "kind": "alcohol", "amount": 2}])
    assert [(a.kind, a.amount, a.label) for a in got] == [("alcohol", 2, "2 alcoholic drinks")]


def test_the_built_in_rule_for_a_handled_kind_stands_aside():
    # "flat white" would be a coffee by itself; with the person's own coffee phrase it is counted once, not twice.
    got = actions("a flat white pick me up", [PICK])
    assert [a.kind for a in got] == ["caffeine"] and got[0].amount == 1


def test_a_saved_food_phrase_points_at_the_saved_food_and_scales_with_a_number():
    one = actions("had my morning shake", [SHAKE])[0]
    assert (one.kind, one.ref_id, one.label, one.servings) == ("saved_food", "f1", "Protein shake", 1.0)
    two = actions("two morning shakes", [SHAKE])[0]
    assert two.servings == 2.0


def test_a_phrase_only_matches_whole_words():
    assert actions("fixed the engine", [{"phrase": "gin", "kind": "alcohol", "amount": 1}]) == []


def test_other_things_in_the_sentence_are_still_understood():
    got = actions("big bottle then I weigh 72.4 kg", [BIG])
    assert sorted(a.kind for a in got) == ["water", "weight"]


# ── what a phrase is allowed to be ──────────────────────────────────────────
def test_a_phrase_is_cleaned_to_plain_lower_case_words():
    assert clean_phrase("  Big   Bottle ") == "big bottle"


@pytest.mark.parametrize("bad", ["", "a", "the and", "250", "big bottle!", "x" * 50, "one two three four five six seven", "café"])
def test_phrases_that_would_catch_too_much_or_use_odd_characters_are_refused(bad):
    with pytest.raises(Problem):
        clean_phrase(bad)


def test_water_amounts_are_kept_sensible():
    assert check_command("water", 750, None, [], [])["amount"] == 750
    for bad in (20, 5000):
        with pytest.raises(Problem):
            check_command("water", bad, None, [], [])


def test_counts_are_whole_numbers_from_one_to_ten():
    assert check_command("caffeine", 2, None, [], [])["amount"] == 2
    for bad in (0, 2.5, 11):
        with pytest.raises(Problem):
            check_command("alcohol", bad, None, [], [])


def test_a_saved_food_must_be_one_of_the_persons_own():
    foods = [{"id": "f1", "name": "Protein shake"}]
    got = check_command("saved_food", 1.5, "f1", foods, [])
    assert (got["ref_id"], got["ref_name"], got["amount"]) == ("f1", "Protein shake", 1.5)
    with pytest.raises(Problem):
        check_command("saved_food", 1, "someone-elses", foods, [])
    with pytest.raises(Problem):
        check_command("saved_meal", 1, "f1", foods, [])  # f1 is a food, not a meal


def test_an_unknown_kind_is_refused():
    with pytest.raises(Problem):
        check_command("steroids", 1, None, [], [])


def test_a_shortcut_is_described_in_words():
    assert describe({"kind": "water", "amount": 750}) == "750 ml of water"
    assert describe({"kind": "water", "amount": 1500}) == "1,500 ml of water"
    assert describe({"kind": "caffeine", "amount": 1}) == "1 coffee"
    assert describe({"kind": "caffeine", "amount": 3}) == "3 coffees"
    assert describe({"kind": "saved_food", "amount": 2, "ref_name": "Protein shake"}) == "2 × Protein shake"
    assert describe({"kind": "saved_food", "amount": 1, "ref_name": "Protein shake"}) == "Protein shake"


# ── numbers in a phrase: said as a word or a digit ──────────────────────────
TWO_DRINKS = {"phrase": "had 2 drinks of water", "kind": "water", "amount": 500}


def test_a_phrase_with_a_digit_matches_the_number_said_as_a_word():
    # iPhone dictation writes "two" where the phrase was typed as "2".
    got = actions("had two drinks of water", [TWO_DRINKS])
    assert [(a.kind, a.amount) for a in got] == [("water", 500)]


def test_a_phrase_with_a_digit_still_matches_the_digit():
    got = actions("had 2 drinks of water", [TWO_DRINKS])
    assert [(a.kind, a.amount) for a in got] == [("water", 500)]


def test_a_phrase_typed_as_a_word_matches_the_digit_said():
    got = actions("had 2 drinks of water", [{"phrase": "had two drinks of water", "kind": "water", "amount": 500}])
    assert [(a.kind, a.amount) for a in got] == [("water", 500)]


def test_a_different_number_does_not_match_the_phrase():
    got = actions("had three drinks of water", [TWO_DRINKS])
    assert [(a.kind, a.amount) for a in got] != [("water", 500)]


def test_ten_matches_as_a_digit_and_a_word():
    cmd = {"phrase": "ten sips", "kind": "water", "amount": 100}
    assert [(a.kind, a.amount) for a in actions("took 10 sips", [cmd])] == [("water", 100)]
    assert [(a.kind, a.amount) for a in actions("took ten sips", [cmd])] == [("water", 100)]

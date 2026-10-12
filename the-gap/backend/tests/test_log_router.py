import pytest

from utils.log_router import guess_meal, match_saved, parse_log, spoken_summary, time_bucket

PROTEIN = {"id": "f1", "name": "Protein drink", "aliases": ["shake"], "use_count": 4}
BANANA_BREAD = {"id": "f2", "name": "Banana bread", "aliases": [], "use_count": 1}
BREKKY = {"id": "m1", "name": "Brekky", "aliases": ["usual breakfast"], "use_count": 9}


def kinds(text, hour=12.0, foods=None, meals=None):
    return [(a.kind, a.amount) for a in parse_log(text, hour, foods or [], meals or []).actions]


# ── water ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "text, ml",
    [
        ("just drank 300ml of water", 300),
        ("drank 500 ml water", 500),
        ("had two glasses of water", 500),
        ("a glass of water", 250),
        ("just finished a bottle of water", 500),
        ("1.5 litres of water", 1500),
        ("drank a litre of water", 1000),
        ("had some water", 250),
        ("3 cups of water", 750),
    ],
)
def test_water_amounts(text, ml):
    assert kinds(text) == [("water", ml)]


def test_too_much_water_in_one_go_is_not_logged_blindly():
    parsed = parse_log("drank 50 litres of water", 12)
    assert parsed.actions == [] and parsed.unsure == ["water amount"]


def test_a_drink_that_is_not_water_is_not_water():
    assert kinds("drank 500ml of cola") == []


# ── cigarettes ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "text, count",
    [
        ("just had a cigarette", 1),
        ("had two cigarettes", 2),
        ("just had a ciggy", 1),
        ("3 durries today", 3),
        ("had a smoke", 1),
        ("just smoked", 1),
    ],
)
def test_cigarettes(text, count):
    assert kinds(text) == [("cigarettes", count)]


def test_smoked_food_is_food_not_a_cigarette():
    assert [k for k, _ in kinds("had smoked salmon for lunch")] == ["food_note"]


# ── alcohol, coffee, energy drinks ───────────────────────────────────────────

@pytest.mark.parametrize(
    "text, count",
    [("had a beer", 1), ("two glasses of wine", 2), ("had 3 pints", 3), ("just had a cocktail", 1), ("had wine with dinner", 1)],
)
def test_alcohol(text, count):
    assert ("alcohol", count) in kinds(text)


def test_things_that_are_not_alcohol():
    for text in ("had a ginger beer", "a pint of milk", "a shot of espresso", "non-alcoholic beer"):
        assert "alcohol" not in [k for k, _ in kinds(text)], text


def test_a_bottle_of_wine_is_not_guessed_at():
    parsed = parse_log("finished a bottle of wine", 21)
    assert [a.kind for a in parsed.actions] == [] and parsed.unsure


@pytest.mark.parametrize("text, count", [("just had a coffee", 1), ("five coffees this morning", 5), ("had a flat white", 1), ("two lattes", 2), ("grabbed a long black", 1)])
def test_coffee(text, count):
    assert ("caffeine", count) in kinds(text)


def test_decaf_is_not_counted_and_an_energy_drink_is_not_a_coffee():
    assert kinds("had a decaf coffee") == []
    assert kinds("had a red bull") == [("energy_drink", 1)]
    assert kinds("two monsters") == [("energy_drink", 2)]


def test_a_shot_of_espresso_is_a_coffee():
    assert ("caffeine", 1) in kinds("a shot of espresso")


def test_several_things_in_one_sentence():
    assert sorted(kinds("had a beer and two cigarettes")) == [("alcohol", 1), ("cigarettes", 2)]


# ── weight ───────────────────────────────────────────────────────────────────

def test_weight():
    assert kinds("I weigh 72.4 kg") == [("weight", 72.4)]
    assert kinds("weighed in at 160 pounds") == [("weight", 72.6)]
    assert kinds("my weight is 81 kilos") == [("weight", 81.0)]
    assert kinds("I weigh 7 kg") == []          # not a human weight


# ── saved foods and meals ────────────────────────────────────────────────────

def test_my_regular_protein_drink_is_the_saved_food():
    parsed = parse_log("just drank my regular protein drink", 8, [PROTEIN], [])
    assert [(a.kind, a.ref_id, a.servings) for a in parsed.actions] == [("saved_food", "f1", 1.0)]


def test_a_number_before_the_name_sets_the_servings():
    parsed = parse_log("had two protein drinks", 8, [PROTEIN], [])
    assert parsed.actions[0].servings == 2.0
    assert parse_log("had a protein drink", 8, [PROTEIN], []).actions[0].servings == 1.0


def test_an_alternative_name_matches_too():
    assert [a.kind for a in parse_log("had my shake", 8, [{**PROTEIN, "name": "Protein drink", "aliases": ["shake"]}], []).actions] == ["saved_food"]


def test_saved_meals_are_matched_and_log_the_meal_not_a_guess():
    parsed = parse_log("had my usual brekky", 8, [PROTEIN], [BREKKY])
    assert [(a.kind, a.ref_id) for a in parsed.actions] == [("saved_meal", "m1")]


def test_a_saved_name_needs_all_its_words():
    assert match_saved("had a protein bar", [PROTEIN]) is None
    assert match_saved("had banana", [BANANA_BREAD]) is None


def test_the_most_specific_then_most_used_saved_item_wins():
    plain = {"id": "a", "name": "Protein", "aliases": [], "use_count": 50}
    hit = match_saved("had my protein drink", [plain, PROTEIN])
    assert hit and hit[0]["id"] == "f1"


def test_a_saved_food_and_a_coffee_in_one_sentence_are_both_logged():
    got = [a.kind for a in parse_log("had my protein drink and a coffee", 8, [PROTEIN], []).actions]
    assert got == ["saved_food", "caffeine"]


# ── foods nobody saved, and plain notes ──────────────────────────────────────

def test_food_nobody_saved_is_kept_as_a_note_not_guessed():
    for text in ("had 2 eggs and bacon for breakfast", "had a banana", "just ate a burger", "had pasta for dinner"):
        assert [a.kind for a in parse_log(text, 12).actions] == ["food_note"], text


def test_ordinary_sentences_stay_plain_notes():
    for text in ("boss just yelled at me", "I had a bad day", "feeling anxious about tomorrow", "slept terribly", "had a great meeting"):
        assert parse_log(text, 12).actions == [], text


def test_a_coffee_alone_is_not_also_a_food_note_but_a_coffee_and_toast_is():
    assert [a.kind for a in parse_log("had a coffee", 8).actions] == ["caffeine"]
    assert [a.kind for a in parse_log("had a coffee and toast", 8).actions] == ["caffeine", "food_note"]


def test_empty_text_does_nothing():
    assert parse_log("   ", 8).actions == []


# ── clock helpers and the spoken answer ──────────────────────────────────────

def test_time_buckets_match_the_check_in_words():
    assert [time_bucket(h) for h in (6, 11.9, 12, 16.9, 17, 21.9, 22, 2)] == ["morning", "morning", "afternoon", "afternoon", "evening", "evening", "late", "late"]


def test_the_meal_is_guessed_from_the_hour():
    assert [guess_meal(h) for h in (7, 12, 16, 19, 23)] == ["breakfast", "lunch", "snack", "dinner", "snack"]


def test_the_spoken_answers_are_short_and_say_what_was_logged():
    assert spoken_summary(["1 cigarette, 3 today"], False, [], False) == "Logged 1 cigarette, 3 today."
    assert spoken_summary(["1 coffee", "300 ml of water"], False, [], False) == "Logged 1 coffee and 300 ml of water."
    assert spoken_summary([], True, [], False) == "Saved to your journal."
    assert "kept it as a note" in spoken_summary([], True, [], True)
    assert "wasn't sure" in spoken_summary([], True, ["a bottle (how many drinks?)"], False)

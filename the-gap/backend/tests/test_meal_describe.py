import asyncio

from utils import meal_describe as md


def run(coro):
    return asyncio.run(coro)


# ── reading what the AI sends back ───────────────────────────────────────────
def test_a_reply_wrapped_in_code_fences_is_still_read():
    assert md.parse_json('```json\n{"name": "Spag bol"}\n```') == {"name": "Spag bol"}


def test_something_that_is_not_a_json_object_is_refused():
    assert md.parse_json("Sure! Here is your meal.") is None
    assert md.parse_json("[1, 2, 3]") is None
    assert md.parse_json("") is None


def good(**changes):
    base = {"name": "mince", "search": "ground beef raw", "grams": 500, "guessed": False, "per100": {"calories": 250, "protein_g": 17, "carbs_g": 0, "fat_g": 20}}
    base.update(changes)
    return base


def test_a_good_reply_is_kept_and_tidied():
    cleaned = md.clean_description({"name": " Spag  bol ", "serves": 4.0, "ingredients": [good()], "notes": ["Assumed a standard jar."]})
    assert cleaned["name"] == "Spag bol" and cleaned["serves"] == 4
    assert cleaned["ingredients"][0]["grams"] == 500 and cleaned["ingredients"][0]["per100"]["calories"] == 250
    assert cleaned["notes"] == ["Assumed a standard jar."]


def test_lines_without_a_name_or_a_sensible_weight_are_dropped():
    cleaned = md.clean_description({"ingredients": [good(name=""), good(grams=0), good(grams=999999), good(grams="lots"), "mince", good(name="onion", grams=150)]})
    assert [i["name"] for i in cleaned["ingredients"]] == ["onion"]


def test_absurd_numbers_from_the_ai_are_not_trusted():
    cleaned = md.clean_description({"ingredients": [good(per100={"calories": 5000, "protein_g": 17})]})
    assert cleaned["ingredients"][0]["per100"] is None


def test_serves_outside_one_to_forty_is_ignored_and_the_list_is_capped():
    assert md.clean_description({"serves": 0, "ingredients": []})["serves"] is None
    assert md.clean_description({"serves": 500, "ingredients": []})["serves"] is None
    many = [good(name=f"item {n}") for n in range(60)]
    assert len(md.clean_description({"ingredients": many})["ingredients"]) == md.MAX_INGREDIENTS


def test_notes_are_limited_to_three():
    assert len(md.clean_description({"ingredients": [], "notes": ["a", "b", "c", "d", "e"]})["notes"]) == 3


# ── choosing the database food ───────────────────────────────────────────────
def test_a_foods_numbers_are_worked_out_per_100_g():
    banana = {"serving_grams": 118, "per_serving": {"calories": 105, "protein_g": 1.3, "carbs_g": 27, "fat_g": 0.4}}
    assert md.per100_of(banana)["calories"] == round(105 * 100 / 118, 1)
    assert md.per100_of({"serving_grams": None, "per_serving": {"calories": 105}}) is None


def test_a_database_food_far_from_what_was_expected_is_not_trusted():
    assert md.plausible({"calories": 160}, {"calories": 350}) is False  # cooked pasta where dry was meant
    assert md.plausible({"calories": 340}, {"calories": 350}) is True
    assert md.plausible({"calories": 30}, {"calories": 60}) is True      # small numbers: close enough in kcal
    assert md.plausible({"calories": 500}, None) is True


def test_a_name_is_tried_whole_and_then_without_its_last_word():
    assert md.search_terms("ground beef raw") == ["ground beef raw", "ground beef"]
    assert md.search_terms("onion") == ["onion"]


def item(name, kcal, grams=100, source="usda"):
    return {"name": name, "source": source, "serving_grams": grams, "per_serving": {"calories": kcal, "protein_g": 10, "carbs_g": 5, "fat_g": 8}}


def test_the_first_sensible_database_match_is_used():
    async def search(term):
        return [item("Spaghetti, cooked", 158), item("Spaghetti, dry", 371)]

    ing = md.clean_description({"ingredients": [good(name="spaghetti", search="spaghetti dry", grams=200, per100={"calories": 350})]})["ingredients"]
    [done] = run(md.ground(ing, search))
    assert done["name"] == "Spaghetti, dry" and done["source"] == "usda" and done["amount"] == 200 and done["unit"] == "g"
    assert done["heard"] == "spaghetti" and done["per_serving"]["calories"] == 371


def test_with_no_database_match_the_estimate_is_used_and_marked():
    async def search(term):
        return []

    ing = md.clean_description({"ingredients": [good(name="nonna's sauce", search="nonna sauce", guessed=True)]})["ingredients"]
    [done] = run(md.ground(ing, search))
    assert done["source"] == "estimate" and done["guessed"] is True and done["per_serving"]["calories"] == 250


def test_a_failed_lookup_falls_back_to_the_estimate_instead_of_failing():
    async def search(term):
        raise RuntimeError("rate limited")

    ing = md.clean_description({"ingredients": [good()]})["ingredients"]
    [done] = run(md.ground(ing, search))
    assert done["source"] == "estimate"


def test_an_ingredient_with_no_match_and_no_estimate_is_left_out():
    async def search(term):
        return []

    ing = md.clean_description({"ingredients": [good(per100=None), good(name="onion", per100=None)]})["ingredients"]
    assert run(md.ground(ing, search)) == []


def test_the_order_of_the_ingredients_is_kept():
    async def search(term):
        return [item(term.title(), 100)]

    names = ["salt", "onion", "garlic", "beef"]
    ing = md.clean_description({"ingredients": [good(name=n, search=n, per100={"calories": 100}) for n in names]})["ingredients"]
    assert [d["heard"] for d in run(md.ground(ing, search, at_a_time=2))] == names

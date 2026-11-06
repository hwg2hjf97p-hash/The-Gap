import pytest

from routers.saved_foods import BuildMealBody
from utils import meal_builder as mb


ING = {"name": "Chicken stir fry (recipe estimate)", "per_serving": {"calories": 420, "protein_g": 38, "carbs_g": 0, "fat_g": 0}, "amount": 1, "unit": "serving", "source": "recipe"}


def idea(**over):
    base = {
        "summary": "A quick one-pan dinner.",
        "time_min": 25,
        "servings": 2,
        "ingredients": ["400 g chicken breast", "2 cups broccoli", "1 tbsp soy sauce"],
        "steps": ["Slice the chicken.", "Fry for 6 minutes.", "Add the broccoli and sauce."],
    }
    base.update(over)
    return base


def test_a_saved_recipe_idea_keeps_its_ingredients_and_method():
    cleaned = mb.clean_suggested(idea())
    assert cleaned == idea()


def test_lines_are_trimmed_capped_and_blanks_dropped():
    cleaned = mb.clean_suggested(idea(ingredients=["  400 g   chicken  ", "", "   "], steps=["x" * 900, "  "], summary="  a  b  "))
    assert cleaned["ingredients"] == ["400 g chicken"]
    assert len(cleaned["steps"]) == 1 and len(cleaned["steps"][0]) == 600
    assert cleaned["summary"] == "a b"


def test_silly_numbers_are_dropped_not_stored():
    cleaned = mb.clean_suggested(idea(time_min=99999, servings=0))
    assert cleaned["time_min"] is None and cleaned["servings"] is None
    assert mb.clean_suggested(idea(time_min="soon"))["time_min"] is None


@pytest.mark.parametrize("junk", [None, "text", 5, [], {}, {"ingredients": [], "steps": [], "summary": ""}, {"unrelated": 1}])
def test_nothing_worth_keeping_gives_none(junk):
    assert mb.clean_suggested(junk) is None


def test_extra_fields_from_the_database_or_the_app_are_not_kept():
    cleaned = mb.clean_suggested({**idea(), "secret": "x", "name": "y"})
    assert set(cleaned) == {"summary", "time_min", "servings", "ingredients", "steps"}


def test_the_recipe_stored_with_a_meal_includes_the_text_only_when_there_is_some():
    plain = mb.recipe_json("Spag bol", 4, None, [ING])
    assert "suggested" not in plain and plain["serves"] == 4
    kept = mb.recipe_json("Stir fry", 1, None, [ING], mb.clean_suggested(idea()))
    assert kept["suggested"]["steps"][0] == "Slice the chicken." and kept["ingredients"][0]["name"].startswith("Chicken")


def test_the_request_accepts_a_suggested_recipe_and_refuses_an_absurd_one():
    body = BuildMealBody(name="Stir fry", ingredients=[ING], suggested=idea())
    assert body.suggested.servings == 2
    assert BuildMealBody(name="Plain", ingredients=[ING]).suggested is None
    with pytest.raises(Exception):
        BuildMealBody(name="Too long", ingredients=[ING], suggested=idea(steps=["s"] * 31))
    with pytest.raises(Exception):
        BuildMealBody(name="Too many", ingredients=[ING], suggested=idea(ingredients=["i"] * 41))


def test_a_saved_recipe_idea_is_a_one_serve_meal_with_the_estimate_as_its_numbers():
    items = mb.build_items([ING], 1)
    assert mb.per_serve_totals(items)["calories"] == 420 and mb.per_serve_totals(items)["protein_g"] == 38

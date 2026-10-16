from utils import meals


def test_the_meals_load_with_a_source_and_enough_of_them():
    loaded = meals.load_meals()
    assert len(loaded) >= 35
    names = [m["name"] for m in loaded]
    assert len(names) == len(set(names))


def test_every_meal_has_complete_numbers_and_a_recipe_link():
    for m in meals.load_meals():
        per = m["per_serving"]
        assert all(v >= 0 for v in per.values()) and 50 <= per["calories"] <= 1500, m["name"]
        assert m["recipe_url"].startswith("https://www.recipetineats.com/") and m["recipe_url"].endswith("/"), m["name"]
        assert m["brand"] == "RecipeTin Eats" and m["recipe_source"] == "RecipeTin Eats"
        assert m["serving_label"] and m["source"] == "common_meal"


def test_published_energy_agrees_with_the_published_macros():
    for m in meals.load_meals():
        per = m["per_serving"]
        expected = 4 * per["protein_g"] + 4 * per["carbs_g"] + 9 * per["fat_g"]
        assert abs(per["calories"] - expected) / expected <= 0.20, m["name"]


def test_typing_a_dish_finds_it_including_common_spellings():
    for text in ("spaghetti bolognese", "spaghetti bolognaise", "spag bol", "bolognaise"):
        assert meals.search(text)[0]["name"] == "Spaghetti Bolognese", text
    assert meals.search("mac and cheese")[0]["name"] == "Baked Mac and Cheese"
    assert meals.search("beef and veg stir fry")[0]["name"] == "Chinese Beef Stir Fry"
    assert meals.search("chicken parmi")[0]["name"] == "Chicken Parmigiana"
    assert meals.search("butter chicken")[0]["name"] == "Butter Chicken"


def test_results_carry_the_link_but_not_the_internal_fields():
    result = meals.search("lasagne")[0]
    assert result["recipe_url"].startswith("https://www.recipetineats.com/")
    assert not any(k.startswith("_") for k in result)


def test_a_search_gives_no_more_than_the_limit_and_nothing_for_junk():
    assert len(meals.search("chicken", 2)) == 2
    assert meals.search("quinoa salad") == []
    assert meals.search("x") == []
    assert meals.search("") == []


def test_a_recipe_idea_from_this_week_can_be_found_and_keeps_its_recipe():
    week = [
        {"title": "Beef and Veg Stir-fry with Jasmine Rice", "summary": "Quick.", "time_min": 25, "servings": 2,
         "ingredients": ["300 g beef", "2 cups veg"], "steps": ["Fry beef", "Add veg"], "estimate": {"calories": 520, "protein_g": 38}},
        {"title": "Overnight oats", "ingredients": ["oats"], "steps": ["Soak"], "estimate": {"calories": 350, "protein_g": 15}},
        {"title": "No numbers", "ingredients": ["x"], "steps": ["y"], "estimate": {"calories": None, "protein_g": None}},
    ]
    found = meals.from_week_recipes(week, "beef stir fry")
    assert [f["name"] for f in found] == ["Beef and Veg Stir-fry with Jasmine Rice"]
    item = found[0]
    assert item["source"] == "recipe" and item["per_serving"]["calories"] == 520.0 and item["per_serving"]["protein_g"] == 38.0
    assert item["recipe"]["steps"] == ["Fry beef", "Add veg"] and "recipe_url" not in item
    assert meals.from_week_recipes(week, "no numbers") == []
    assert meals.from_week_recipes(week, "pizza") == []
    assert meals.from_week_recipes([], "oats") == []

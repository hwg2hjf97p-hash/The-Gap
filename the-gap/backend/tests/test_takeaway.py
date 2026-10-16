from utils import takeaway


def mcd():
    return next(c for c in takeaway.load_chains() if c["name"] == "McDonald's")


def test_the_chain_data_loads_with_its_source_and_a_real_number_of_items():
    chain = mcd()
    assert len(chain["items"]) >= 100 and chain["collected"] and "mcdonalds.com" in chain["source"]


def test_every_item_is_complete_and_names_are_unique():
    names = [i["name"] for i in mcd()["items"]]
    assert len(names) == len(set(names))
    for item in mcd()["items"]:
        per = item["per_serving"]
        assert all(v >= 0 for v in per.values()) and per["calories"] <= 2000, item["name"]


def test_published_energy_agrees_with_the_published_macros():
    # Nothing is kept whose energy and macros disagree by more than 20%, so a typo on the chain's own page can't slip in.
    for item in mcd()["items"]:
        per = item["per_serving"]
        expected = 4 * per["protein_g"] + 4 * per["carbs_g"] + 9 * per["fat_g"]
        if per["calories"] > 50:
            assert abs(per["calories"] - expected) / per["calories"] <= 0.20, item["name"]


def test_meals_are_the_sum_of_their_parts():
    by_name = {i["name"]: i["per_serving"] for i in mcd()["items"]}
    meal = next(m for m in mcd()["meals"] if m["name"] == "Quarter Pounder Meal (Large) with Coke")
    parts = [by_name["Quarter Pounder"], by_name["Fries (Large)"], by_name["Coca-Cola (Large)"]]
    assert meal["per_serving"]["calories"] == round(sum(p["calories"] for p in parts), 1)
    assert meal["per_serving"]["protein_g"] == round(sum(p["protein_g"] for p in parts), 1)
    assert meal["serving_label"] == "1 meal" and meal["source"] == "takeaway"


def test_there_is_a_meal_for_each_main_size_and_drink():
    assert len(mcd()["meals"]) == 21 * 3 * 2


def test_the_chain_name_or_a_nickname_finds_its_dishes():
    for text in ("mcdonalds", "McDonald's", "maccas", "macca's"):
        results = takeaway.search(text, 8)
        assert results and all(r["brand"] == "McDonald's" for r in results), text


def test_a_dish_name_finds_it_with_or_without_the_chain():
    assert takeaway.search("big mac")[0]["name"] == "Big Mac"
    assert takeaway.search("maccas big mac")[0]["name"] == "Big Mac"
    assert takeaway.search("quart")[0]["name"].startswith("Quarter Pounder")


def test_asking_for_a_meal_gives_that_dishs_meals_smallest_to_largest():
    results = takeaway.search("quarter pounder meal", 8)
    assert results and all("Meal" in r["name"] for r in results)
    assert [r["name"] for r in results[:6]] == [
        "Quarter Pounder Meal (Small) with Coke", "Quarter Pounder Meal (Small) with Coke Zero",
        "Quarter Pounder Meal (Medium) with Coke", "Quarter Pounder Meal (Medium) with Coke Zero",
        "Quarter Pounder Meal (Large) with Coke", "Quarter Pounder Meal (Large) with Coke Zero",
    ]
    assert takeaway.search("large quarter pounder meal coke")[0]["name"] == "Quarter Pounder Meal (Large) with Coke"


def test_something_that_isnt_on_a_menu_finds_nothing():
    assert takeaway.search("quinoa salad") == []
    assert takeaway.search("x") == []


def test_the_summary_lists_each_chain():
    assert takeaway.chains_summary()[0]["name"] == "McDonald's"

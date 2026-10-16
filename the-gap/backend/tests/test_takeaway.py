from utils import takeaway

CHAINS = ("McDonald's", "Guzman y Gomez", "Hungry Jack's", "KFC", "Domino's", "Subway")


def chain(name):
    return next(c for c in takeaway.load_chains() if c["name"] == name)


def test_every_chain_loads_with_its_source_and_a_real_number_of_items():
    for name in CHAINS:
        c = chain(name)
        assert len(c["items"]) >= 15 and c["collected"], name
        assert "http" in c["source"], name


def test_mcdonalds_is_the_big_one():
    assert len(chain("McDonald's")["items"]) >= 100 and "mcdonalds.com" in chain("McDonald's")["source"]


def test_every_item_is_complete_and_names_are_unique_within_a_chain():
    for c in takeaway.load_chains():
        names = [i["name"] for i in c["items"]]
        assert len(names) == len(set(names)), c["name"]
        for item in c["items"]:
            per = item["per_serving"]
            assert all(v >= 0 for v in per.values()) and per["calories"] <= 5000, (c["name"], item["name"])
            assert item["brand"] == c["name"] and item["source"] == "takeaway"


def test_published_energy_agrees_with_the_published_macros():
    # Nothing is kept whose energy and macros disagree by more than the chain's allowed gap (20% unless noted), so a
    # typo on the chain's own page can't slip in.
    for c in takeaway.load_chains():
        for item in c["items"]:
            per = item["per_serving"]
            expected = 4 * per["protein_g"] + 4 * per["carbs_g"] + 9 * per["fat_g"]
            if per["calories"] > 50:
                assert abs(per["calories"] - expected) / expected <= c["max_gap"] + 0.0001, (c["name"], item["name"])


def test_meals_are_the_sum_of_their_parts():
    by_name = {i["name"]: i["per_serving"] for i in chain("McDonald's")["items"]}
    meal = next(m for m in chain("McDonald's")["meals"] if m["name"] == "Quarter Pounder Meal (Large) with Coke")
    parts = [by_name["Quarter Pounder"], by_name["Fries (Large)"], by_name["Coca-Cola (Large)"]]
    assert meal["per_serving"]["calories"] == round(sum(p["calories"] for p in parts), 1)
    assert meal["per_serving"]["protein_g"] == round(sum(p["protein_g"] for p in parts), 1)
    assert meal["serving_label"] == "1 meal" and meal["source"] == "takeaway"


def test_there_is_a_meal_for_each_main_size_and_drink():
    assert len(chain("McDonald's")["meals"]) == 21 * 3 * 2


def test_serving_labels_say_what_one_serve_is():
    pizza = next(i for i in chain("Domino's")["items"] if i["category"] == "pizza")
    assert pizza["serving_label"].startswith("1 slice")
    assert next(i for i in chain("Subway")["items"])["serving_label"] == "1 six-inch sub"
    assert next(i for i in chain("Guzman y Gomez")["items"] if i["category"] == "burrito")["serving_label"] == "1 burrito"
    assert next(i for i in chain("McDonald's")["items"])["serving_label"] == "1 serve"


def test_the_chain_name_or_a_nickname_finds_its_dishes():
    for text, brand in (
        ("mcdonalds", "McDonald's"), ("McDonald's", "McDonald's"), ("maccas", "McDonald's"), ("macca's", "McDonald's"),
        ("gyg", "Guzman y Gomez"), ("guzman y gomez", "Guzman y Gomez"),
        ("hungry jacks", "Hungry Jack's"), ("hj", "Hungry Jack's"), ("kfc", "KFC"),
        ("dominos", "Domino's"), ("domino's", "Domino's"), ("subway", "Subway"),
    ):
        results = takeaway.search(text, 8)
        assert results and all(r["brand"] == brand for r in results), text


def test_a_dish_name_finds_it_with_or_without_the_chain():
    assert takeaway.search("big mac")[0]["name"] == "Big Mac"
    assert takeaway.search("maccas big mac")[0]["name"] == "Big Mac"
    assert takeaway.search("quart")[0]["name"].startswith("Quarter Pounder")
    assert takeaway.search("zinger burger")[0]["brand"] == "KFC"
    assert takeaway.search("whopper")[0]["brand"] == "Hungry Jack's"
    assert takeaway.search("gyg burrito grilled chicken")[0]["name"] == "Burrito - Grilled Chicken"
    assert takeaway.search("dominos hawaiian")[0]["name"] == "Hawaiian Pizza"
    assert takeaway.search("subway italian")[0]["name"].startswith("Italian B.M.T.")


def test_a_word_every_chain_has_gives_a_few_from_each_not_all_from_one():
    results = takeaway.search("chicken", 8)
    assert 2 <= len(results) <= 6
    assert len({r["brand"] for r in results}) >= 3


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
    names = [c["name"] for c in takeaway.chains_summary()]
    for name in CHAINS:
        assert name in names

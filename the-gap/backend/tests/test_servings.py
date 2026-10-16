from routers import nutrition
from utils.servings import default_serving, portion_from_measures


def test_everyday_plain_foods_get_a_recognisable_serving():
    assert default_serving("Bananas, raw") == ("1 medium (118 g)", 118.0)
    assert default_serving("Banana") == ("1 medium (118 g)", 118.0)
    assert default_serving("Bread, white") is None  # first part is "bread" with a comma remainder "white": not in the plain list
    assert default_serving("Bread") == ("1 slice (32 g)", 32.0)
    assert default_serving("Milk, whole") == ("1 cup (258 g)", 258.0)


def test_things_made_from_the_food_are_not_mistaken_for_it():
    for name in ("Banana bread", "Apple juice", "Bananas, dehydrated", "Apple, dried", "Egg, fried", "Orange, canned", "Peanut butter bar"):
        assert default_serving(name) is None


def test_an_unknown_food_stays_without_a_default():
    assert default_serving("Quinoa salad") is None and default_serving("") is None


def test_the_databases_own_household_measure_is_used_and_nonsense_is_skipped():
    measures = [
        {"disseminationText": "Quantity not specified", "gramWeight": 100, "rank": 1},
        {"disseminationText": "1 cup", "gramWeight": 244, "rank": 2},
        {"disseminationText": "1 tablespoon", "gramWeight": 15, "rank": 3},
    ]
    assert portion_from_measures(measures) == ("1 cup (244 g)", 244.0)
    assert portion_from_measures([{"disseminationText": "1 pinch", "gramWeight": 0.4}]) is None
    assert portion_from_measures([]) is None and portion_from_measures(None) is None


def test_the_new_style_portion_fields_work_too():
    portions = [{"amount": 1, "modifier": "medium", "gramWeight": 118}]
    assert portion_from_measures(portions) == ("1 medium (118 g)", 118.0)


def usda(description, **extra):
    return {"fdcId": 1, "description": description, "foodNutrients": [
        {"nutrientNumber": "208", "unitName": "KCAL", "value": 89},
        {"nutrientNumber": "203", "value": 1.1}, {"nutrientNumber": "205", "value": 23}, {"nutrientNumber": "204", "value": 0.3},
    ], **extra}


def test_a_generic_food_with_no_serving_now_shows_a_serving_and_scales_the_numbers():
    item = nutrition._usda_to_item(usda("Bananas, raw"))
    assert item is not None
    assert item["serving_label"] == "1 medium (118 g)"
    assert item["serving_grams"] == 118.0
    assert item["per_serving"]["calories"] == round(89 * 1.18, 1)


def test_a_database_measure_beats_the_built_in_list():
    item = nutrition._usda_to_item(usda("Bananas, raw", foodMeasures=[{"disseminationText": "1 small", "gramWeight": 101, "rank": 1}]))
    assert item is not None and item["serving_grams"] == 101.0 and item["serving_label"].startswith("1 small")


def test_a_food_nothing_is_known_about_stays_per_100_g():
    item = nutrition._usda_to_item(usda("Mystery casserole"))
    assert item is not None and item["serving_label"] == "100 g" and item["serving_grams"] == 100.0
    assert item["per_serving"]["calories"] == 89.0


def test_a_branded_item_keeps_its_own_serving():
    item = nutrition._usda_to_item(usda("Granola bar", servingSize=40, servingSizeUnit="g", householdServingFullText="1 bar", brandName="ACME"))
    assert item is not None and item["serving_label"] == "1 bar (40 g)" and item["serving_grams"] == 40.0

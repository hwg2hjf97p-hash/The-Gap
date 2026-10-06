import json
from datetime import date

from routers import suggestions as s


def test_vegan_rules_out_meat_and_dairy_but_not_chickpeas():
    profile = {"diet_prefs": ["vegan"], "allergies": None}
    assert s._violates("Grilled chicken salad", profile)
    assert s._violates("Greek yoghurt bowl", profile)
    assert s._violates("Scrambled eggs on toast", profile)
    assert not s._violates("Chickpea and spinach curry", profile)


def test_vegetarian_allows_eggs_but_not_fish():
    profile = {"diet_prefs": ["vegetarian"], "allergies": None}
    assert s._violates("Salmon fillet", profile)
    assert not s._violates("Veggie omelette with eggs", profile)


def test_gluten_free_rules_out_wheat_products():
    profile = {"diet_prefs": ["gluten_free"], "allergies": None}
    assert s._violates("Whole-wheat pasta", profile)
    assert s._violates("Spaghetti and bread", profile)
    assert not s._violates("Rice bowl with grilled fish", profile)


def test_peanut_allergy_catches_peanut_butter():
    profile = {"diet_prefs": [], "allergies": "peanuts"}
    assert s._violates("Banana on toast with peanut butter", profile)
    assert not s._violates("Banana on toast with almond butter", profile)


def test_tree_nut_allergy_expands_to_common_nuts():
    profile = {"diet_prefs": [], "allergies": "tree nuts"}
    assert s._violates("Almond flour pancakes", profile)
    assert s._violates("Walnut brownie", profile)


def test_allergy_text_with_several_items():
    profile = {"diet_prefs": [], "allergies": "shellfish, eggs and sesame"}
    assert s._violates("Garlic prawn skewers with shellfish stock", profile)
    assert s._violates("Fried egg", profile)
    assert s._violates("Sesame noodles", profile)


def test_no_allergies_means_nothing_blocked():
    assert not s._violates("Peanut butter toast", {"diet_prefs": [], "allergies": None})


def _recipe(title, ingredients):
    return {
        "title": title,
        "summary": "Quick and easy.",
        "time_min": 20,
        "servings": 2,
        "ingredients": ingredients,
        "steps": ["Mix it.", "Cook it."],
        "estimate": {"calories": 450, "protein_g": 30},
    }


def test_clean_payload_drops_recipes_that_break_the_diet():
    raw = json.dumps({
        "foods": [{"name": "Chicken breast", "why": "High in protein."}, {"name": "Lentils", "why": "Plant protein."}],
        "recipes": [
            _recipe("Chicken stir fry", ["200 g chicken breast", "1 cup rice"]),
            _recipe("Lentil dahl", ["1 cup red lentils", "1 onion"]),
        ],
    })
    cleaned = s._clean_food_payload(raw, {"diet_prefs": ["vegan"], "allergies": None})
    assert cleaned is not None
    assert [f["name"] for f in cleaned["foods"]] == ["Lentils"]
    assert [r["title"] for r in cleaned["recipes"]] == ["Lentil dahl"]
    assert cleaned["recipes"][0]["estimate"] == {"calories": 450, "protein_g": 30}


def test_clean_payload_accepts_fenced_json_and_rejects_garbage():
    body = json.dumps({"foods": [{"name": "Oats", "why": "Slow energy."}], "recipes": []})
    assert s._clean_food_payload("```json\n" + body + "\n```", {}) is not None
    assert s._clean_food_payload("not json at all", {}) is None
    assert s._clean_food_payload(json.dumps({"foods": [], "recipes": []}), {}) is None


def test_clean_payload_ignores_malformed_items():
    raw = json.dumps({"foods": ["a string", {"name": "", "why": "x"}, {"name": "Rice", "why": "Energy."}], "recipes": [{"title": "No steps"}]})
    cleaned = s._clean_food_payload(raw, {})
    assert cleaned == {"foods": [{"name": "Rice", "why": "Energy."}], "recipes": []}


def test_week_starts_on_monday():
    assert s._week_start(date(2026, 10, 7)) == date(2026, 10, 5)  # a Wednesday
    assert s._week_start(date(2026, 10, 5)) == date(2026, 10, 5)
    assert s._week_start(date(2026, 10, 11)) == date(2026, 10, 5)  # Sunday


def _by_id():
    return {v["id"]: v for v in s._videos()}


def test_video_list_is_well_formed():
    videos = s._videos()
    assert len(videos) > 50
    ids = [v["id"] for v in videos]
    assert len(ids) == len(set(ids))
    for v in videos:
        assert v["format"] in ("video", "short")
        assert v["kind"] in ("food", "workout")
        assert v["title"] and v["channel"]


def test_vegan_gets_only_vegan_suitable_food_videos():
    by_id = _by_id()
    picked = s.pick_food_videos({"diet_goal": "maintain", "diet_prefs": ["vegan"]}, "user-1", date(2026, 10, 5))
    assert picked
    for v in picked:
        assert "vegan" in by_id[v["id"]]["suits"]


def test_food_videos_match_the_goal_and_are_stable_through_the_week():
    by_id = _by_id()
    profile = {"diet_goal": "lose", "diet_prefs": []}
    first = s.pick_food_videos(profile, "user-1", date(2026, 10, 5))
    again = s.pick_food_videos(profile, "user-1", date(2026, 10, 5))
    assert first == again
    assert len(first) <= 7
    for v in first:
        assert "lose" in by_id[v["id"]]["goals"]


def test_workout_videos_respect_equipment():
    by_id = _by_id()
    profile = {"training_goal": "muscle", "equipment": "bodyweight"}
    picked = s.pick_workout_videos(profile, "user-1", date(2026, 10, 5), set())
    assert picked
    for v in picked:
        assert "bodyweight" in by_id[v["id"]]["equipment"]


def test_workout_videos_put_untrained_groups_first():
    by_id = _by_id()
    profile = {"training_goal": "general", "equipment": "gym"}
    picked = s.pick_workout_videos(profile, "user-1", date(2026, 10, 5), {"Back"})
    long_videos = [v for v in picked if v["format"] == "video"]
    assert "Back" in by_id[long_videos[0]["id"]]["groups"]

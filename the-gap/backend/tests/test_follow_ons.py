import numpy as np
import pandas as pd

from utils import follow_ons as fo
from utils.patterns import build_patterns


def days(n=40, **cols):
    idx = pd.date_range("2026-08-01", periods=n)
    df = pd.DataFrame(index=idx)
    for name, on in cols.items():
        df[name] = 0.0
        for i in on:
            df.iloc[i, df.columns.get_loc(name)] = 1.0
    return df


def test_it_finds_a_behaviour_that_keeps_following_an_event_on_the_same_day():
    df = days(conflict_event=[3, 9, 15, 21, 27], skipped_lunch=[3, 9, 15, 21, 33])
    found = fo.follow_ons(df)
    assert len(found) == 1
    item = found[0]
    assert item["event"] == "conflict_event" and item["behaviour"] == "skipped_lunch"
    assert (item["k_event"], item["n_event"], item["k_other"], item["n_other"]) == (4, 5, 1, 35)
    assert "5 days you logged an argument or conflict, 4 also had no lunch logged" in item["headline"]
    assert "other 35 days it was 1" in item["detail"] and "order isn't known" in item["detail"]


def test_it_stays_quiet_with_too_few_days_of_the_event():
    df = days(conflict_event=[3, 9, 15], skipped_lunch=[3, 9, 15])
    assert fo.follow_ons(df) == []


def test_it_stays_quiet_when_the_behaviour_is_just_common():
    everyday = [i for i in range(40) if i % 5 != 0]  # skipped lunch on 80% of all days
    df = days(conflict_event=[3, 9, 15, 21, 27], skipped_lunch=everyday + [3, 9, 15, 21, 27])
    assert fo.follow_ons(df) == []


def test_it_stays_quiet_when_it_is_only_a_few_days_of_luck():
    df = days(conflict_event=[3, 9, 15, 21, 27], skipped_lunch=[3, 9, 6, 12, 18, 24, 30, 36])
    assert fo.follow_ons(df) == []


def test_a_day_nobody_answered_is_not_counted_as_a_no():
    df = days(conflict_event=[3, 9, 15, 21, 27], skipped_lunch=[3, 9, 15, 21, 33])
    df.loc[df.index[10:30], "skipped_lunch"] = np.nan  # lunch not recorded on those days
    out = fo.follow_ons(df)
    # Only recorded days count, so there are fewer "other" days than 35.
    assert not out or out[0]["n_other"] < 35


def test_the_same_story_is_not_told_twice():
    both = [3, 9, 15, 21, 27]
    df = days(conflict_event=both, argument_flag=both, skipped_lunch=[3, 9, 15, 21, 33])
    assert len(fo.follow_ons(df)) == 1


def test_a_habit_is_never_compared_with_itself():
    df = days(alcohol_flag=[2, 6, 10, 14, 18])
    assert fo.follow_ons(df) == []


def test_meal_skips_look_at_when_food_was_logged():
    entries = pd.DataFrame(
        {
            "local_date": ["2026-10-01", "2026-10-01", "2026-10-02", "2026-10-02", "2026-10-03"],
            "local_hour": [8.5, 18.0, 12.5, None, 7.0],
        }
    )
    out = fo.meal_skips(entries)
    assert out is not None
    assert out.loc["2026-10-01", "skipped_lunch"] == 1 and out.loc["2026-10-01", "skipped_breakfast"] == 0
    assert "2026-10-02" not in out.index  # one entry has no time, so a meal might be missing from the record
    assert out.loc["2026-10-03", "skipped_lunch"] == 1
    assert fo.meal_skips(pd.DataFrame()) is None


def test_the_patterns_reply_carries_the_follow_ons():
    df = days(60, conflict_event=[3, 9, 15, 21, 27], skipped_lunch=[3, 9, 15, 21, 53])
    df["sleep_total_min"] = 420.0
    out = build_patterns(df)
    assert "follow_ons" in out and "follow_ons_caveat" in out
    assert out["follow_ons"] and out["follow_ons"][0]["behaviour"] == "skipped_lunch"

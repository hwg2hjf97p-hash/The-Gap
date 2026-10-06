import numpy as np
import pandas as pd

from causal.hypotheses import HYPOTHESES, PRIVATE_HYPOTHESIS_IDS
from causal.interpreter import interpret_result
from utils.data_cleaning import clean_dataframe

NEW_CHECKIN_IDS = [
    "alcohol_drinks_hrv", "energy_drinks_sleep", "late_energy_drink_deep_sleep", "cigarettes_hrv",
    "cigarettes_rhr", "gambling_sleep", "gambling_hrv", "substance_hrv", "substance_deep_sleep",
    "work_hours_hrv", "work_hours_sleep", "late_work_sleep", "travel_hours_sleep", "travel_hours_hrv",
]


def test_hypothesis_ids_are_unique():
    ids = [h.id for h in HYPOTHESES]
    assert len(ids) == len(set(ids))


def test_hypotheses_are_well_formed():
    for h in HYPOTHESES:
        assert h.treatment_col and h.outcome_col and h.treatment_label and h.outcome_label
        assert h.treatment_scale > 0


def test_private_ids_are_real_hypotheses():
    ids = {h.id for h in HYPOTHESES}
    assert PRIVATE_HYPOTHESIS_IDS <= ids


def test_every_hypothesis_turns_into_an_insight_in_both_directions():
    for h in HYPOTHESES:
        for effect, lo, hi in ((3.2, 1.0, 5.4), (-3.2, -5.4, -1.0)):
            insight = interpret_result(hypothesis=h, effect=effect, ci_low=lo, ci_high=hi, n_obs=60, p_value=0.01)
            assert insight.hypothesis_id == h.id
            assert insight.headline and insight.actionable_tip
            assert insight.is_private == (h.id in PRIVATE_HYPOTHESIS_IDS)


def test_new_checkin_hypotheses_have_their_own_wording():
    by_id = {h.id: h for h in HYPOTHESES}
    for hid in NEW_CHECKIN_IDS:
        h = by_id[hid]
        insight = interpret_result(hypothesis=h, effect=2.0, ci_low=0.5, ci_high=3.5, n_obs=45, p_value=0.02)
        # The generic fallback headline starts with the treatment label.
        assert not insight.headline.startswith(h.treatment_label), hid


def test_a_rare_yes_no_flag_survives_cleaning():
    idx = pd.date_range("2026-08-01", periods=40)
    df = pd.DataFrame({"hrv": np.linspace(50, 70, 40), "sleep_total_min": 420.0, "energy_drink_late_flag": 0.0}, index=idx)
    df.loc[idx[5], "energy_drink_late_flag"] = 1.0
    df.loc[idx[20], "energy_drink_late_flag"] = 1.0
    cleaned = clean_dataframe(df)
    assert cleaned["energy_drink_late_flag"].sum() == 2


def test_next_day_columns_line_up_with_the_calendar():
    idx = pd.date_range("2026-08-01", periods=10)
    df = pd.DataFrame({"hrv": np.arange(50.0, 60.0)}, index=idx)
    cleaned = clean_dataframe(df)
    assert cleaned["hrv_next"].iloc[0] == cleaned["hrv"].iloc[1]
    assert np.isnan(cleaned["hrv_next"].iloc[-1])

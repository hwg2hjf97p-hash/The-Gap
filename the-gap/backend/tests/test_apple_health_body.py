import asyncio

import numpy as np
import pandas as pd

from routers.sources import CAN_SUPPLY
from sync import apple_health_store as store
from utils.snapshot import METRIC_DISPLAY
from utils.source_merge import GROUPS, merge_sources


def test_believable_body_readings_are_kept_and_rounded():
    assert store.clean_body({"weight_kg": 72.46, "body_fat_pct": 18.04}) == {"weight_kg": 72.5, "body_fat_pct": 18.0}


def test_impossible_readings_are_dropped():
    # a weight typed in pounds as kilos, a body fat stored as a fraction, and a stray zero
    assert store.clean_body({"weight_kg": 5.0, "body_fat_pct": 0.18}) == {"weight_kg": None, "body_fat_pct": None}
    assert store.clean_body({"weight_kg": 900, "body_fat_pct": 95}) == {"weight_kg": None, "body_fat_pct": None}
    assert store.clean_body({"weight_kg": 0}) == {"weight_kg": None, "body_fat_pct": None}


def test_missing_or_odd_values_do_not_break_anything():
    assert store.clean_body({}) == {"weight_kg": None, "body_fat_pct": None}
    assert store.clean_body({"weight_kg": "abc", "body_fat_pct": None}) == {"weight_kg": None, "body_fat_pct": None}


def test_apple_health_can_supply_weight_and_body_fat():
    assert "apple_health" in CAN_SUPPLY["body"]
    assert "weight_kg" in GROUPS["body"] and "body_fat_pct" in GROUPS["body"]
    assert METRIC_DISPLAY["body_fat_pct"]["unit"] == "%"


def _days(n=10):
    return pd.date_range("2026-10-01", periods=n, freq="D")


def test_apple_health_weight_and_body_fat_reach_the_merged_table():
    idx = _days()
    apple = pd.DataFrame({"steps": np.full(10, 8000.0), "weight_kg": np.linspace(72.0, 71.0, 10), "body_fat_pct": np.full(10, 18.5)}, index=idx)
    merged = merge_sources({"apple_health": apple}, None)
    assert merged is not None
    assert np.allclose(merged["weight_kg"].values, apple["weight_kg"].values)
    assert np.allclose(merged["body_fat_pct"].values, 18.5)


def test_a_logged_weight_stays_the_main_source_and_body_fat_still_comes_from_apple_health():
    idx = _days()
    manual = pd.DataFrame({"weight_kg": np.full(10, 70.0)}, index=idx)
    apple = pd.DataFrame({"weight_kg": np.full(10, 72.0), "body_fat_pct": np.full(10, 20.0)}, index=idx)
    merged = merge_sources({"manual": manual, "apple_health": apple}, None)
    assert np.allclose(merged["weight_kg"].values, 70.0)   # the weight the person typed leads
    assert np.allclose(merged["body_fat_pct"].values, 20.0)  # nothing typed for body fat, so Apple Health fills it


# ── saving: the rest still saves before the database columns exist ──────────

class _Resp:
    def __init__(self, status):
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")


class _Client:
    def __init__(self, statuses):
        self.statuses, self.posts = list(statuses), []

    async def post(self, url, headers=None, params=None, json=None):
        self.posts.append(json)
        return _Resp(self.statuses.pop(0))


def test_rows_save_with_body_columns_when_they_exist():
    client = _Client([201])
    rows = [{"user_id": "u", "entry_date": "2026-10-01", "steps": 1, "weight_kg": 72.0, "body_fat_pct": 18.0}]
    resp = asyncio.run(store._post_rows(client, rows))
    assert resp.status_code == 201 and "weight_kg" in client.posts[0][0]


def test_rows_save_without_body_columns_when_the_database_does_not_have_them_yet():
    client = _Client([400, 201])
    rows = [{"user_id": "u", "entry_date": "2026-10-01", "steps": 1, "weight_kg": 72.0, "body_fat_pct": 18.0}]
    resp = asyncio.run(store._post_rows(client, rows))
    assert resp.status_code == 201
    assert len(client.posts) == 2
    assert "weight_kg" not in client.posts[1][0] and "body_fat_pct" not in client.posts[1][0]
    assert client.posts[1][0]["steps"] == 1

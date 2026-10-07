"""
Runs the sample data through the real analysis. Needs the full engine, so it is
skipped where econml isn't installed (the quick CI job) and runs in the
"engine" CI job and on any machine with the full requirements.
"""
from datetime import date

import pandas as pd
import pytest

pytest.importorskip("econml")

from causal.engine import run_all_hypotheses  # noqa: E402
from routers import checkin  # noqa: E402
from utils.data_cleaning import clean_dataframe  # noqa: E402
from utils.demo_data import generate_demo_data  # noqa: E402
from utils.snapshot import build_snapshot  # noqa: E402


class _FakeResponse:
    def __init__(self, rows):
        self._rows = rows

    def raise_for_status(self):
        pass

    def json(self):
        return self._rows


def _frame(monkeypatch):
    health, checkins = generate_demo_data(date.today())
    monkeypatch.setattr(checkin.httpx, "get", lambda *a, **k: _FakeResponse(checkins))
    health_df = pd.DataFrame.from_dict(health, orient="index")
    health_df.index = pd.to_datetime(health_df.index)
    checkin_df = checkin.get_checkin_dataframe("demo-user")
    return clean_dataframe(health_df.join(checkin_df, how="outer").sort_index())


def test_the_sample_data_produces_real_looking_insights(monkeypatch):
    insights = run_all_hypotheses(_frame(monkeypatch))
    ids = {i.hypothesis_id for i in insights}
    assert len(insights) >= 4, ids
    assert "alcohol_hrv" in ids
    alcohol = next(i for i in insights if i.hypothesis_id == "alcohol_hrv")
    assert alcohol.ate < 0
    assert any(i.confidence != "weak" for i in insights)


def test_the_sample_data_fills_the_home_screen(monkeypatch):
    snapshot = build_snapshot(_frame(monkeypatch))
    metrics = {c["metric"] for c in snapshot["latest"]}
    assert {"hrv", "sleep_total_min", "steps"} <= metrics

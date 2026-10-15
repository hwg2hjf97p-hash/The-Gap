"""
A lab for the engine: how many real patterns it finds, and how many false ones, under different
settings, on made-up people whose true patterns are known (utils/demo_data.py).

Not part of the app and not run by the normal tests. Run by the "Engine lab" workflow, which prints a
summary as annotations. Each made-up person has 12 weeks of wearable data; their check-ins cover only the
LAST `days_logged` days, like someone who has just started logging. In the "null" version the check-in
answers are shuffled between days, so any check-in pattern found there is false by construction.
"""

from __future__ import annotations

import logging
import os
import random
import sys
import time
from datetime import date

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SUPABASE_URL", "http://supabase.invalid")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "lab")

from causal import engine, interpreter  # noqa: E402
from causal.hypotheses import HYPOTHESES  # noqa: E402
from routers import checkin  # noqa: E402
from utils.data_cleaning import clean_dataframe  # noqa: E402
from utils.demo_data import generate_demo_data  # noqa: E402

logging.disable(logging.CRITICAL)

# What the sample person's life really contains (see utils/demo_data.py).
TRUE_TREATMENTS = {"alcohol_flag", "alcohol_drinks", "afternoon_caffeine", "stress_score", "screen_hours", "late_screen_flag", "steps"}

SETTINGS = {
    "now": dict(rows=1.0, treated=1.0, adaptive=False, fdr=0.10, moderate_n=30),
    "less_data": dict(rows=0.7, treated=0.7, adaptive=True, fdr=0.10, moderate_n=21),
    "less_data_fdr15": dict(rows=0.7, treated=0.7, adaptive=True, fdr=0.15, moderate_n=21),
    "least_data_fdr15": dict(rows=0.55, treated=0.6, adaptive=True, fdr=0.15, moderate_n=18),
}


class _Resp:
    def __init__(self, rows):
        self._rows = rows

    def raise_for_status(self):
        pass

    def json(self):
        return self._rows


def build_frame(seed: int, days_logged: int, shuffled: bool) -> tuple[pd.DataFrame, set[str]]:
    health, checkins = generate_demo_data(date(2026, 10, 14), seed=seed)
    rows = checkins[-days_logged:]
    if shuffled:
        rng = random.Random(seed)
        dates = [r["date"] for r in rows]
        answers = [{k: v for k, v in r.items() if k != "date"} for r in rows]
        rng.shuffle(answers)
        rows = [{"date": d, **a} for d, a in zip(dates, answers)]
    checkin.httpx.get = lambda *a, **k: _Resp(rows)  # type: ignore[assignment]
    checkin_df = checkin.get_checkin_dataframe("lab")
    health_df = pd.DataFrame.from_dict(health, orient="index")
    health_df.index = pd.to_datetime(health_df.index)
    df = clean_dataframe(health_df.join(checkin_df, how="outer").sort_index())
    return df, set(checkin_df.columns)


def apply(name: str) -> None:
    s = SETTINGS[name]
    engine.MIN_ROWS_SCALE = s["rows"]
    engine.MIN_TREATED_SCALE = s["treated"]
    engine.ADAPTIVE_COVARIATES = s["adaptive"]
    engine.FDR_Q = s["fdr"]
    interpreter.MODERATE_MIN_N = s["moderate_n"]


def main() -> None:
    seeds = [int(x) for x in os.environ.get("LAB_SEEDS", "11,12,13").split(",")]
    days_options = [int(x) for x in os.environ.get("LAB_DAYS", "21,35").split(",")]
    by_hyp = {h.id: h for h in HYPOTHESES}
    lines: list[str] = []
    started = time.time()

    for days_logged in days_options:
        for name in SETTINGS:
            apply(name)
            tot = dict(real_confirmed=0, real_true=0, real_weak=0, null_confirmed=0, null_weak=0, runs=0)
            found: dict[str, int] = {}
            for seed in seeds:
                for shuffled in (False, True):
                    df, checkin_cols = build_frame(seed, days_logged, shuffled)
                    insights = engine.run_all_hypotheses(df)
                    confirmed = [i for i in insights if i.confidence != "weak"]
                    weak = [i for i in insights if i.confidence == "weak"]
                    if not shuffled:
                        tot["runs"] += 1
                        tot["real_confirmed"] += len(confirmed)
                        tot["real_weak"] += len(weak)
                        for i in confirmed:
                            if by_hyp[i.hypothesis_id].treatment_col in TRUE_TREATMENTS:
                                tot["real_true"] += 1
                                found[i.hypothesis_id] = found.get(i.hypothesis_id, 0) + 1
                    else:
                        # only answers the person typed are shuffled; wearable-only patterns are still real
                        ck = [i for i in confirmed if by_hyp[i.hypothesis_id].treatment_col in checkin_cols]
                        ckw = [i for i in weak if by_hyp[i.hypothesis_id].treatment_col in checkin_cols]
                        tot["null_confirmed"] += len(ck)
                        tot["null_weak"] += len(ckw)
            n = max(1, tot["runs"])
            line = (
                f"logged={days_logged}d setting={name}: per person real confirmed={tot['real_confirmed']/n:.1f} "
                f"(of which on true patterns {tot['real_true']/n:.1f}), real early={tot['real_weak']/n:.1f}; "
                f"SHUFFLED check-ins (all false) confirmed={tot['null_confirmed']/n:.2f} early={tot['null_weak']/n:.2f}; "
                f"true found: {dict(sorted(found.items()))}"
            )
            print(line, flush=True)
            lines.append(line)
    summary = " || ".join(lines)
    print(f"LAB_DONE seconds={time.time()-started:.0f}")
    print("::notice title=Engine lab::" + summary.replace("%", "%25").replace("\n", "%0A"))
    for i, line in enumerate(lines):
        print(f"::notice title=Engine lab {i+1}::" + line.replace("%", "%25"))


if __name__ == "__main__":
    main()

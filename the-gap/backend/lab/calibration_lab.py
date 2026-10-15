"""
Are the engine's p-values trustworthy on a few weeks of data?

On made-up people whose check-in answers are SHUFFLED between days (so every check-in pattern is false
by construction), a trustworthy p-value is below 0.05 about 5% of the time. Several ways of working out the
p-value are compared, along with how many REAL patterns each still finds on the unshuffled version.
"""

from __future__ import annotations

import logging
import os
import sys
import time

import numpy as np
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SUPABASE_URL", "http://supabase.invalid")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "lab")

from causal import engine  # noqa: E402
from causal.estimator import run_linear_dml  # noqa: E402
from causal.hypotheses import HYPOTHESES  # noqa: E402
from engine_lab import TRUE_TREATMENTS, build_frame  # noqa: E402

logging.disable(logging.CRITICAL)

engine.ADAPTIVE_COVARIATES = True
engine.MIN_ROWS_SCALE = 0.7
engine.MIN_TREATED_SCALE = 0.7


def p_variants(r: dict) -> dict[str, float]:
    n, k = r["n_obs"], r["n_covariates"]
    out = {"raw": r["p_value"]}
    se = r.get("stderr")
    if se and se > 0:
        z = abs(r["effect"]) / se
        df = max(3, n - k - 2)
        out["t"] = float(2 * stats.t.sf(z, df))
        infl = np.sqrt(n / max(3.0, n - k - 2))
        out["t_infl"] = float(2 * stats.t.sf(z / infl, df))
        out["t_infl2"] = float(2 * stats.t.sf(z / (infl * 1.25), df))
    return out


def bh_count(ps: list[float], q: float) -> int:
    ps = sorted(p for p in ps if p == p)
    m, k = len(ps), 0
    for rank, p in enumerate(ps, start=1):
        if p <= rank / m * q:
            k = rank
    return k


def main() -> None:
    n_seeds = int(os.environ.get("LAB_NSEEDS", "24"))
    days_options = [int(x) for x in os.environ.get("LAB_DAYS", "21,28,35").split(",")]
    started = time.time()
    for days in days_options:
        null_p: dict[str, list[float]] = {}
        real_true_p: dict[str, list[float]] = {}
        real_other_p: dict[str, list[float]] = {}
        bh_null: dict[str, list[int]] = {}
        bh_real: dict[str, list[int]] = {}
        for seed in range(100, 100 + n_seeds):
            for shuffled in (True, False):
                df, checkin_cols = build_frame(seed, days, shuffled)
                per_run: dict[str, list[float]] = {}
                for hyp in HYPOTHESES:
                    if hyp.treatment_col not in checkin_cols or hyp.outcome_col not in df.columns:
                        continue
                    missing = [c for c in (hyp.covariate_cols or []) if c not in df.columns]
                    if missing:
                        continue
                    sub, covs = engine.working_frame(df, hyp)
                    if len(sub) < engine.required_rows(hyp):
                        continue
                    if hyp.binary_treatment and sub[hyp.treatment_col].sum() < engine.required_treated(hyp):
                        continue
                    r = run_linear_dml(df=sub, treatment_col=hyp.treatment_col, outcome_col=hyp.outcome_col, covariate_cols=covs, binary_treatment=hyp.binary_treatment)
                    if not r:
                        continue
                    for name, p in p_variants(r).items():
                        per_run.setdefault(name, []).append(p)
                        if shuffled:
                            null_p.setdefault(name, []).append(p)
                        elif hyp.treatment_col in TRUE_TREATMENTS:
                            real_true_p.setdefault(name, []).append(p)
                        else:
                            real_other_p.setdefault(name, []).append(p)
                for name, ps in per_run.items():
                    for q in (0.10,):
                        (bh_null if shuffled else bh_real).setdefault(f"{name}@q{q}", []).append(bh_count(ps, q))
        lines = []
        for name in null_p:
            ps = np.array(null_p[name])
            tp = np.array(real_true_p.get(name, [1.0]))
            lines.append(
                f"{name}: false p<.05 {np.mean(ps < .05)*100:.0f}% p<.10 {np.mean(ps < .10)*100:.0f}% (n={len(ps)}); "
                f"true patterns p<.05 {np.mean(tp < .05)*100:.0f}% p<.10 {np.mean(tp < .10)*100:.0f}% (n={len(tp)})"
            )
        for key in bh_null:
            lines.append(f"BH {key}: false confirmed/person {np.mean(bh_null[key]):.2f}, real confirmed/person {np.mean(bh_real.get(key, [0])):.2f}")
        head = f"logged={days}d seeds={n_seeds}"
        for line in lines:
            print(head, line, flush=True)
            print(f"::notice title=Calibration {days}d::" + line)
    print(f"LAB_DONE seconds={time.time()-started:.0f}")


if __name__ == "__main__":
    main()

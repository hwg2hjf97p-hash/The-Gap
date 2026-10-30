import asyncio
from datetime import datetime, timezone

import pytest

from utils import ai_budget


def _now(y=2026, m=10, d=20):
    return datetime(y, m, d, 12, 0, tzinfo=timezone.utc)


def test_cost_is_tokens_times_price_in_millionths_of_a_dollar():
    # 2,000 in and 300 out on the smarter model: 2000*3 + 300*15 = 10,500 millionths = US$0.0105
    assert ai_budget.cost_micro("claude-sonnet-4-6", {"input_tokens": 2000, "output_tokens": 300}) == 10500
    # the cheap model: 1,000 in and 1,000 out = 1000*1 + 1000*5
    assert ai_budget.cost_micro("claude-haiku-4-5-20251001", {"input_tokens": 1000, "output_tokens": 1000}) == 6000


def test_unknown_model_is_counted_at_the_dearest_rate():
    assert ai_budget.cost_micro("some-new-model", {"input_tokens": 1000, "output_tokens": 0}) == 3000


def test_missing_or_odd_usage_costs_nothing():
    assert ai_budget.cost_micro("claude-sonnet-4-6", None) == 0
    assert ai_budget.cost_micro("claude-sonnet-4-6", {}) == 0
    assert ai_budget.cost_micro("claude-sonnet-4-6", {"input_tokens": None, "output_tokens": None}) == 0


def test_allowance_resets_on_the_first_of_next_month():
    assert ai_budget.month_key(_now()) == "2026-10"
    assert ai_budget.resets_on(_now()) == "2026-11-01"
    assert ai_budget.resets_on(_now(2026, 12, 31)) == "2027-01-01"


def test_default_allowances_and_environment_overrides(monkeypatch):
    for k in ("AI_BUDGET_TRIAL_USD", "AI_BUDGET_PAID_USD"):
        monkeypatch.delenv(k, raising=False)
    assert ai_budget.budget_micro("trial") == 1_000_000
    assert ai_budget.budget_micro("paid") == 2_500_000
    monkeypatch.setenv("AI_BUDGET_PAID_USD", "4")
    assert ai_budget.budget_micro("paid") == 4_000_000
    monkeypatch.setenv("AI_BUDGET_PAID_USD", "nonsense")
    assert ai_budget.budget_micro("paid") == 2_500_000
    monkeypatch.setenv("AI_BUDGET_PAID_USD", "-3")
    assert ai_budget.budget_micro("paid") == 2_500_000


def test_plan_is_worked_out_from_the_subscription_row():
    now = _now()
    future = "2026-12-01T00:00:00+00:00"
    assert ai_budget.tier_from_row(None, now) == "paid"
    assert ai_budget.tier_from_row({"is_active": False}, now) == "paid"
    assert ai_budget.tier_from_row({"is_active": True, "period_type": "TRIAL", "expires_at": future}, now) == "trial"
    assert ai_budget.tier_from_row({"is_active": True, "period_type": "NORMAL", "expires_at": future}, now) == "paid"
    # a trial that has already run out is not a trial
    assert ai_budget.tier_from_row({"is_active": True, "period_type": "TRIAL", "expires_at": "2026-01-01T00:00:00Z"}, now) == "paid"


def test_used_percent_and_exhausted(monkeypatch):
    monkeypatch.delenv("AI_BUDGET_PAID_USD", raising=False)
    s = ai_budget.summarize(0, "paid", _now())
    assert (s["used_pct"], s["exhausted"]) == (0, False)
    s = ai_budget.summarize(1_250_000, "paid", _now())
    assert (s["used_pct"], s["exhausted"]) == (50, False)
    s = ai_budget.summarize(2_499_999, "paid", _now())
    assert (s["used_pct"], s["exhausted"]) == (99, False)
    s = ai_budget.summarize(2_500_000, "paid", _now())
    assert (s["used_pct"], s["exhausted"]) == (100, True)
    s = ai_budget.summarize(9_000_000, "paid", _now())
    assert (s["used_pct"], s["exhausted"]) == (100, True)


def test_the_message_names_the_reset_date_and_says_the_rest_still_works():
    m = ai_budget.blocked_message({"tier": "paid", "resets_on": "2026-11-01"})
    assert "2026-11-01" in m and "rest of The Gap" in m
    t = ai_budget.blocked_message({"tier": "trial", "resets_on": "2026-11-01"})
    assert "free week" in t


def test_enforcement_can_be_switched_off(monkeypatch):
    monkeypatch.delenv("AI_BUDGET_ENFORCE", raising=False)
    assert ai_budget.enforcing() is True
    monkeypatch.setenv("AI_BUDGET_ENFORCE", "false")
    assert ai_budget.enforcing() is False


# ── Metering a request ───────────────────────────────────────────────────────

def _patch_io(monkeypatch, status, recorded):
    async def fake_status(user_id):
        return status

    async def fake_record(user_id, feature, micro, calls):
        recorded.append((user_id, feature, micro, calls))

    monkeypatch.setattr(ai_budget, "status", fake_status)
    monkeypatch.setattr(ai_budget, "_record", fake_record)


def test_usage_inside_a_metered_request_is_recorded_once(monkeypatch):
    recorded = []
    _patch_io(monkeypatch, {"tier": "paid", "used_pct": 10, "exhausted": False, "resets_on": "2026-11-01"}, recorded)

    async def go():
        async with ai_budget.metered("u1", "assistant") as m:
            assert m.blocked is False
            ai_budget.note_usage("claude-sonnet-4-6", {"input_tokens": 2000, "output_tokens": 300})
            ai_budget.note_usage("claude-haiku-4-5-20251001", {"input_tokens": 1000, "output_tokens": 1000})

    asyncio.run(go())
    assert recorded == [("u1", "assistant", 16500, 2)]


def test_usage_outside_a_metered_request_is_ignored(monkeypatch):
    recorded = []
    _patch_io(monkeypatch, {"tier": "paid", "used_pct": 0, "exhausted": False, "resets_on": "x"}, recorded)
    ai_budget.note_usage("claude-sonnet-4-6", {"input_tokens": 5000, "output_tokens": 500})  # background job: no meter
    asyncio.run(asyncio.sleep(0))
    assert recorded == []


def test_a_person_who_has_used_their_allowance_is_blocked_and_nothing_is_recorded(monkeypatch):
    monkeypatch.delenv("AI_BUDGET_ENFORCE", raising=False)
    recorded = []
    _patch_io(monkeypatch, {"tier": "paid", "used_pct": 100, "exhausted": True, "resets_on": "2026-11-01"}, recorded)

    async def go():
        async with ai_budget.metered("u1", "explanation") as m:
            return m.blocked

    assert asyncio.run(go()) is True
    assert recorded == []


def test_switching_enforcement_off_lets_them_through_but_still_counts(monkeypatch):
    monkeypatch.setenv("AI_BUDGET_ENFORCE", "false")
    recorded = []
    _patch_io(monkeypatch, {"tier": "paid", "used_pct": 100, "exhausted": True, "resets_on": "2026-11-01"}, recorded)

    async def go():
        async with ai_budget.metered("u1", "assistant") as m:
            ai_budget.note_usage("claude-sonnet-4-6", {"input_tokens": 100, "output_tokens": 100})
            return m.blocked

    assert asyncio.run(go()) is False
    assert recorded and recorded[0][2] == 1800


def test_if_the_allowance_cannot_be_read_the_person_is_let_through(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    st = asyncio.run(ai_budget.status("u1"))
    assert st["exhausted"] is False


def test_the_meter_does_not_leak_into_the_next_request(monkeypatch):
    recorded = []
    _patch_io(monkeypatch, {"tier": "paid", "used_pct": 0, "exhausted": False, "resets_on": "x"}, recorded)

    async def go():
        async with ai_budget.metered("u1", "assistant"):
            pass
        ai_budget.note_usage("claude-sonnet-4-6", {"input_tokens": 1000, "output_tokens": 1000})  # after: no meter

    asyncio.run(go())
    assert recorded == []

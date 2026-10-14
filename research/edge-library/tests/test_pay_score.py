"""LOCK of the payout pipeline's numbers and its group score (blueprint/pay_rules.py, blueprint/pay_score.py).

1. The three slots are the owner's sessions in the futures day's order; a clock minute falls in one slot or in none.
2. Days are drawn in runs: a run is consecutive days of the pool, the same call gives the same days.
3. A funded account is walked past its first payout: the cycle starts again, a later payout has its own cap, the trader gets his share.
4. An open loss that reaches the floor loses the account that day, whatever the day closes at; an account is walked from where it stands.
5. An intraday floor trails the day's high; an end-of-day floor does not.
6. An account that pays a last payout stops; the group is read on the same paths.
The app's own rule files are read; nothing is run and nothing is written.

  pytest tests/test_pay_score.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W))
from blueprint import pay_rules as PY  # noqa: E402
from blueprint import pay_score as SC  # noqa: E402
from blueprint import propodds as PO  # noqa: E402

PRO, FLEX, APEX50, APEX300 = "lucid-pro-50k-no-dll@2026-10-11", "lucid-flex-50k@2026-10-11", "apex-legacy-50k@2026-10-11b", "apex-legacy-300k@2026-10-11b"


def rules(rid: str) -> dict:
    return PO.app().load_rules(rid)


def days(net, open_=None, up=None) -> tuple:
    """One path: (net, traded, open, up) as (1 x days) arrays."""
    net = np.asarray([net], np.float64)
    z = np.zeros_like(net)
    return net, net != 0, z if open_ is None else np.asarray([open_], np.float64), z if up is None else np.asarray([up], np.float64)


# ================================================================ 1. the slots

def test_the_slots_are_the_owners_three_sessions_in_the_days_order():
    assert [s["id"] for s in PY.slots()] == ["evening", "night", "day"]
    clock = lambda h, m: h * 60 + m  # noqa: E731
    got = {(h, m): PY.slot_of(clock(h, m)) for h, m in ((20, 0), (23, 59), (0, 0), (1, 59), (2, 0), (9, 24), (9, 25), (9, 30), (15, 59), (16, 0), (18, 0))}
    assert got == {(20, 0): "evening", (23, 59): "evening", (0, 0): None, (1, 59): None, (2, 0): "night", (9, 24): "night", (9, 25): None,
                   (9, 30): "day", (15, 59): "day", (16, 0): None, (18, 0): None}


def test_a_rule_files_firm_and_what_follows_a_payout():
    assert PY.firm(PRO) == "lucid" and PY.firm(APEX300) == "apex" and PY.firm_need(PRO)["trader_share"] == 0.9
    assert PY.after(PRO) == {"cap_later": 2500} and PY.after(FLEX) == {"max_count": 5} and PY.after(APEX50)["uncapped_from"] == 6 and PY.after("other-1") == {}


# ================================================================ 2. days in runs

def test_days_are_drawn_in_runs_of_consecutive_days_and_the_same_call_gives_the_same_days():
    idx = SC.blocks(100, 50, 23, 5, 7)
    assert idx.shape == (50, 23) and idx.min() >= 0 and idx.max() < 100
    runs = idx[:, :20].reshape(50, 4, 5)
    assert ((np.diff(runs, axis=2) % 100) == 1).all()                      # inside a run: the next day of the pool (it wraps at the end)
    assert (SC.blocks(100, 50, 23, 5, 7) == idx).all() and not (SC.blocks(100, 50, 23, 5, 8) == idx).all()


# ================================================================ 3. past the first payout

def test_a_lucid_pro_account_is_paid_again_and_again_and_the_trader_gets_his_share():
    got = SC.walk(*days([500.0] * 20), rules(PRO), rule_id=PRO)
    # +$500 a day. The maximum first payout ($2,000) needs $4,100: day 9. It leaves $2,500; the next cycle's maximum ($2,500) needs $4,600: 5 days more.
    assert got["first"][0] == 9 and got["pays"][0] == 3 and got["bust"][0] == 0
    assert got["paid"][0] == pytest.approx(0.9 * (2000 + 2500 + 2500))


def test_asking_as_soon_as_any_payout_can_be_had_pays_earlier_and_smaller():
    got = SC.walk(*days([500.0] * 20), rules(PRO), rule_id=PRO, request="min")
    assert got["first"][0] == 6 and got["paid"][0] > 0                      # $3,000: $900 above the buffer, the largest day 40 % of it or less


def test_the_largest_day_holds_a_payout_back():
    one_big = SC.walk(*days([4500.0] + [0.0] * 19), rules(PRO), rule_id=PRO)
    assert one_big["pays"][0] == 0 and one_big["bust"][0] == 0              # the one day is the whole profit: over 40 % of it


# ================================================================ 4. open losses, and the account as it stands

def test_an_open_loss_at_the_floor_loses_the_account_whatever_the_day_closes_at():
    got = SC.walk(*days([100.0, 100.0], open_=[1999.0, 2100.0]), rules(PRO), rule_id=PRO)
    assert got["bust"][0] == 2                                              # day 1: $1 above the floor. Day 2: +$100 on file, $2,100 under it at worst
    assert SC.walk(*days([-2000.0]), rules(PRO), rule_id=PRO)["bust"][0] == 1


def test_an_account_is_walked_from_where_it_stands_today():
    r, start = rules(APEX50), {"profit": 2949.30, "peak": 2949.30}          # over +$2,600 once: its floor is locked at +$100
    assert SC.walk(*days([0.0], open_=[2800.0]), r, start, APEX50)["bust"][0] == 0
    assert SC.walk(*days([0.0], open_=[2900.0]), r, start, APEX50)["bust"][0] == 1
    assert SC.walk(*days([0.0], open_=[2400.0]), r, None, APEX50)["bust"][0] == 0 and SC.walk(*days([0.0], open_=[2500.0]), r, None, APEX50)["bust"][0] == 1


# ================================================================ 5. the intraday floor

def test_an_intraday_floor_trails_the_days_high_and_an_end_of_day_floor_does_not():
    up_then_flat = days([-50.0], up=[7600.0])                               # +$7,600 at the day's high, closed $50 down
    assert SC.walk(*up_then_flat, rules(APEX300), rule_id=APEX300)["bust"][0] == 1      # the floor locked at +$100 on the way: the close is under it
    assert SC.walk(*up_then_flat, rules(PRO), rule_id=PRO)["bust"][0] == 0


# ================================================================ 6. the last payout, the group

def test_a_lucid_flex_account_leaves_after_its_fifth_payout():
    got = SC.walk(*days([400.0] * 250), rules(FLEX), rule_id=FLEX)
    assert got["pays"][0] == 5 and got["bust"][0] == 0


def test_the_group_is_read_on_the_same_paths():
    rng = np.random.default_rng(1)
    pool = rng.normal(150, 600, 400)
    day = {"net": pool, "traded": np.ones(400, bool), "open": np.maximum(-pool, 0) + 100, "up": np.maximum(pool, 0)}
    idx = SC.blocks(400, 300, 60, 5, 3)
    a, b = SC.account(day, rules(PRO), idx, rule_id=PRO), SC.account(day, rules(PRO), idx, rule_id=PRO)
    g = SC.group([("a", a), ("b", b)], 60, 5)
    assert (a["paid"] == b["paid"]).all()                                   # the same days: the same account twice is the same result twice
    assert g["per_week"] == pytest.approx(2 * g["accounts"][0]["per_week"]) and g["p_paid"] == pytest.approx(g["accounts"][0]["p_paid"])
    assert 0 <= g["survivors"] <= 2 and g["accounts"][0]["p_bust"] == pytest.approx((a["bust"] > 0).mean())

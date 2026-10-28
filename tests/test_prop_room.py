"""Prop room on the chart (read-only): daily loss room, trailing drawdown room and contracts allowed per account.
Display only: an order is never refused for it (the owner: block only on his word)."""
from __future__ import annotations

from homebase.config import AccountCfg
from homebase.desk.risk import prop_room
from tests.test_trading_guards import order
from tests.trading_util import mkdesk

LUCID = {"trailing_mll": 2000, "lock_at": 2100, "lock_floor": 100, "daily_loss_limit": 1200, "cap_micros": 40}


def test_the_floor_trails_the_eod_peak_and_locks_at_start_plus_the_lock_floor():
    r = prop_room(LUCID, 50000, {"2026-09-10": 51000.0, "2026-09-11": 50500.0}, "2026-09-14", 50400.0)
    assert r == {"daily": 1100.0, "drawdown": 1400.0, "contracts": 4}      # peak 51,000 -> floor 49,000
    r = prop_room(LUCID, 50000, {"2026-09-10": 53000.0}, "2026-09-14", 52000.0)
    assert r["drawdown"] == 1900.0                                          # locked: floor 50,100, not 51,000
    # today's own balance line is not an end-of-day peak
    assert prop_room(LUCID, 50000, {"2026-09-14": 55000.0}, "2026-09-14", 50000.0)["drawdown"] == 2000.0


def test_no_daily_limit_and_no_cap_are_none_not_zero():
    r = prop_room({**LUCID, "daily_loss_limit": None, "cap_micros": None}, 50000, {}, "2026-09-14", 50000.0)
    assert r["daily"] is None and r["contracts"] is None


def _prop_desk(tmp_path, balance=50000.0, realized=0.0):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    desk.cfg.accounts["a1"] = AccountCfg(keyring_key="k", account_name="A1", label="A1",
                                         prop={"rules": "lucid-flex-50k-dll@2026-10-11", "start_balance": 50000})
    eng.balance_history = lambda a: {"2026-09-11": 50800.0}
    ads["a1"].view.update(balance=balance, realized_pnl=realized)
    return desk, ads


def test_the_account_view_carries_the_room_and_a_plain_account_carries_none(tmp_path):
    desk, ads = _prop_desk(tmp_path, balance=50300.0, realized=-500.0)
    assert desk.account_view("a1")["room"] == {"daily": 700.0, "drawdown": 1500.0, "contracts": 4}   # peak 50,800 -> floor 48,800
    assert desk.account_view("a2")["room"] is None


def test_daily_room_ignores_a_lifetime_realized_pnl(tmp_path):
    # a paper book's realized_pnl is since the book began: +400 lifetime, all of it made yesterday -> today's P&L is 0
    desk, ads = _prop_desk(tmp_path, balance=50400.0, realized=400.0)
    desk.engine.balance_history = lambda a: {"2026-09-11": 50400.0}
    assert desk.account_view("a1")["room"]["daily"] == 1200.0
    desk.engine.balance_history = lambda a: {}                              # no history: the day started at the start balance
    assert desk.account_view("a1")["room"]["daily"] == 1200.0 + 400.0


def test_a_missing_rule_file_hides_the_room_instead_of_breaking_the_view(tmp_path):
    desk, ads = _prop_desk(tmp_path)
    desk.cfg.accounts["a1"].prop["rules"] = "no-such-rule"
    assert desk.account_view("a1")["room"] is None


def test_an_order_past_every_limit_is_still_sent(tmp_path):
    desk, ads = _prop_desk(tmp_path, balance=48000.0, realized=-1500.0)    # daily limit gone, under the floor
    assert desk.account_view("a1")["room"]["daily"] < 0
    assert order(desk)["a1"]["ok"] is True and len(ads["a1"].orders) == 1

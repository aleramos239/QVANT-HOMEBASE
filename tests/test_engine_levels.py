"""The engine's side of the "levels" strategies: one OCO pair per account with that account's own size and take,
brackets moved to the fill, the day's closed P&L, day_take / day_lock / target_take, the price-watcher backstop.

No broker, no IO outside tmp_path (FakeAdapter from test_engine).  The geometry is a fixed one: buy stop 24510,
sell stop 24490, stop 130 pts from the trigger -- ATR 43.5 x 3."""
from __future__ import annotations

import dataclasses
import json

import pytest

from homebase.broker.base import FillEvent
from homebase.config import AccountCfg, AppCfg, _defaults
from homebase.engine import TAKE_GRACE_S, Engine
from homebase.levels import Geometry
from tests.test_engine import Clock, FakeAdapter, run

GEO = Geometry("atr_straddle", upper=24510.0, lower=24490.0, sl_pts=130.0, atr=43.5, atr_bars=19, anchor=24500.0)
PRO = "lucid-pro-50k-no-dll@2026-09-27b"
FLEX = "lucid-flex-50k@2026-09-27"


class BalAdapter(FakeAdapter):
    def __init__(self, account_id, balance=None):
        super().__init__(account_id)
        self.balance = balance

    async def get_metrics(self):
        return {"connected": True, "account": self.account_id, "balance": self.balance}


def strat(name="nq_nyam_flex", **over):
    return dataclasses.replace(_defaults().strategies[name], **{"enabled": True, **over})


def desk(tmp_path, strategies, accounts, book, balances=None, armed=True, clock=None, history=None, at=(9, 30)):
    """strategies {name: StrategyCfg}; accounts {id: AccountCfg}; book {strategy: [(account, qty)]}."""
    cfg = AppCfg(armed=armed, accounts=accounts, strategies=strategies,
                 book={n: [{"account": a, "qty": q} for a, q in rows] for n, rows in book.items()})
    adapters = {aid: BalAdapter(aid, (balances or {}).get(aid)) for aid in accounts}
    clock = clock or Clock()
    clock.set_et(*at)
    eng = Engine(cfg, adapters, now_fn=clock, root=tmp_path)
    if history is not None:
        eng.balance_history = lambda account: history.get(account, {})
    return eng, adapters, clock


def paper(**prop):
    return AccountCfg(keyring_key="k", account_name="P", paper=True, prop=prop)


def events(tmp_path, name=None):
    p = tmp_path / "journal.jsonl"
    rows = [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []
    return [r for r in rows if name is None or r["event"] == name]


def fill(eng, st, side, px, qty=4, oid=None):
    run(eng.on_fill(FillEvent(account_id=st.account, symbol="NQZ6", side=side, qty=qty, price=px,
                              raw={"orderId": oid if oid is not None else "x"})))


def enter_long(eng, name="nq_nyam_flex", account="a", at=24510.25):
    st = eng._state(name, account)
    fill(eng, st, "Buy", at, oid=st.upper_id)
    return st


# ---------------------------------------------------------------------------------------------- placement
def test_each_account_gets_its_own_size_stop_and_take(tmp_path):
    eng, ads, _ = desk(tmp_path, {"nq_nyam_flex": strat()}, {"a": paper(), "b": paper()},
                       {"nq_nyam_flex": [("a", 4), ("b", 2)]})
    out = run(eng.handle_levels("nq_nyam_flex", GEO))
    assert out["ok"] and out["armed"]
    for aid, qty, tp in (("a", 4, 19.0), ("b", 2, 37.75)):           # $1,500 net: 4 NQ -> 19.00 pts, 2 NQ -> 37.75
        buy, sell = ads[aid].brackets
        assert (buy.side, buy.order_type, buy.price, buy.stop_price, buy.tp_price, buy.qty) == \
            ("Buy", "Stop", 24510.0, 24510.0 - 130.0, 24510.0 + tp, qty)
        assert (sell.side, sell.price, sell.stop_price, sell.tp_price, sell.qty) == \
            ("Sell", 24490.0, 24490.0 + 130.0, 24490.0 - tp, qty)
        st = eng._state("nq_nyam_flex", aid)
        assert (st.status, st.qty, st.sl_pts, st.tp_pts, st.take_usd, st.take_src) == \
            ("placed", qty, 130.0, tp, 1500.0, "day_take")
    placed = events(tmp_path, "levels_placed")[0]
    assert placed["accounts"]["a"]["stop_usd"] == 10400.0            # 130 pts x $80: said at the fire, 5x a $2,000 limit
    assert events(tmp_path, "placed")[0]["sl_pts"] == 130.0


def test_a_real_account_sits_out_until_the_open_loss_is_acknowledged(tmp_path):
    live = AccountCfg(keyring_key="k", account_name="L")
    eng, ads, _ = desk(tmp_path, {"nq_nyam_flex": strat()}, {"a": paper(), "live": live},
                       {"nq_nyam_flex": [("a", 4), ("live", 4)]})
    out = run(eng.handle_levels("nq_nyam_flex", GEO))
    assert out["ok"] and "ack_open_loss" in out["sat_out"]["live"]
    assert ads["live"].brackets == [] and len(ads["a"].brackets) == 2
    eng2, ads2, _ = desk(tmp_path / "ack", {"nq_nyam_flex": strat(ack_open_loss=True)}, {"live": live},
                         {"nq_nyam_flex": [("live", 4)]}) if (tmp_path / "ack").mkdir() is None else (None,) * 3
    assert run(eng2.handle_levels("nq_nyam_flex", GEO))["ok"] and len(ads2["live"].brackets) == 2


def test_pm_size_follows_the_accounts_eod_profit(tmp_path):
    prop = dict(start_balance=50000, rules=FLEX, mode="funded")
    eng, ads, _ = desk(tmp_path, {"nq_pm_flex": strat("nq_pm_flex")},
                       {"lo": paper(**prop), "mid": paper(**prop), "hi": paper(**prop), "none": paper()},
                       {"nq_pm_flex": [("lo", 4), ("mid", 4), ("hi", 4), ("none", 4)]},
                       balances={"lo": 50400.0, "mid": 51200.0, "hi": 52500.0}, at=(13, 30))
    out = run(eng.handle_levels("nq_pm_flex", GEO))
    assert out["ok"]
    got = {aid: (ads[aid].brackets[0].qty, ads[aid].brackets[0].tp_price - 24510.0) for aid in ads}
    assert got == {"lo": (2, 15.25), "mid": (3, 10.25), "hi": (4, 7.75),
                   "none": (2, 15.25)}                                 # no standing: the smallest size


def test_pro_target_take_is_the_remaining_distance_to_the_target(tmp_path):
    eng, ads, _ = desk(tmp_path, {"nq_nyam_pro": strat("nq_nyam_pro")},
                       {"day1": paper(start_balance=50000, rules=PRO), "day3": paper(start_balance=50000, rules=PRO)},
                       {"nq_nyam_pro": [("day1", 4), ("day3", 4)]}, balances={"day1": 50000.0, "day3": 51800.0})
    out = run(eng.handle_levels("nq_nyam_pro", GEO))
    assert out["ok"]
    assert ads["day1"].brackets[0].tp_price - 24510.0 == 37.75         # $3,000 + $16 fee over $80
    assert ads["day3"].brackets[0].tp_price - 24510.0 == 15.25         # $1,200 left
    assert eng._state("nq_nyam_pro", "day3").take_src == "target_take"
    assert events(tmp_path, "account_prepared")[1]["target_level"] == 1200.0


def test_pro_without_a_level_sits_out_rather_than_run_to_the_fallback_target(tmp_path):
    """No standing (no balance / no rules): a target_take-only strategy has no take -- never a 6 ATR target."""
    eng, ads, _ = desk(tmp_path, {"nq_nyam_pro": strat("nq_nyam_pro")}, {"a": paper()},
                       {"nq_nyam_pro": [("a", 4)]})
    out = run(eng.handle_levels("nq_nyam_pro", GEO))
    assert not out["ok"] and "sat out" in out["reason"] and ads["a"].brackets == []
    assert "target_take has no level" in out["sat_out"]["a"]


def test_flex_cannot_pass_on_day_one_so_only_day_take_applies(tmp_path):
    eng, ads, _ = desk(tmp_path, {"nq_nyam_flex": strat()}, {"a": paper(start_balance=50000, rules=FLEX)},
                       {"nq_nyam_flex": [("a", 4)]}, balances={"a": 50000.0})
    assert run(eng.handle_levels("nq_nyam_flex", GEO))["ok"]
    st = eng._state("nq_nyam_flex", "a")
    assert (st.take_src, st.tp_pts) == ("day_take", 19.0) and eng.book("a").target_level is None


def test_flex_target_level_comes_from_the_balance_record(tmp_path):
    hist = {"a": {"2026-09-10": 50000.0, "2026-09-11": 51200.0, "2026-09-12": 52000.0}}
    eng, ads, _ = desk(tmp_path, {"nq_nyam_flex": strat()}, {"a": paper(start_balance=50000, rules=FLEX)},
                       {"nq_nyam_flex": [("a", 4)]}, balances={"a": 52000.0}, history=hist)
    assert run(eng.handle_levels("nq_nyam_flex", GEO))["ok"]
    b = eng.book("a")
    assert (b.morning_profit, b.largest_day, b.days, b.target_level) == (2000.0, 1200.0, 2, 1000.0)
    st = eng._state("nq_nyam_flex", "a")
    assert (st.take_src, st.take_usd, st.tp_pts) == ("target_take", 1000.0, 12.75)    # lower than day_take 1,500


def test_a_restart_mid_day_reads_the_morning_profit_from_the_record_not_todays_balance(tmp_path):
    hist = {"a": {"2026-09-11": 50000.0, "2026-09-13": 51000.0}}
    eng, ads, _ = desk(tmp_path, {"nq_pm_flex": strat("nq_pm_flex")},
                       {"a": paper(start_balance=50000, rules=FLEX, mode="funded")},
                       {"nq_pm_flex": [("a", 4)]}, balances={"a": 53000.0}, history=hist, at=(13, 30))
    st = eng._state("nq_pm_flex", "a")
    st.status = "done"                                        # it already traded today: the balance includes that
    assert run(eng.prepare_account("a")).morning_profit == 1000.0


def test_disarmed_and_shadow_only_journal(tmp_path):
    eng, ads, _ = desk(tmp_path, {"nq_nyam_flex": strat()}, {"a": paper()}, {"nq_nyam_flex": [("a", 4)]}, armed=False)
    out = run(eng.handle_levels("nq_nyam_flex", GEO))
    assert out["ok"] and out["armed"] is False and ads["a"].brackets == []
    ev, = events(tmp_path, "dry_run")
    assert (ev["qty"], ev["tp_pts"], ev["take_usd"], ev["upper"], ev["sl_pts"]) == (4, 19.0, 1500.0, 24510.0, 130.0)
    eng2, ads2, _ = desk(tmp_path / "s", {"nq_nyam_flex": strat(shadow=True)}, {"a": paper()},
                         {"nq_nyam_flex": [("a", 4)]}) if (tmp_path / "s").mkdir() is None else (None,) * 3
    assert run(eng2.handle_levels("nq_nyam_flex", GEO))["note"].startswith("shadow") and ads2["a"].brackets == []


def test_levels_refusals(tmp_path):
    eng, ads, clock = desk(tmp_path, {"nq_nyam_flex": strat(), "nq_orb_pro": strat("nq_orb_pro", enabled=False),
                                      "nq930": dataclasses.replace(_defaults().strategies["nq930"], enabled=True)},
                           {"a": paper()}, {"nq_nyam_flex": [("a", 4)], "nq930": [("a", 1)]})
    assert "unknown" in run(eng.handle_levels("nope", GEO))["reason"]
    assert "unknown" in run(eng.handle_levels("nq_orb_pro", GEO))["reason"]               # disabled
    assert "not a levels" in run(eng.handle_levels("nq930", GEO))["reason"]
    clock.set_et(9, 45)
    assert "window" in run(eng.handle_levels("nq_nyam_flex", GEO))["reason"]
    clock.set_et(9, 30)
    bad = Geometry("atr_straddle", 24490.0, 24510.0, 130.0, 43.5, 19)
    assert "geometry" in run(eng.handle_levels("nq_nyam_flex", bad))["reason"]
    run(eng.kill_strategy("nq_nyam_flex"))
    assert "killed" in run(eng.handle_levels("nq_nyam_flex", GEO))["reason"]
    assert ads["a"].brackets == []


def test_one_levels_fire_a_day(tmp_path):
    eng, ads, _ = desk(tmp_path, {"nq_nyam_flex": strat()}, {"a": paper()}, {"nq_nyam_flex": [("a", 4)]})
    assert run(eng.handle_levels("nq_nyam_flex", GEO))["ok"]
    assert "already" in run(eng.handle_levels("nq_nyam_flex", GEO))["reason"]
    assert len(ads["a"].brackets) == 2


def test_a_manually_skipped_account_is_not_placed(tmp_path):
    eng, ads, _ = desk(tmp_path, {"nq_nyam_flex": strat()}, {"a": paper(), "b": paper()},
                       {"nq_nyam_flex": [("a", 4), ("b", 4)]})
    eng.skip_today("nq_nyam_flex", "b")
    assert run(eng.handle_levels("nq_nyam_flex", GEO))["ok"]
    assert ads["b"].brackets == [] and len(ads["a"].brackets) == 2


# ------------------------------------------------------------------------------------------- the fill / exit
def test_the_fill_moves_stop_and_take_to_the_fill_by_the_accounts_own_points(tmp_path):
    eng, ads, _ = desk(tmp_path, {"nq_nyam_flex": strat()}, {"a": paper()}, {"nq_nyam_flex": [("a", 4)]})
    run(eng.handle_levels("nq_nyam_flex", GEO))
    st = enter_long(eng, at=24510.25)                       # a tick of slip
    assert st.status == "live" and st.take_px == 24510.25 + 19.0
    mods = {m[1]: m[2] for m in ads["a"].modified}
    assert mods == {"Stop": 24510.25 - 130.0, "Limit": 24510.25 + 19.0}


def test_a_short_fill_takes_below_the_fill(tmp_path):
    eng, ads, _ = desk(tmp_path, {"nq_nyam_flex": strat()}, {"a": paper()}, {"nq_nyam_flex": [("a", 4)]})
    run(eng.handle_levels("nq_nyam_flex", GEO))
    st = eng._state("nq_nyam_flex", "a")
    fill(eng, st, "Sell", 24489.75, oid=st.lower_id)
    assert st.take_px == 24489.75 - 19.0
    assert {m[1]: m[2] for m in ads["a"].modified} == {"Stop": 24489.75 + 130.0, "Limit": 24489.75 - 19.0}


def test_an_exit_at_the_take_is_graded_and_books_the_day_and_locks_it(tmp_path):
    eng, ads, _ = desk(tmp_path, {"nq_nyam_flex": strat()}, {"a": paper()}, {"nq_nyam_flex": [("a", 4)]})
    run(eng.handle_levels("nq_nyam_flex", GEO))
    st = enter_long(eng)
    fill(eng, st, "Sell", 24510.25 + 19.0)
    assert (st.status, st.exit_reason, st.pnl) == ("done", "tp", 1520.0)
    b = eng.book("a")
    assert b.closed_net == 1504.0 and b.locked == "day_take" and eng.account_locked("a") == "day_take"
    assert events(tmp_path, "day_booked")[0]["net"] == 1504.0
    assert events(tmp_path, "day_rule_lock")[0]["reason"] == "day_take"


def test_a_stop_exit_is_graded_sl_and_does_not_lock(tmp_path):
    eng, ads, _ = desk(tmp_path, {"nq_nyam_flex": strat()}, {"a": paper()}, {"nq_nyam_flex": [("a", 4)]})
    run(eng.handle_levels("nq_nyam_flex", GEO))
    st = enter_long(eng)
    fill(eng, st, "Sell", 24510.25 - 130.0 - 0.25)
    assert st.exit_reason == "sl" and st.pnl < 0
    b = eng.book("a")
    assert b.closed_net == round(st.pnl - 16, 2) and b.locked is None


def test_the_books_survive_a_restart(tmp_path):
    clock = Clock()
    eng, ads, _ = desk(tmp_path, {"nq_nyam_flex": strat()}, {"a": paper()}, {"nq_nyam_flex": [("a", 4)]}, clock=clock)
    run(eng.handle_levels("nq_nyam_flex", GEO))
    fill(eng, enter_long(eng), "Sell", 24510.25 + 19.0)
    again = Engine(eng.cfg, ads, now_fn=clock, root=tmp_path)
    assert again.account_locked("a") == "day_take" and again.book("a").closed_net == 1504.0
    # and another day starts clean
    clock.dt = clock.dt.replace(day=15)
    assert again.account_locked("a") is None and again.book("a").closed_net == 0.0


# --------------------------------------------------------------------------- an account stopped for the day
def two_strategies(tmp_path, **levels_over):
    return desk(tmp_path, {"nq_nyam_flex": strat(**levels_over),
                           "nq930": dataclasses.replace(_defaults().strategies["nq930"], enabled=True, gated=False)},
                {"a": paper()}, {"nq_nyam_flex": [("a", 4)], "nq930": [("a", 1)]})


def test_a_locked_account_places_nothing_new_on_any_path(tmp_path):
    eng, ads, _ = two_strategies(tmp_path)
    run(eng.handle_levels("nq_nyam_flex", GEO))
    fill(eng, enter_long(eng), "Sell", 24510.25 + 19.0)                           # day_take: locked
    n = len(ads["a"].brackets)
    out = run(eng.handle_alert({"strategy": "nq930", "upper": 24510.0, "lower": 24490.0}))
    assert not out["ok"] and ads["a"].brackets[n:] == []
    assert any(r["reason"].startswith("locked") for r in events(tmp_path, "place_skipped"))


def test_day_lock_stops_the_day_after_a_close_and_cancels_resting_entries(tmp_path):
    eng, ads, _ = two_strategies(tmp_path, day_take=0.0, day_lock=750.0, target_take=False)
    run(eng.handle_alert({"strategy": "nq930", "upper": 24510.0, "lower": 24490.0}))   # resting on the account
    run(eng.handle_levels("nq_nyam_flex", GEO))
    other = eng._state("nq930", "a")
    assert other.status == "placed"
    fill(eng, enter_long(eng), "Sell", 24510.25 + 19.0)                                # +1,504 net: past 750
    assert eng.account_locked("a") == "day_lock"
    assert other.status == "done" and other.exit_reason == "day_lock"
    assert other.upper_id in ads["a"].cancelled and other.lower_id in ads["a"].cancelled


def test_day_lock_ignores_a_close_below_it_and_open_pnl(tmp_path):
    eng, ads, _ = two_strategies(tmp_path, day_take=0.0, day_lock=2000.0, target_take=False)
    run(eng.handle_levels("nq_nyam_flex", GEO))
    st = enter_long(eng)
    assert eng.account_locked("a") is None                                              # open: never counted
    fill(eng, st, "Sell", 24510.25 + 19.0)
    assert eng.book("a").closed_net == 1504.0 and eng.account_locked("a") is None


# ----------------------------------------------------------------------------- the day_take price backstop
class Mono:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def live_long(tmp_path, **kw):
    eng, ads, _ = desk(tmp_path, {"nq_nyam_flex": strat()}, {"a": paper()}, {"nq_nyam_flex": [("a", 4)]}, **kw)
    mono = eng._mono = Mono()
    run(eng.handle_levels("nq_nyam_flex", GEO))
    st = enter_long(eng)
    return eng, ads["a"], st, mono


TAKE = 24510.25 + 19.0           # the limit's price; $1,520 gross, $1,504 net


def check(eng, px):
    return run(eng.check_takes({"NQ": px}))


def test_below_the_take_nothing_happens(tmp_path):
    eng, ad, st, mono = live_long(tmp_path)
    ad.net = 4
    assert check(eng, TAKE - 0.25) == [] and ad.orders == [] and st.status == "live"


def test_a_touch_waits_for_the_limit_then_market_flattens_and_stops_the_day(tmp_path):
    eng, ad, st, mono = live_long(tmp_path)
    ad.net = 4
    assert check(eng, TAKE) == [] and ad.orders == []                  # touched: the resting limit gets its chance
    mono.t += TAKE_GRACE_S - 0.1
    assert check(eng, TAKE) == [] and ad.orders == []
    mono.t += 0.2
    out = check(eng, TAKE + 0.25)
    assert [o.order_type for o in ad.orders] == ["Market"] and (ad.orders[0].side, ad.orders[0].qty) == ("Sell", 4)
    assert out[0]["account"] == "a"
    assert (st.status, st.exit_reason, st.exit_fill) == ("done", "day_take", TAKE + 0.25)
    b = eng.book("a")
    assert b.locked == "day_take" and b.closed_net == pytest.approx((TAKE + 0.25 - 24510.25) * 80 - 16)
    assert st.upper_id in ad.cancelled and st.up_tp_id in ad.cancelled      # entries and brackets are gone
    assert events(tmp_path, "day_take_flatten")
    assert check(eng, TAKE + 5) == []                                        # and it never fires twice


def test_the_take_cancels_the_accounts_other_resting_entries_and_sells_once(tmp_path):
    eng, ads, _ = two_strategies(tmp_path)
    mono = eng._mono = Mono()
    run(eng.handle_alert({"strategy": "nq930", "upper": 24510.0, "lower": 24490.0}))      # resting on the account
    run(eng.handle_levels("nq_nyam_flex", GEO))
    st, other = enter_long(eng), eng._state("nq930", "a")
    assert other.status == "placed"
    ads["a"].net = 4
    check(eng, TAKE)
    mono.t += 5
    check(eng, TAKE)
    assert [o.order_type for o in ads["a"].orders] == ["Market"]                          # one market-out, not two
    assert other.status == "done" and other.exit_reason == "day_take"
    assert other.upper_id in ads["a"].cancelled and other.lower_id in ads["a"].cancelled
    assert st.status == "done" and eng.account_locked("a") == "day_take"


def test_a_limit_that_fills_during_the_grace_is_never_sold_twice(tmp_path):
    eng, ad, st, mono = live_long(tmp_path)
    ad.net = 4
    check(eng, TAKE)
    fill(eng, st, "Sell", TAKE)                                             # the limit filled: the exit fill is in
    ad.net = 0
    mono.t += 5
    assert check(eng, TAKE) == [] and ad.orders == []
    assert eng.account_locked("a") == "day_take" and eng.book("a").closed_net == 1504.0


def test_a_position_the_broker_shows_flat_is_not_sold(tmp_path):
    """The limit filled but its fill push was lost: _flatten_state reads the position first."""
    eng, ad, st, mono = live_long(tmp_path)
    ad.net = 0
    check(eng, TAKE)
    mono.t += 5
    check(eng, TAKE)
    assert ad.orders == []


def test_a_price_that_falls_back_resets_the_grace(tmp_path):
    eng, ad, st, mono = live_long(tmp_path)
    ad.net = 4
    check(eng, TAKE)
    mono.t += 1.5
    check(eng, TAKE - 1)                                                    # back under: the clock stops
    mono.t += 1.5
    assert check(eng, TAKE) == [] and ad.orders == []                       # a NEW touch: the grace starts over


def test_no_price_means_no_decision(tmp_path):
    eng, ad, st, mono = live_long(tmp_path)
    ad.net = 4
    check(eng, TAKE)
    mono.t += 10
    assert run(eng.check_takes({})) == [] and ad.orders == []


def test_open_pnl_adds_to_what_the_day_already_closed(tmp_path):
    eng, ad, st, mono = live_long(tmp_path)
    ad.net = 4
    eng.book("a").closed_net = 400.0                                        # an earlier trade closed +400 net
    px = 24510.25 + (1500 - 400 + 16) / 80                                  # 13.95: the open trade needs only $1,100 more
    check(eng, px)
    mono.t += 5
    assert len(check(eng, px)) == 1 and ad.orders[0].order_type == "Market"


def test_the_backstop_uses_the_lower_of_day_take_and_target_take(tmp_path):
    eng, ads, _ = desk(tmp_path, {"nq_nyam_flex": strat()}, {"a": paper(start_balance=50000, rules=PRO)},
                       {"nq_nyam_flex": [("a", 4)]}, balances={"a": 51800.0})
    mono = eng._mono = Mono()
    run(eng.handle_levels("nq_nyam_flex", GEO))                              # Pro level today: $1,200 net
    st = enter_long(eng)
    ads["a"].net = 4
    px = 24510.25 + (1200 + 16) / 80
    check(eng, px)
    mono.t += 5
    assert len(check(eng, px)) == 1


def test_accounts_without_rules_are_not_watched(tmp_path):
    eng, ads, _ = desk(tmp_path, {"nq930": dataclasses.replace(_defaults().strategies["nq930"], enabled=True)},
                       {"a": paper()}, {"nq930": [("a", 3)]})
    run(eng.handle_alert({"strategy": "nq930", "upper": 24510.0, "lower": 24490.0}))
    st = eng._state("nq930", "a")
    fill(eng, st, "Buy", 24510.25, qty=3, oid=st.upper_id)
    ads["a"].net = 3
    mono = eng._mono = Mono()
    run(eng.check_takes({"NQ": 99999.0}))
    mono.t += 10
    assert run(eng.check_takes({"NQ": 99999.0})) == [] and ads["a"].orders == []

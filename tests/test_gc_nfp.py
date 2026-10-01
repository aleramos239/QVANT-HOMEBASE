"""gc_nfp: the GC 08:30 NFP straddle on the desk (verified 2026-10-01, research/nfp-2026-10-02).

Pins the spec the user will put real Lucid evals on: it fires ONLY on its event day, at 08:30:00.000 ET,
OCO stops at anchor +/- 2.0, SL 3.7 / TP 7.7 from the fill, unfilled cancelled 08:45, flat 09:55 --
and that the 09:30 strategies' schedule did not move when the timer learned per-strategy fire times.
"""
from __future__ import annotations

import datetime as dt
from array import array
from dataclasses import replace

import pytest

from homebase import config as desk_config
from homebase.backtest.engine import Costs, run_session
from homebase.backtest.tape import Tape, et_ns
from homebase.broker.base import FillEvent
from homebase.broker.tradovate import renewal_due
from homebase.config import AccountCfg, AppCfg
from homebase.contracts import point_value
from homebase.engine import Engine
from homebase.server import compute_readiness
from homebase.strategies import REGISTRY
from homebase.strategies.gc_nfp import GCNfp
from homebase.timer import (DONE_T, FIRE_T, GATE_T, STAGE_T, SelfTimer, fire_clock, fire_time,
                            schedule)
from tests.test_engine import Clock, FakeAdapter, run
from tests.test_timer import ET, FakeMD, at as _at, events

NFP_DAY = (2026, 10, 2)          # Friday, the BLS release day
THU, NEXT_FRI = (2026, 10, 1), (2026, 10, 9)
ANCHOR = 3950.0


def at(clock, h, m, s=0, us=0, date=NFP_DAY):
    """The clock to an ET wall time on NFP day (tests.test_timer.at defaults to a Monday in September)."""
    _at(clock, h, m, s, us, date=date)


@pytest.fixture(autouse=True)
def desk_file(monkeypatch, tmp_path):
    """The tester reads the desk config from a temp path (absent = the frozen defaults)."""
    p = tmp_path / "config.json"
    monkeypatch.setattr(desk_config, "config_path", lambda: p)
    return p


def gc_cfg(**over):
    return replace(desk_config._defaults().strategies["gc_nfp"], enabled=True, **over)


def mk(tmp_path, *, armed=True, qty=4, date=NFP_DAY, cfg=None, accounts=("evalA", "evalB")):
    clock = Clock()
    at(clock, 8, 0, date=date)
    cfgs = AppCfg(armed=armed, webhook_secret="s",
                  accounts={a: AccountCfg(keyring_key=a, account_name=a.upper()) for a in accounts},
                  book={"gc_nfp": [{"account": a, "qty": qty} for a in accounts]},
                  strategies={"gc_nfp": cfg or gc_cfg()})
    adapters = {a: FakeAdapter(a) for a in accounts}
    engine = Engine(cfgs, adapters, now_fn=clock, root=tmp_path)
    md = FakeMD(last_trade=ANCHOR, clock=clock)
    return SelfTimer(cfgs, engine, md_factory=lambda: md, now_fn=clock), engine, md, clock, adapters


def drive(timer, clock, date=NFP_DAY, through=(8, 30, 0)):
    for step in ((8, 21), (8, 29), through):
        at(clock, *step, date=date)
        run(timer.tick())


# --------------------------------------------------------------------------- the spec, in the config
def test_the_desk_config_is_the_verified_spec_and_ships_off_and_unbooked():
    c = desk_config._defaults().strategies["gc_nfp"]
    assert (c.symbol, c.qty, c.offset_pts, c.sl_pts, c.tp_pts) == ("GC", 4, 2.0, 3.7, 7.7)
    assert (c.fire_et, c.cancel_et, c.flat_et) == ("08:30:00", "08:45", "09:55")
    assert c.only_dates == ["2026-10-02"]
    assert c.kind == "straddle" and c.self_fire and not c.gated and not c.shadow
    assert c.enabled is False                       # the user books the evals and switches it on
    assert (c.accept_from_et, c.accept_until_et) == ("08:29", "08:31")   # a fire a minute late is refused
    assert desk_config._defaults().book == {}


def test_the_risk_is_inside_the_2000_dollar_limit_with_room_for_slippage_and_fees():
    c = desk_config._defaults().strategies["gc_nfp"]
    pv = point_value("GC")
    stop_loss = c.sl_pts * pv * c.qty               # $1,480 at 4 contracts, before slippage
    target = c.tp_pts * pv * c.qty                  # $3,080 gross
    fees = 2 * 2.30 * c.qty                         # Lucid's listed GC fee, $18.40 round turn at 4 ct
    assert round(stop_loss, 2) == 1480.0 and round(target, 2) == 3080.0
    assert round(target - fees, 2) == 3061.60       # clears the $3,000 target after fees
    # the stop may slip ~11 ticks a contract (4 ct x $10 x 11 = $440) before the $2,000 limit is touched
    assert 2000 - (stop_loss + fees) > 400


# --------------------------------------------------------------------------- the schedule
def test_the_default_schedule_is_the_original_0930_one():
    assert schedule(desk_config.StrategyCfg(symbol="NQ", qty=1, offset_pts=1, sl_pts=1, tp_pts=1)) \
        == (GATE_T, STAGE_T, FIRE_T, DONE_T) \
        == (dt.time(9, 20), dt.time(9, 28, 30), dt.time(9, 30), dt.time(9, 31))


def test_the_gc_schedule_hangs_off_0830():
    assert schedule(gc_cfg()) == (dt.time(8, 20), dt.time(8, 28, 30), dt.time(8, 30), dt.time(8, 31))
    assert fire_time(gc_cfg(fire_et="08:30")) == dt.time(8, 30)
    assert fire_clock(0, dt.time(8, 30)) == "8:30:00" and fire_clock(4.2, dt.time(8, 30)) == "8:30:04"
    assert fire_clock(4) == "9:30:04"               # unchanged for the 09:30 strategies


# --------------------------------------------------------------------------- it fires only on NFP day
def test_it_fires_at_0830_on_nfp_day_and_not_a_second_before(tmp_path):
    timer, engine, md, clock, ads = mk(tmp_path, armed=False)
    drive(timer, clock, through=(8, 29, 59))
    assert timer.status()["strategies"]["gc_nfp"]["stage"] == "staged"
    assert md.subs == ["GC"] and not any(e["event"] == "timer_fired" for e in events(tmp_path))
    at(clock, 8, 30, 0)
    run(timer.tick())
    st = timer.status()["strategies"]["gc_nfp"]
    assert st["stage"] == "fired" and st["anchor"] == ANCHOR and st["gate"] is True
    fired = [e for e in events(tmp_path) if e["event"] == "timer_fired"]
    assert len(fired) == 1 and fired[0]["late"] is False and fired[0]["anchor_source"] == "pre_open"
    for e in events(tmp_path):
        if e["event"] == "dry_run":
            assert (e["upper"], e["lower"]) == (3952.0, 3948.0)


@pytest.mark.parametrize("day", [THU, NEXT_FRI])
def test_it_does_nothing_on_any_other_day(tmp_path, day):
    timer, engine, md, clock, ads = mk(tmp_path, date=day)
    drive(timer, clock, date=day)
    at(clock, 9, 30, date=day)
    run(timer.tick())
    assert timer.status()["strategies"] == {}                # no state, no feed, no orders
    assert md.subs == [] and events(tmp_path) == []
    assert all(a.brackets == [] for a in ads.values())
    out = run(engine.handle_alert({"strategy": "gc_nfp", "upper": 3952.0, "lower": 3948.0}))
    assert out["ok"] is False and "does not trade today" in out["reason"]
    assert [e["reason"] for e in events(tmp_path) if e["event"] == "alert_refused"] == ["not_a_trading_day"]


def test_an_empty_only_dates_still_means_every_weekday():
    c = desk_config._defaults().strategies["nq930"]
    assert c.only_dates == [] and c.trades_on(dt.date(2026, 10, 1)) and c.trades_on("2026-10-02")
    assert gc_cfg().trades_on(dt.date(2026, 10, 2)) and not gc_cfg().trades_on(dt.date(2026, 10, 1))


def test_a_late_fire_is_refused_not_re_anchored_after_the_release(tmp_path):
    """Desk up at 08:32 (or the quote dead until then): the move has happened -- no stops go out."""
    timer, engine, md, clock, ads = mk(tmp_path)
    at(clock, 8, 32, date=NFP_DAY)
    run(timer.tick())
    assert timer.status()["strategies"]["gc_nfp"]["stage"] == "missed"
    assert all(a.brackets == [] for a in ads.values()) and md.subs == []


# --------------------------------------------------------------------------- what goes to the broker
def test_armed_it_places_the_oco_stops_and_brackets_as_specified_on_every_booked_eval(tmp_path):
    timer, engine, md, clock, ads = mk(tmp_path)
    drive(timer, clock)
    for a in ("evalA", "evalB"):
        buy, sell = ads[a].brackets
        assert (buy.symbol, buy.side, buy.order_type, buy.qty) == ("GC", "Buy", "Stop", 4)
        assert (sell.symbol, sell.side, sell.order_type, sell.qty) == ("GC", "Sell", "Stop", 4)
        assert buy.price == pytest.approx(3952.0) and sell.price == pytest.approx(3948.0)
        assert buy.stop_price == pytest.approx(3948.3) and buy.tp_price == pytest.approx(3959.7)
        assert sell.stop_price == pytest.approx(3951.7) and sell.tp_price == pytest.approx(3940.3)
        assert engine._state("gc_nfp", a).status == "placed"
    # both evals get the IDENTICAL straddle in the same instant (no long-vs-short hedge across accounts)
    assert [(r.side, r.price, r.stop_price, r.tp_price, r.qty) for r in ads["evalA"].brackets] \
        == [(r.side, r.price, r.stop_price, r.tp_price, r.qty) for r in ads["evalB"].brackets]


def test_the_contract_count_is_the_books_per_account_qty(tmp_path):
    timer, engine, md, clock, ads = mk(tmp_path, qty=2)
    drive(timer, clock)
    assert [r.qty for r in ads["evalA"].brackets] == [2, 2]


def test_the_fill_moves_both_brackets_to_the_fill_at_3_7_and_7_7(tmp_path):
    timer, engine, md, clock, ads = mk(tmp_path, accounts=("evalA",))
    drive(timer, clock)
    ad, st = ads["evalA"], engine._state("gc_nfp", "evalA")
    at(clock, 8, 30, 1)
    run(engine.on_fill(FillEvent(account_id="evalA", symbol="GCZ6", side="Buy", qty=4, price=3952.3,
                                 raw={"orderId": st.upper_id})))
    assert st.status == "live" and st.entry_side == "Buy" and st.lower_id in ad.cancelled
    moved = {oid: px for oid, _, px in ad.modified}
    assert set(moved) == {f"{st.upper_id}-sl", f"{st.upper_id}-tp"}
    assert moved[f"{st.upper_id}-sl"] == pytest.approx(3948.6)      # 3952.3 - 3.7
    assert moved[f"{st.upper_id}-tp"] == pytest.approx(3960.0)      # 3952.3 + 7.7


def test_unfilled_entries_are_cancelled_at_0845(tmp_path):
    timer, engine, md, clock, ads = mk(tmp_path, accounts=("evalA",))
    drive(timer, clock)
    ad, st = ads["evalA"], engine._state("gc_nfp", "evalA")
    at(clock, 8, 44, 59)
    run(engine.clock_tick())
    assert st.status == "placed" and ad.cancelled == []
    at(clock, 8, 45, 1)
    run(engine.clock_tick())
    assert st.status == "done" and st.exit_reason == "no_fill"
    assert {st.upper_id, st.lower_id} <= set(ad.cancelled)


def test_an_open_position_is_flattened_at_0955(tmp_path):
    timer, engine, md, clock, ads = mk(tmp_path, accounts=("evalA",))
    drive(timer, clock)
    ad, st = ads["evalA"], engine._state("gc_nfp", "evalA")
    run(engine.on_fill(FillEvent(account_id="evalA", symbol="GCZ6", side="Sell", qty=4, price=3947.9,
                                 raw={"orderId": st.lower_id})))
    ad.net = -4
    at(clock, 9, 54, 59)
    run(engine.clock_tick())
    assert st.status == "live"
    at(clock, 9, 55, 1)
    run(engine.clock_tick())
    assert st.status == "done" and st.exit_reason == "flat"
    flat = [o for o in ad.orders if o.order_type == "Market"]
    assert len(flat) == 1 and flat[0].side == "Buy" and flat[0].qty == 4


# --------------------------------------------------------------------------- the 09:30 strategies are untouched
def test_the_0930_strategy_is_not_touched_by_the_0830_clock(tmp_path):
    from tests.test_timer import mk as mk_nq
    timer, engine, md, clock = mk_nq(tmp_path)
    for h, m in ((8, 21), (8, 29), (8, 30), (8, 45)):
        clock.set_et(h, m)
        run(timer.tick())
        assert timer.status()["strategies"]["nq930"]["stage"] == "idle"
    assert md.subs == [] and events(tmp_path) == []


# --------------------------------------------------------------------------- the tester twin
def _tape(d, rows):
    ts, px = array("q"), array("d")
    for t, p in rows:
        hms, _, ms = t.partition(".")
        ts.append(et_ns(d, hms) + int(ms or 0) * 1_000_000)
        px.append(p)
    return Tape("GC", d, "X", ts, px, array("i", [1] * len(ts)), {})


def test_the_twin_is_registered_and_reads_the_desk_config():
    s = GCNfp()
    assert REGISTRY["gc_nfp"] is GCNfp
    assert (s.p["offset_pts"], s.p["sl_pts"], s.p["tp_pts"]) == (2.0, 3.7, 7.7)
    assert s.times() == ["08:30:00", "08:45", "09:55"]
    assert s.session_window == ("08:20", "09:56") and s.provenance()["fire"] == "08:30:00"


def test_the_twin_trades_nfp_days_only_and_tomorrow():
    s = GCNfp()
    assert s.trades_on(dt.date(2026, 10, 2)) and s.trades_on(dt.date(2024, 12, 6))   # tomorrow; a past NFP
    assert not s.trades_on(dt.date(2026, 10, 1))
    assert not s.trades_on(dt.date(2024, 1, 11))                                     # CPI day


def test_the_twin_trades_exactly_the_desk_geometry():
    d = dt.date(2024, 12, 6)
    tp = _tape(d, [("08:29:59", 2650.0), ("08:30:00.100", 2652.3), ("08:31", 2661.0)])
    t, = run_session(GCNfp(), tp, Costs()).trades
    assert t.side == "long" and t.entry_price == pytest.approx(2652.4)   # first print through 2652.0, +1 tick
    assert t.sl == pytest.approx(2648.7) and t.tp == pytest.approx(2660.1)   # 3.7 / 7.7 from the FILL
    assert t.exit_reason == "tp" and t.net == round(7.7 * 100 - 4.0, 2)


# --------------------------------------------------------------------------- operations around the fire
def test_no_token_renewal_drop_around_the_0830_fire():
    def at_et(h, m, s=0):
        return dt.datetime(*NFP_DAY, h, m, s, tzinfo=ET)

    def exp(h, m):
        return dt.datetime(*NFP_DAY, h, m, tzinfo=ET).timestamp()

    # a token that would come due inside 08:25-08:50 is renewed early instead (08:10-08:25) ...
    assert renewal_due(at_et(8, 12), exp(8, 50)) == (True, "early")
    assert renewal_due(at_et(8, 12), exp(9, 30)) == (False, "normal")        # one that is not due is left alone
    # ... and nothing is dropped from 08:25 to 08:50, however close to expiry -- unless it dies before 08:51
    assert renewal_due(at_et(8, 29, 59), exp(8, 55)) == (False, "quiet")
    assert renewal_due(at_et(8, 30, 1), exp(8, 36)) == (True, "expires_in_window")
    assert renewal_due(at_et(8, 30, 1), 0.0) == (False, "quiet")             # an unknown expiry is never renewed here
    # outside those windows the old rule is unchanged
    assert renewal_due(at_et(7, 0), exp(7, 5)) == (True, "normal")
    assert renewal_due(at_et(8, 51), exp(9, 20)) == (False, "normal")
    assert renewal_due(at_et(9, 25), exp(9, 45)) == (False, "quiet")      # the 09:30 rule, as before


def test_readiness_is_silent_on_other_days_and_flags_an_ungated_gc_nfp_on_nfp_day(tmp_path):
    timer, engine, md, clock, ads = mk(tmp_path)
    acct = {a: {"connected": True} for a in ads}

    def checks(day, h, m):
        out = compute_readiness(dt.datetime(*day, h, m, tzinfo=ET), timer.cfg, engine, acct,
                                timer_status=timer.status(), power=None)
        return [c for c in out["checks"] if c["label"] == "gc_nfp"]

    assert checks(THU, 9, 0) == [] and checks(NEXT_FRI, 12, 0) == []   # no "no signal arrived" alarm
    at(clock, 8, 25, date=NFP_DAY)
    assert [(c["level"], c["detail"]) for c in checks(NFP_DAY, 8, 25)] \
        == [("bad", "timer has not gated — the 8:30 fire is not armed")]
    run(timer.tick())                                                  # 08:25: past the gate time
    assert checks(NFP_DAY, 8, 25) == []

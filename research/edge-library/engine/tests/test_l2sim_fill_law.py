"""The fill law on synthetic tapes (no market data read)."""
import datetime as dt

import numpy as np
import pytest

import l2sim as S

D = dt.date(2024, 3, 5)                       # an ordinary in-sample weekday (EST)
T0 = S.et_ns(D, "09:30")


def tape(prints, d=D):
    """prints: [(seconds after 09:30 ET, price[, size])]"""
    ts = [T0 + int(round(p[0] * 1e9)) for p in prints]
    return S.Tape("NQ", d, "NQH4", ts, [p[1] for p in prints], [p[2] if len(p) > 2 else 1 for p in prints])


class Script(S.Strategy):
    """Calls self.fn(ctx, kind, arg) on every event."""
    session_window = ("09:30", "10:00")
    bar_minutes = 1

    def __init__(self, fn, times=(), placement_ms=85, bar_minutes=1):
        super().__init__({})
        self.fn, self._times, self.placement_ms, self.bar_minutes = fn, list(times), placement_ms, bar_minutes

    def times(self):
        return self._times

    def on_session(self, ctx):
        self.fn(ctx, "session", None)

    def on_bar(self, ctx, bar):
        self.fn(ctx, "bar", bar)

    def on_time(self, ctx, t):
        self.fn(ctx, "time", t)


def run(prints, fn, **kw):
    return S.run_session(Script(fn, **kw), tape(prints)).trades


def at_session(action):
    def fn(ctx, kind, arg):
        if kind == "session":
            action(ctx)
    return fn


def test_market_fills_first_print_after_placement_latency_plus_one_tick():
    # 85 ms latency: the print at +0.05 s is too early, the one at +0.085 s is the fill
    pr = [(0.05, 100.0), (0.085, 101.0), (5, 102.0), (60 * 29.99, 103.0)]
    tr = run(pr, at_session(lambda c: c.market("long")))
    assert len(tr) == 1
    t = tr[0]
    assert t["entry_price"] == 101.25 and t["entry_ms"] == (T0 + 85_000_000) // 1_000_000
    assert t["exit_reason"] == "eod" and t["exit_price"] == 103.0 - 0.25      # flat at the last print, -1 tick
    assert t["gross"] == (102.75 - 101.25) * 20 and t["commission"] == 4.0 and t["net"] == t["gross"] - 4.0
    tr = run(pr, at_session(lambda c: c.market("short")))
    assert tr[0]["entry_price"] == 100.75 and tr[0]["exit_price"] == 103.25


def test_stop_entry_fills_at_trigger_plus_slip_and_pays_the_gap():
    pr = [(1, 100.0), (2, 100.75), (3, 101.0), (4, 101.5), (1700, 101.5)]
    t = run(pr, at_session(lambda c: c.stop_entry("long", 101.0)))[0]
    assert t["entry_price"] == 101.25 and t["order_price"] == 101.0          # touch -> trigger + 1 tick
    pr = [(1, 100.0), (2, 103.0), (1700, 103.0)]                               # gaps through 101
    t = run(pr, at_session(lambda c: c.stop_entry("long", 101.0)))[0]
    assert t["entry_price"] == 103.25
    pr = [(1, 100.0), (2, 97.0), (1700, 97.0)]
    t = run(pr, at_session(lambda c: c.stop_entry("short", 99.0)))[0]
    assert t["entry_price"] == 96.75


def test_limit_entry_needs_one_tick_trade_through_and_fills_at_the_limit():
    touch = [(1, 100.0), (2, 99.0), (3, 99.0), (1700, 100.0)]
    assert run(touch, at_session(lambda c: c.limit_entry("long", 99.0))) == []      # touched, never through
    thru = [(1, 100.0), (2, 99.0), (3, 98.75), (1700, 100.0)]
    t = run(thru, at_session(lambda c: c.limit_entry("long", 99.0)))[0]
    assert t["entry_price"] == 99.0 and t["entry_ms"] == (T0 + 3 * S.NS) // 1_000_000
    thru = [(1, 100.0), (2, 101.0), (3, 101.25), (1700, 100.0)]
    assert run(thru[:2] + thru[3:], at_session(lambda c: c.limit_entry("short", 101.0))) == []
    t = run(thru, at_session(lambda c: c.limit_entry("short", 101.0)))[0]
    assert t["entry_price"] == 101.0


def test_stop_loss_slips_one_tick_and_target_needs_trade_through():
    pr = [(1, 100.0), (2, 100.0), (3, 98.0), (1700, 98.0)]                      # entry on print 1 (market)
    t = run(pr, at_session(lambda c: c.market("long", sl=98.0, tp=104.0)))[0]
    assert t["entry_price"] == 100.25 and t["exit_reason"] == "sl" and t["exit_price"] == 97.75
    pr = [(1, 100.0), (2, 104.0), (3, 104.0), (1700, 103.0)]                    # touches 104, never through
    t = run(pr, at_session(lambda c: c.market("long", sl=98.0, tp=104.0)))[0]
    assert t["exit_reason"] == "eod"
    pr = [(1, 100.0), (2, 104.0), (3, 104.25), (1700, 103.0)]
    t = run(pr, at_session(lambda c: c.market("long", sl=98.0, tp=104.0)))[0]
    assert t["exit_reason"] == "tp" and t["exit_price"] == 104.0               # at the limit, no slip
    pr = [(1, 100.0), (2, 96.0), (1700, 96.0)]                                  # gap through the stop: pays the gap
    t = run(pr, at_session(lambda c: c.market("long", sl=98.0)))[0]
    assert t["exit_price"] == 95.75


def test_brackets_cannot_trigger_on_the_entry_print_itself():
    # the entry print (100 -> fill 100.25) is already below the stop 100.5: the SL waits for the NEXT print
    pr = [(1, 100.0), (2, 100.0), (1700, 100.0)]
    t = run(pr, at_session(lambda c: c.market("long", sl=100.5)))[0]
    assert t["exit_ms"] == (T0 + 2 * S.NS) // 1_000_000 and t["exit_reason"] == "sl"


def test_one_print_hitting_stop_and_target_resolves_to_the_stop():
    # two overlapping positions bracketed so that ONE print (90) is through long's SL and short's TP; and a
    # single position whose SL and TP both trigger on the same print must exit "sl"
    def act(c):
        c.market("short", sl=95.0, tp=105.0)       # short: SL (buy stop) at 95 is ABOVE..: print 110 >= 95 -> sl;
    pr = [(1, 100.0), (2, 110.0), (1700, 110.0)]   # ...and the TP (buy limit 105) needs a print <= 104.75: not hit
    t = run(pr, at_session(act))[0]
    assert t["exit_reason"] == "sl"

    def both(c):
        c.market("long", sl=101.0, tp=99.0)        # inverted bracket: a print at 98.75.. triggers neither side's
    pr = [(1, 100.0), (2, 100.5), (1700, 100.5)]   # TP (sell limit 99 needs >= 99.25: 100.5 hits) and SL (sell stop
    t = run(pr, at_session(both))[0]               # 101: 100.5 <= 101 hits) on the SAME print -> SL wins
    assert t["exit_reason"] == "sl" and t["exit_price"] == 100.25


def test_oco_cancels_the_other_leg_and_cancel_flatten_work():
    seen = {}

    def act(c):
        a = c.stop_entry("long", 101.0, sl=99.0)
        b = c.stop_entry("short", 99.0, sl=101.0)
        c.oco(a, b)
        seen["a"], seen["b"] = a, b
    pr = [(1, 100.0), (2, 101.0), (3, 98.0), (1700, 98.0)]
    tr = run(pr, at_session(act))
    assert len(tr) == 1 and tr[0]["side"] == "long" and tr[0]["exit_reason"] == "sl"
    assert seen["a"].status == "filled" and seen["b"].status == "cancelled"

    def cancel_then(c, kind, arg):                 # cancelled before it can fill
        if kind == "session":
            seen["o"] = c.stop_entry("long", 101.0)
        elif kind == "time":
            c.cancel(seen["o"])
    pr = [(1, 100.0), (70, 101.0), (1700, 101.0)]
    assert run(pr, cancel_then, times=["09:31:00"]) == []

    def flat(c, kind, arg):
        if kind == "session":
            c.market("long")
        elif kind == "time":
            c.flatten("time")
    pr = [(1, 100.0), (59, 105.0), (61, 106.0), (1700, 101.0)]
    t = run(pr, flat, times=["09:31:00"])[0]       # flatten: first print AT/AFTER 09:31:00, -1 tick, no latency
    assert t["exit_reason"] == "time" and t["exit_price"] == 105.75 and t["exit_ms"] == (T0 + 61 * S.NS) // 1_000_000


def test_move_brackets_to_fill_and_tp_rr():
    def act(c):
        c.move_brackets_to_fill = True
        c.market("long", sl=98.0, tp=104.0, ref=100.0)     # fill 100.75 (+0.75 vs ref): brackets shift by 0.75
    pr = [(1, 100.5), (2, 100.5), (1700, 100.5)]
    t = run(pr, at_session(act))[0]
    assert (t["sl"], t["tp"]) == (98.75, 104.75)

    def rr(c):
        c.market("long", sl=98.0, tp_rr=2.0)               # tp = fill + 2 x |fill - sl|
    t = run(pr, at_session(rr))[0]
    assert t["tp"] == 100.75 + 2 * 2.75


def test_mae_mfe_measured_from_the_entry_print_against_the_fill():
    pr = [(1, 100.0), (2, 99.0), (3, 103.0), (4, 101.0), (1700, 101.0)]
    t = run(pr, at_session(lambda c: c.market("long")))[0]
    assert t["entry_price"] == 100.25
    assert t["mae_pts"] == 1.25 and t["mfe_pts"] == 2.75
    assert t["mae_usd"] == 25.0 and t["mfe_usd"] == 55.0
    # a stop entry's MAE includes at least its own slippage (segment starts at the entry print)
    pr = [(1, 100.0), (2, 101.0), (3, 102.0), (1700, 102.0)]
    t = run(pr, at_session(lambda c: c.stop_entry("long", 101.0)))[0]
    assert t["mae_pts"] == 0.25 and t["mfe_pts"] == 0.75


def test_events_run_before_the_first_print_at_their_time_and_bar_sees_only_its_minute():
    log = []

    def fn(ctx, kind, arg):
        if kind == "bar":
            log.append((arg.start_ns - T0, arg.o, arg.h, arg.l, arg.c, arg.v, ctx.last_price, ctx.now_ns - T0))
    pr = [(0, 100.0, 2), (30, 101.0, 3), (59.999, 99.0, 1), (60, 105.0, 7), (200, 104.0, 1), (1700, 104.0, 1)]
    run(pr, fn)
    # bar 09:30 closes at 09:31:00.000 and does NOT contain the print stamped exactly 09:31:00
    assert log[0] == (0, 100.0, 101.0, 99.0, 99.0, 6, 99.0, 60 * S.NS)
    assert log[1][0] == 60 * S.NS and log[1][1:6] == (105.0, 105.0, 105.0, 105.0, 7)
    assert log[2][0] == 180 * S.NS                 # the empty minute 09:32 makes no bar
    assert len(log) == 4                           # 09:30, 09:31, 09:33, 09:58 (the 09:59 close == session end never fires)


def test_prices_snap_to_the_tick_grid():
    pr = [(1, 100.0), (2, 101.25), (1700, 101.0)]
    t = run(pr, at_session(lambda c: c.stop_entry("long", 101.13, sl=99.9)))[0]
    assert t["order_price"] == 101.25 and t["sl"] == 100.0 and t["entry_price"] == 101.5


def test_trade_schema_matches_the_tester_bundle_plus_ns():
    pr = [(1, 100.0), (2, 100.0), (1700, 101.0)]
    t = run(pr, at_session(lambda c: c.market("long")))[0]
    need = {"date", "side", "qty", "entry_price", "exit_price", "exit_reason", "order_price", "sl", "tp", "gross",
            "commission", "net", "mae_pts", "mfe_pts", "mae_usd", "mfe_usd", "bars", "seconds", "entry_ms", "exit_ms"}
    assert need <= set(t) and set(t) - need == {"entry_ns", "exit_ns", "oco", "both_sides"}
    assert t["date"] == "2024-03-05" and t["qty"] == 1 and t["bars"] == 29 and t["seconds"] == 1699.0


def test_features_enforce_the_timestamp_law():
    # row stamped minute 09:30 is usable at 09:31:00, row 09:31 at 09:32:00
    f = S.Features([T0 + 60 * S.NS, T0 + 120 * S.NS, T0 + 180 * S.NS], {"x": [1.0, 2.0, 3.0]})
    seen = []

    def fn(ctx, kind, arg):
        if kind == "bar":
            seen.append((ctx.now_ns - T0, ctx.feat("x"), ctx.feat("x", back=1), ctx.feat_window("x").tolist()))
        elif kind == "session":
            seen.append(("s", ctx.feat("x"), ctx.feat_n()))
    pr = [(1, 100.0), (61, 100.0), (121, 100.0), (1700, 100.0)]
    S.run_session(Script(fn), tape(pr), features=f)
    assert seen[0] == ("s", None, 0)                               # nothing usable at 09:30:00
    assert seen[1] == (60 * S.NS, 1.0, None, [1.0])                # decision at END of minute 09:30 sees row 09:30 only
    assert seen[2] == (120 * S.NS, 2.0, 1.0, [1.0, 2.0])
    with pytest.raises(ValueError):
        S.Features([2, 1], {"x": [1, 2]})
    with pytest.raises(ValueError):
        S.Features([1, 2], {"x": [1]})


def test_first_at_or_above_below_are_tick_tolerant_and_chunked():
    px = np.full(3 * S.CHUNK + 5, 100.0)
    px[2 * S.CHUNK + 3] = 64.01 + 0.01                               # 64.02000000000001
    assert S.first_at_or_below(px, 64.02, 0, len(px), 0.01 * 1e-6) == 2 * S.CHUNK + 3
    assert S.first_at_or_below(px, 64.0, 0, len(px), 0.01 * 1e-6) == len(px)
    px = np.full(3 * S.CHUNK + 5, 1.0)
    px[-1] = 64.02                                                   # a hair BELOW the level 64.02000000000001
    assert S.first_at_or_above(px, 64.01 + 0.01, 0, len(px), 0.01 * 1e-6) == len(px) - 1
    assert S.first_at_or_above(px, 64.01 + 0.01, 5, 5, 0.01 * 1e-6) == 5
    assert S.first_at_or_above(px, 65.0, 0, len(px), 0.01 * 1e-6) == len(px)

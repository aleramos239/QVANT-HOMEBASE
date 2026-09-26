"""The tick engine's fill law, case by case, on synthetic tapes (no archive)."""
from __future__ import annotations

import datetime as dt
from array import array

from homebase.backtest.engine import Costs, build_bars, run_session, to_tick
from homebase.backtest.tape import Tape, et_ns
from homebase.strategies.base import Strategy

D = dt.date(2024, 3, 5)                      # a Tuesday
TICK = 0.25                                  # NQ; $20/pt


def tape(rows, root="NQ") -> Tape:
    """rows: [("HH:MM:SS.mmm", price), ...] in tape order."""
    ts, px = array("q"), array("d")
    for t, p in rows:
        hms, _, ms = t.partition(".")
        ts.append(et_ns(D, hms) + int(ms or 0) * 1_000_000)
        px.append(p)
    return Tape(root, D, "NQH4", ts, px, array("i", [1] * len(ts)), {})


class Script(Strategy):
    """A test strategy: {et_time: fn(ctx, self)} run by on_time."""
    id, root = "script", "NQ"
    session_window = ("09:25", "16:00")

    def __init__(self, plan, bars=0, move=True):
        super().__init__({})
        self.plan, self.bar_minutes, self.move, self.o = plan, bars, move, {}
        self.seen = []

    def times(self):
        return list(self.plan)

    def on_time(self, ctx, t):
        ctx.move_brackets_to_fill = self.move
        self.plan[t](ctx, self)

    def on_bar(self, ctx, bar):
        self.seen.append(bar)


def straddle(off=10.0, sl=5.0, tp=15.0):
    def fire(ctx, s):
        a = ctx.last_price
        s.o["buy"] = ctx.stop_entry("long", a + off, sl=a + off - sl, tp=a + off + tp)
        s.o["sell"] = ctx.stop_entry("short", a - off, sl=a - off + sl, tp=a - off - tp)
        ctx.oco(s.o["buy"], s.o["sell"])
    return fire


def cancel(ctx, s):
    for o in s.o.values():
        ctx.cancel(o)


def flat(ctx, s):
    ctx.flatten("time")


PLAN = lambda **kw: {"09:30:00": straddle(**kw), "12:55": cancel, "15:55": flat}  # noqa: E731


def one(rows, plan=None, slip=1.0, comm=4.0, **kw):
    res = run_session(Script(plan or PLAN(), **kw), tape(rows), Costs(comm, slip), qty=1)
    return res.trades


def test_gap_through_stop_entry_pays_the_gap_plus_slip():
    t, = one([("09:29:59", 100.0), ("09:30:01", 112.0), ("09:31", 140.0)])
    assert t.side == "long" and t.order_price == 110.0
    assert t.entry_price == 112.25                       # max(110, 112) + 1 tick
    assert (t.sl, t.tp) == (107.25, 127.25)              # brackets moved to the fill
    assert t.exit_reason == "tp" and t.exit_price == 127.25


def test_target_needs_one_tick_penetration():
    rows = [("09:29:59", 100.0), ("09:30:01", 110.0), ("09:31", 125.25), ("09:32", 125.25)]
    t, = one(rows + [("15:56", 120.0)])
    assert t.entry_price == 110.25 and t.tp == 125.25
    assert t.exit_reason == "time"                       # touched, never penetrated
    t, = one(rows + [("09:33", 125.5)])
    assert t.exit_reason == "tp" and t.exit_price == 125.25   # fills AT the limit, no slip


def test_stop_loss_is_touch_and_pays_slip_and_gap():
    t, = one([("09:29:59", 100.0), ("09:30:01", 110.0), ("09:31", 105.25)])
    assert (t.entry_price, t.sl) == (110.25, 105.25)
    assert t.exit_reason == "sl" and t.exit_price == 105.0          # min(105.25, 105.25) - 1 tick
    t, = one([("09:29:59", 100.0), ("09:30:01", 110.0), ("09:31", 104.0)])
    assert t.exit_price == 103.75                                    # the gap is paid too
    assert t.gross == round((103.75 - 110.25) * 20, 2) and t.net == t.gross - 4.0


def test_same_ts_prints_resolve_in_row_order():
    base = [("09:29:59", 100.0), ("09:30:01", 110.0)]
    t, = one(base + [("09:31", 125.5), ("09:31", 105.0)])
    assert t.exit_reason == "tp"
    t, = one(base + [("09:31", 105.0), ("09:31", 125.5)])
    assert t.exit_reason == "sl"


def test_oco_first_fill_cancels_the_other_leg():
    trades = one([("09:29:59", 100.0), ("09:30:01", 110.0), ("09:31", 125.5),
                  ("09:40", 85.0), ("09:41", 60.0)])
    assert [t.side for t in trades] == ["long"]


def test_orders_go_live_after_the_placement_latency():
    t, = one([("09:29:59", 100.0), ("09:30:00.050", 111.0), ("09:30:00.085", 110.5),
              ("09:31", 130.0)])
    assert t.entry_ns == et_ns(D, "09:30:00") + 85_000_000 and t.entry_price == 110.75


def test_anchor_is_the_last_print_strictly_before_the_fire():
    t, = one([("09:29:59", 100.0), ("09:30:00", 90.0), ("09:30:01", 110.0), ("09:31", 130.0)])
    assert t.order_price == 110.0                      # anchored at 100, not the 09:30:00 print


def test_unfilled_entries_are_cancelled_at_the_first_print_at_or_after_cancel_time():
    assert one([("09:29:59", 100.0), ("12:54:59", 105.0), ("12:55:00", 120.0)]) == []


def test_flat_fills_on_the_first_print_at_or_after_the_flat_time():
    t, = one([("09:29:59", 100.0), ("09:30:01", 110.0), ("15:54:59", 112.0),
              ("15:55:00.200", 113.0), ("15:56", 90.0)])
    assert t.exit_reason == "time" and t.exit_price == 112.75        # 113 - 1 tick
    assert t.exit_ns == et_ns(D, "15:55:00") + 200_000_000


def test_position_open_when_the_tape_ends_exits_eod_on_the_last_print():
    t, = one([("09:29:59", 100.0), ("09:30:01", 110.0), ("15:50", 112.0)])
    assert t.exit_reason == "eod" and t.exit_price == 111.75


def test_no_move_keeps_brackets_at_the_trigger():
    t, = one([("09:29:59", 100.0), ("09:30:01", 112.0), ("09:31", 125.5)], move=False)
    assert (t.sl, t.tp) == (105.0, 125.0) and t.exit_reason == "tp" and t.exit_price == 125.0


def test_slippage_zero_and_commission_inputs():
    t, = one([("09:29:59", 100.0), ("09:30:01", 110.0), ("09:31", 104.0)], slip=0, comm=2.5)
    assert (t.entry_price, t.exit_price) == (110.0, 104.0)
    assert t.net == round((104.0 - 110.0) * 20 - 2.5, 2)


def test_mae_mfe_bars_and_seconds():
    t, = one([("09:29:59", 100.0), ("09:30:01", 110.0), ("09:31:30", 108.0), ("09:32", 120.0),
              ("09:33", 125.5)])
    assert (t.mae_pts, t.mfe_pts) == (2.25, 15.25)
    assert (t.mae_usd, t.mfe_usd) == (45.0, 305.0)
    assert t.bars == 4 and t.seconds == 179.0


def test_market_entry_with_rr_target_rederived_from_the_fill():
    def go(ctx, s):
        ctx.market("short", sl=110.0, tp=95.0, tp_rr=0.75, ref=100.0)
    t, = one([("09:59:59", 100.0), ("10:00:00.100", 101.0), ("10:05", 93.5)],
             plan={"10:00": go, "15:55": flat})
    assert t.entry_price == 100.75                     # first print after 85 ms, minus 1 tick
    assert t.sl == 110.0 and t.tp == to_tick(100.75 - 0.75 * (110.0 - 100.75), TICK) == 93.75
    assert t.exit_reason == "tp" and t.exit_price == 93.75


def test_limit_entry_needs_penetration():
    def go(ctx, s):
        ctx.limit_entry("long", 99.0, sl=97.0, tp=103.0)
    assert one([("09:59:59", 100.0), ("10:01", 99.0), ("10:02", 99.0)],
               plan={"10:00": go, "15:55": flat}) == []
    t, = one([("09:59:59", 100.0), ("10:01", 98.75), ("10:02", 103.25)],
             plan={"10:00": go, "15:55": flat})
    assert t.entry_price == 99.0 and t.exit_reason == "tp"


def test_two_orders_triggered_by_one_print_both_fill_oldest_first():
    def go(ctx, s):
        ctx.stop_entry("long", 101.0, sl=90.0, tp=200.0)
        ctx.stop_entry("long", 102.0, sl=90.0, tp=200.0)
    trades = one([("09:59:59", 100.0), ("10:01", 103.0), ("10:30", 50.0)],
                 plan={"10:00": go, "15:55": flat}, move=False)
    assert [t.order_price for t in trades] == [101.0, 102.0]
    assert all(t.exit_reason == "sl" for t in trades)


def test_skip_is_recorded():
    def go(ctx, s):
        ctx.skip("gate")
    res = run_session(Script({"09:30:00": go}), tape([("09:29:59", 100.0)]), Costs())
    assert res.skip == "gate" and res.trades == []


def test_bars_close_before_the_next_print_and_are_built_from_ticks():
    tp = tape([("09:30:05", 100.0), ("09:30:40", 102.0), ("09:30:59", 101.0), ("09:32:10", 99.0)])
    bars = build_bars(tp.ts, tp.px, tp.size, 0, len(tp.ts), et_ns(D, "09:30"), et_ns(D, "09:35"), 1)
    assert [(b.o, b.h, b.l, b.c, b.v) for b in bars] == [(100.0, 102.0, 100.0, 101.0, 3),
                                                         (99.0, 99.0, 99.0, 99.0, 1)]
    assert bars[0].end_ns == et_ns(D, "09:31")
    s = Script({}, bars=1)
    run_session(s, tp, Costs())
    assert [b.c for b in s.seen] == [101.0, 99.0]

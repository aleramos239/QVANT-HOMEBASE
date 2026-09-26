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


def run(rows, plan=None, slip=1.0, comm=4.0, root="NQ", **kw):
    return run_session(Script(plan or PLAN(), **kw), tape(rows, root=root), Costs(comm, slip), qty=1)


def one(rows, plan=None, slip=1.0, comm=4.0, root="NQ", **kw):
    return run(rows, plan, slip, comm, root, **kw).trades


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
    # Fix round 1, ruling on tp_rr + move_brackets_to_fill: the SL moves FIRST (keeping
    # its distance to `ref`), then TP is derived from the fill and the MOVED SL's
    # distance -- so this no longer matches the old (pre-fix) mutually-exclusive
    # tp_rr-vs-move behaviour; the numbers below are the corrected ones.
    def go(ctx, s):
        ctx.market("short", sl=110.0, tp=95.0, tp_rr=0.75, ref=100.0)
    t, = one([("09:59:59", 100.0), ("10:00:00.100", 101.0), ("10:05", 93.0)],
             plan={"10:00": go, "15:55": flat})
    assert t.entry_price == 100.75                     # first print after 85 ms, minus 1 tick
    d = t.entry_price - 100.0                          # ref
    assert t.sl == to_tick(110.0 + d, TICK) == 110.75   # SL moved first, same distance to ref
    assert t.tp == to_tick(t.entry_price - 0.75 * abs(100.0 - 110.0), TICK) == 93.25
    assert t.exit_reason == "tp" and t.exit_price == 93.25


def test_tp_rr_moves_the_sl_first_then_derives_tp_from_its_distance():
    """Fix round 1, reviewer's worked case: stop entry long at 110, sl=105, tp_rr=3,
    move on, print gaps to 112 -> fill 112.25 -> SL 107.25, TP 127.25."""
    def go(ctx, s):
        ctx.stop_entry("long", 110.0, sl=105.0, tp_rr=3.0)
    t, = one([("09:29:59", 100.0), ("09:30:01", 112.0), ("09:31", 130.0)],
             plan={"09:30:00": go, "15:55": flat})
    assert t.entry_price == 112.25
    assert t.sl == 107.25 and t.tp == 127.25
    assert t.exit_reason == "tp" and t.exit_price == 127.25


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


# ---- Fix round 1 -----------------------------------------------------------
# Item 1: float tick-grid comparisons must be snapped + epsilon-tolerant. Raw
# float64 arithmetic on non-power-of-two ticks (CL 0.01, GC 0.1, SI 0.005)
# routinely lands a hair off the clean grid value, which then rejects a real
# print sitting exactly at that level.

def test_cl_tp_penetration_survives_tick_grid_float_noise():
    """CL tick 0.01: a long's `tp=64.01` needs a print >= 64.01 + 0.01, which in raw
    float64 is 64.02000000000001 -- a real print at exactly 64.02 must still fill
    it (this hits ~11.5% of CL levels). Mirrored for the short side."""
    t, = one([("09:29:59", 63.80), ("09:30:01", 63.90), ("09:31", 64.02)],
             plan={"09:30:00": lambda ctx, s: ctx.stop_entry("long", 63.90, sl=63.80, tp=64.01),
                   "15:55": flat},
             root="CL", move=False)
    assert t.entry_price == 63.91 and t.tp == 64.01
    assert t.exit_reason == "tp" and t.exit_price == 64.01

    t, = one([("09:29:59", 64.20), ("09:30:01", 64.10), ("09:31", 64.01)],
             plan={"09:30:00": lambda ctx, s: ctx.stop_entry("short", 64.10, sl=64.20, tp=64.02),
                   "15:55": flat},
             root="CL", move=False)
    assert t.entry_price == 64.09 and t.tp == 64.02
    assert t.exit_reason == "tp" and t.exit_price == 64.02


def test_gc_stop_entry_price_survives_anchor_offset_float_noise():
    """GC tick 0.1: a strategy's own `anchor + offset` arithmetic (2047.9 + 0.3) lands
    on 2048.2000000000003 in raw float64 -- an exact touch at 2048.2, never exceeded
    again, must still trigger the stop (not be silently missed). Mirrored short."""
    def go_long(ctx, s):
        a = ctx.last_price
        ctx.stop_entry("long", a + 0.3, sl=a - 0.3, tp=a + 5.0)
    t, = one([("09:29:59", 2047.9), ("09:30:01", 2048.2)], plan={"09:30:00": go_long},
             root="GC", move=False)
    assert t.order_price == 2048.2
    assert t.entry_price == 2048.3                      # touch + 1 tick slip
    assert t.exit_reason == "eod" and t.exit_price == 2048.1

    def go_short(ctx, s):
        a = ctx.last_price
        ctx.stop_entry("short", a - 0.2, sl=a + 0.3, tp=a - 5.0)
    t, = one([("09:29:59", 2000.1), ("09:30:01", 1999.9)], plan={"09:30:00": go_short},
             root="GC", move=False)
    assert t.order_price == 1999.9
    assert t.entry_price == 1999.8                      # touch - 1 tick slip
    assert t.exit_reason == "eod" and t.exit_price == 2000.0


def test_si_stop_entry_price_survives_anchor_offset_float_noise():
    """SI tick 0.005: same anchor+offset float noise, on a third (smaller) grid."""
    def go_long(ctx, s):
        a = ctx.last_price
        ctx.stop_entry("long", a + 0.01, sl=a - 0.01, tp=a + 0.05)
    t, = one([("09:29:59", 18.01), ("09:30:01", 18.02)], plan={"09:30:00": go_long},
             root="SI", move=False)
    assert t.order_price == 18.02
    assert t.entry_price == 18.025                      # touch + 1 tick slip
    assert t.exit_reason == "eod" and t.exit_price == 18.015

    def go_short(ctx, s):
        a = ctx.last_price
        ctx.stop_entry("short", a - 0.01, sl=a + 0.01, tp=a - 0.05)
    t, = one([("09:29:59", 18.005), ("09:30:01", 17.995)], plan={"09:30:00": go_short},
             root="SI", move=False)
    assert t.order_price == 17.995
    assert t.entry_price == 17.99                       # touch - 1 tick slip
    assert t.exit_reason == "eod" and t.exit_price == 18.0


# Item 3: a strategy callback that crashes (e.g. `ctx.last_price` is None with no
# print before the fire time) must not blow up the run -- it records a skip.

def test_missing_last_price_at_fire_time_is_caught_and_recorded_as_skip():
    for rows in ([], [("09:30:01", 100.0), ("09:31", 101.0)]):
        res = run(rows)
        assert res.trades == []
        assert res.skip is not None and res.skip.startswith("strategy error:")


# Item 4: short-side coverage for gross P&L and MAE/MFE (previously long-only).

def test_stop_loss_is_touch_and_pays_slip_and_gap_short_side():
    t, = one([("09:29:59", 100.0), ("09:30:01", 90.0), ("09:31", 94.75)])
    assert (t.entry_price, t.sl) == (89.75, 94.75)
    assert t.exit_reason == "sl" and t.exit_price == 95.0
    t, = one([("09:29:59", 100.0), ("09:30:01", 90.0), ("09:31", 96.0)])
    assert t.exit_price == 96.25
    assert t.gross == round((89.75 - 96.25) * 20, 2) and t.net == t.gross - 4.0


def test_mae_mfe_short_side():
    t, = one([("09:29:59", 100.0), ("09:30:01", 90.0), ("09:31:30", 92.0), ("09:32", 80.0),
              ("09:33", 74.5)])
    assert t.side == "short"
    assert (t.mae_pts, t.mfe_pts) == (2.25, 15.25)
    assert (t.mae_usd, t.mfe_usd) == (45.0, 305.0)
    assert t.bars == 4 and t.seconds == 179.0

"""NQ 09:30-09:45 RANGE BREAK 15m on the VWAP side, NY AM (stack, shadow): the first 15-minute close after 09:45 beyond the
09:30-09:45 range is the day's one signal; with the session VWAP on its side -> market with the break, stop 2 x (close - the
range's other edge), target 1.5R. One trade. 1 NQ.

THE LAB COPY of the stack rule vh_i7_orb_15_ny-NQ-tf15, box r_end0945_own2-r1p5 (stack #6 of research/edge-library/out/
vwap_hunt_2026-10-20/hm40/STACK.md / stack.json; spec .../hm40/specs/vh_i7_orb_15_ny.json): engine family `win_break`
(research/edge-library/engine/families/flex.py WinBreak: r_start 09:30, r_end 09:45, entry market, mode follow, wait 0), run as
families/blocks.py B_win_break with the open layer families/_flex.py (gate vwap_dev, g_lvl 0, g_side with) on l2sim.Template;
tf 15, dir both, max_tr 1, hold_to day, stop_mode own x 2.0 (Template._dist: the structure level is the range's other edge),
tgt_r 1.5, every other block off. win_break runs ONE instance only: the pass that holds the first 15-minute close after
r_end (10:00 -> nyam; flex._Window.fam_filter), so this is the only file; SESSION stays a constant like the other stack drafts.

THE RULE, as the engine runs it (New York times; the trade date's own 1-minute bars from 00:00):
  1. Bars: 15-minute bars on the ET clock. A bucket whose last minute had no print closes when the next bucket's first minute
     arrives (Template.on_bar), before that minute counts. Every 15-minute bar since 00:00 feeds the ATR (mean true range of
     the bars so far up to 14, then Wilder; the day's first bar's tr = high - low); all of it restarts each day.
  2. The range: high / low of the 1-minute bars that start 09:30 .. 09:44 (Template.rng(09:30, 09:45)).
  3. The session VWAP: volume-weighted typical price (h + l + c) / 3 of the 1-minute bars from 09:30 (the tester session nyam;
     Template.vw), and its volume-weighted sigma; at a close it holds every minute up to that close.
  4. At each 15-minute close whose nominal end is after 09:45 and inside the session (09:30 < end <= 11:00), when an entry could
     be placed (3+ bars since 00:00, flat, nothing working, no entry filled yet, the clock before 10:55 -- the session end - 5
     min, and before the day's flatten - 5 min): close > range high -> a long break, close < range low -> a short break, else
     nothing yet. The FIRST break is the day's one signal, traded or not (WinBreak.used).
  5. The gate (flexind VwapDev + gate_ok, line 0, with) on that break: (close - VWAP) / sigma > 0 for a long, < 0 for a short;
     no volume or sigma 0 = no entry. A break the gate turns down ends the day.
  6. Entry: a market order at that close. Stop = 2 x |close - the range's other edge| (the low for a long, the high for a
     short), at least 0.25 x the ATR including the break bar, and 2 ticks; target = 1.5 x that distance. Both re-priced to the
     fill (Template._mkt, move_brackets_to_fill).
  7. Held to the stop or target past the session end; flat at 15:58 (13:13 on a CME half day: l2sim.day_flat).
  In practice the decisions fall at the 10:00, 10:15, 10:30 and 10:45 closes (the 11:00 close is past the 10:55 cut).

WHERE IT DIFFERS FROM THE ENGINE, AND WHY:
  * Flat at 15:58 like the engine, in the tester AND in shadow (a shadow day runs the strategy's own times). Only if ever
    BOOKED on an account does the Desk cap it at 15:55 (labcfg.FLAT_LATEST): a trade still open 15:55-15:58 would then close up
    to 3 minutes earlier. On a CME half day (homebase.backtest.tape.early_close_et, the same calendar as l2sim.EARLY_CLOSES) it
    is flat at 13:13; entries end 10:55 either way.
  * Today's prints are the tester's tape (print-identical to the engine's) or, on the Desk, the live prints: live volume can
    differ from the archive's (late prints), so the session VWAP, and a close within a tick of it or of a range edge, can read
    the other way live.
  * The day window here is 00:00-16:00 (the engine replays to 16:10): nothing is decided after 10:55 in either.
  * Not copied because this box never uses them: the limit / fade entries (entry market, mode follow), trail / exit-bars exits
    (0), every filter block (off), the entry window / day rule / release layer (off), the cancel of a working entry at the
    session end - 5 min (a market entry fills at the next print), prior-day levels, the overnight range, rolls.
  * Fills and costs are the tester's (l2sim is its port: $4.00 a round turn, 1 tick slip on market / stop fills) or the Desk's
    shadow fills; 1 contract of NQ (size set on the Desk). A market entry only: nothing rests, nothing here is shadow-only for
    want of a limit order.
Draws the range high / low and the session VWAP during the session, and marks a break the VWAP gate turned down.

CHECKED 2026-10-21: this file run in-process through homebase/backtest/runner.py (prepare / execute, the real TapeStore over
~/futures_derived) on the store's 42 in-sample months only (883 days, the same 7 days skipped by both: 2021-12-01, 2022-06-21,
2022-08-05, 2023-04-07, 2025-07-04, 2025-11-28, 2026-04-03) equals the store's box r_end0945_own2-r1p5 (library.load_unit of
runs_wf/vh_i7_orb_15_ny-NQ-tf15/is, unit_cell, sess nyam) trade for trade (date, entry time to the ms, side, duration, exit
reason, stop distance, net): 757 / 757, +$190,122 both (exits: 620 at the 15:58 flatten, 107 stop, 30 target; entries at the
10:00 / 10:15 / 10:30 / 10:45 closes 396 / 199 / 101 / 61). First round, no fix needed. The same run flattened at 15:55 (the
Desk's cap if ever booked) keeps the same 757 entries and moves the net to +$196,222 (+$6,100). No test month was run.
"""
from __future__ import annotations

import datetime as dt
import math
from zoneinfo import ZoneInfo

from homebase.backtest.tape import early_close_et
from homebase.strategies.base import Strategy

SESSION = "nyam"                                   # win_break's one pass for r_end 09:45 at tf 15 (flex._Window._plan)
SESS = {"nyam": (34200, 39600), "mid": (39600, 48600), "pm": (48600, 57480)}     # seconds after 00:00 ET (l2sim.SESS)
ET = ZoneInfo("America/New_York")
NS = 1_000_000_000
TF = 15                                            # minutes
STEP = TF * 60 * NS
R_START, R_END = 34200, 35100                      # the range: 1-minute bars 09:30 .. 09:44 (r_start 09:30, r_end 09:45)
STOP_X, TGT_R, MAX_TR, WARM = 2.0, 1.5, 1, 3       # box own2-r1p5; the spec's max_tr; Template.WARM
DAY_FLAT_S, HALF_FLAT_S = 57480, 47580             # 15:58 / 13:13: the engine's flatten (l2sim.day_flat), for the entry cut
FLAT, HALF_FLAT = "15:58", "13:13"                 # when this copy flattens: the engine's day_flat


class NqStackWinBreak15(Strategy):
    id = "draft_nq_sk_winbrk15_nyam"
    name = "NQ 09:30-09:45 range break 15m on the VWAP side, NY AM, own stop x2 1.5R (stack, shadow)"
    root = "NQ"
    session_window = ("00:00", "16:00")
    bar_minutes = 1
    session_independent = True
    own_stop = True
    max_trades_day = 1                             # the engine's max_tr: one session per instance

    def times(self):
        return [HALF_FLAT, FLAT]

    def on_session(self, ctx):
        d = ctx.date
        self.t0 = int(dt.datetime(d.year, d.month, d.day, tzinfo=ET).timestamp()) * NS      # 00:00 ET of the trade date
        self.half = early_close_et(ctx.root, d) is not None
        self.s0, self.s1 = SESS[SESSION]
        self.cut = min(self.s1, HALF_FLAT_S if self.half else DAY_FLAT_S) - 300            # no entry from here (seconds)
        self.cur = None                            # the 15-minute bar being built: [k, h, l, c]
        self.C, self.TR = [], []
        self.atr = None
        self.rh = self.rl = None                   # the range high / low
        self.vs = [0.0, 0.0, 0.0]                  # session VWAP sums: volume, volume x typical, volume x typical^2
        self.order, self.n_ent, self.used = None, 0, False

    def on_bar(self, ctx, bar):
        k = bar.start_ns // STEP
        if self.cur is not None and self.cur[0] != k:
            self._close(ctx)                       # the bucket's last minute had no print: it closes now, before this minute counts
        s = (bar.start_ns - self.t0) // NS
        if R_START <= s and s + 60 <= R_END:
            self.rh = bar.h if self.rh is None else max(self.rh, bar.h)
            self.rl = bar.l if self.rl is None else min(self.rl, bar.l)
        if self.s0 <= s < self.s1 and bar.v > 0:
            v, tp = bar.v, (bar.h + bar.l + bar.c) / 3.0
            a = self.vs
            a[0] += v
            a[1] += v * tp
            a[2] += v * tp * tp
        c = self.cur
        if c is None:
            self.cur = [k, bar.h, bar.l, bar.c]
        else:
            c[1], c[2], c[3] = max(c[1], bar.h), min(c[2], bar.l), bar.c
        if bar.end_ns % STEP == 0:
            self._close(ctx)

    def _vwap(self):
        """(VWAP, sigma) of the session so far, or None (l2sim.Template._vw)."""
        a = self.vs
        if a[0] <= 0:
            return None
        m = a[1] / a[0]
        return m, math.sqrt(max(a[2] / a[0] - m * m, 0.0))

    def _close(self, ctx):
        k, h, l, c = self.cur
        self.cur = None
        self.TR.append(h - l if not self.C else max(h - l, abs(h - self.C[-1]), abs(l - self.C[-1])))
        self.C.append(c)
        n = len(self.C)
        self.atr = sum(self.TR) / n if n <= 14 else (self.atr * 13.0 + self.TR[-1]) / 14.0
        o = self.order
        if o is not None and o.status != "working":
            self.n_ent += o.status == "filled"
            self.order = None
        end = ((k + 1) * STEP - self.t0) // NS     # the bar's nominal clock end, seconds after 00:00 ET
        if not self.s0 < end <= self.s1:
            return
        t = (k + 1) * STEP
        w = self._vwap()
        if w is not None:
            ctx.plot("session VWAP", t, w[0])
        if self.rh is not None:
            ctx.plot("range high", t, self.rh)
            ctx.plot("range low", t, self.rl)
        if (self.used or end <= R_END or self.order is not None or not ctx.flat or self.n_ent >= MAX_TR or n < WARM
                or ctx.now_ns - self.t0 >= self.cut * NS or self.rh is None):
            return                                 # Template.can_enter, then WinBreak.fam_signal's own checks
        side = "long" if c > self.rh else "short" if c < self.rl else None
        if side is None:
            return
        self.used = True                           # the FIRST break is the day's one signal, traded or not
        sd = 1 if side == "long" else -1
        if w is None or not w[1] or w[1] <= 0 or not (c - w[0]) / w[1] * sd > 0.0:
            ctx.mark("range break, VWAP gate", t - 1, c, "against VWAP", side)
            return                                 # the gate (flexind.VwapDev, gate_ok line 0 with)
        far = self.rl if sd > 0 else self.rh
        d = max(max(abs(c - far) * STOP_X, 0.25 * self.atr), 2 * ctx.tick)
        ctx.move_brackets_to_fill = True
        self.order = ctx.market(side, sl=c - sd * d, tp=c + sd * TGT_R * d, ref=c)

    def on_time(self, ctx, et_time):
        if et_time == FLAT or (et_time == HALF_FLAT and self.half):
            ctx.flatten("time")

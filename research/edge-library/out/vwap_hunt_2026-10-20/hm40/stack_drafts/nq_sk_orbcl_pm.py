"""NQ ORB CONFIRM LONG 5m, NY PM (stack, shadow): once the 09:30-10:30 range is done, a 5-minute close above its high while the
close is above the session's VWAP -> market long, stop 1.5 x (close - range low), target 2R. One trade.

THE LAB COPY of the stack rule vh_i7_orbc_long_5_ny-NQ-tf5, box or_min60_own1p5-r2 (stack #1 of research/edge-library/out/
vwap_hunt_2026-10-20/hm40/STACK.md; engine family `orb_confirm`: research/edge-library/engine/families/round1.py OrbConfirm, run
as families/blocks.py B_orb_confirm with the open layer families/_flex.py, on l2sim.Template; spec .../hm40/specs/
vh_i7_orbc_long_5_ny.json; or_min 60, dir long, max_tr 1, tf 5, hold_to day, gate vwap_dev g_lvl 0 g_side with, stop_mode own
1.5, tgt_r 2.0, every other block off). The engine runs nyam / mid / pm as three INDEPENDENT instances (run_idea.cell_specs);
this file is the one for SESSION below. nq_sk_orbcl_nyam / _mid / _pm are the same code but for SESSION, `id` and `name`.

THE RULE, as the engine runs it (New York times):
  1. Bars: the trade date's 1-minute bars from 00:00, summed into 5-minute bars on the clock. A 5-minute bar whose last minute had
     no print closes when the next bucket's first minute arrives (the engine does the same). Every 5-minute bar since 00:00 feeds
     the ATR (mean true range of the bars so far up to 14, then Wilder; the day's first bar's tr = high - low).
  2. The range: high / low of the 1-minute bars that start 09:30 .. 10:29 (l2sim.Template.rng(09:30, 10:30)).
  3. The session's VWAP: volume-weighted typical price (h + l + c) / 3 of the 1-minute bars of THIS session from its start (nyam
     09:30, mid 11:00, pm 13:30: the Template's session VWAP restarts at each of the tester's sessions), and its volume-weighted
     sigma. The gate (flexind vwap_dev, line 0, with): (close - VWAP) / sigma > 0; no volume or sigma 0 = no entry.
  4. At a 5-minute close whose clock end lies after 10:30, after the session start and at or before the session end: close > range
     high AND the gate holds -> market long at the close. At least 3 bars since 00:00, flat, nothing working, no entry yet in this
     session (max_tr 1 counts FILLED entries), and the close before the session end - 5 min (and before the day's flatten - 5 min).
  5. Stop = 1.5 x (close - range low), at least 0.25 ATR and 2 ticks, below the close; target = 2 x that above it; both moved to
     the fill (Template._mkt / _dist, stop_mode own: the structure level is the range low).
  6. Held to stop or target past the session end; flat at 15:58 (13:13 on a CME half day: l2sim.day_flat).

WHERE IT DIFFERS FROM THE ENGINE, AND WHY:
  * Flat at 15:58 like the engine, in the tester AND in shadow (a shadow day runs the strategy's own times). Only if ever BOOKED on
    an account does the Desk cap it at 15:55 (labcfg.FLAT_LATEST): a trade still open 15:55-15:58 would then close up to 3 minutes
    earlier. Most trades of this box end at the flatten (in-sample 926 of 975), yet a 15:55 flatten moved the in-sample nets by
    only +$140 nyam / +$775 mid / -$530 pm (+$385 in all). Entries keep the engine's cut (no close at or after 10:55 in nyam, 13:25 in mid, 15:53 in pm). On a CME half day
    (homebase.backtest.tape.early_close_et, the same calendar as l2sim.EARLY_CLOSES) it is flat at 13:13 and takes no entry from
    13:08 on, as the engine; pm never trades then.
  * Today's prints are the tester's tape (print-identical to the engine's) or, on the Desk, the live prints: live volume can differ
    from the archive's (late prints), so the session VWAP, and a close within a tick of it, can read the other way live.
  * The day window here is 00:00-16:00 (the engine replays to 16:10): nothing is decided after 15:53 in either.
  * Not copied because this box never uses them: trail / exit-bars exits (0), every filter block (off), the author cell (auth off),
    the cancel of a working entry at the session end - 5 min (a market entry fills at the next print), prior-day levels and rolls
    (unused by orb_confirm), the short side (dir long).
  * Fills and costs are the tester's (l2sim is its port) or the Desk's shadow fills; 1 contract of NQ (size set on the Desk).
Draws the range high / low and the session VWAP during its session.

CHECKED 2026-10-21: the three files in the tester's engine (homebase/backtest/runner.execute, the real TapeStore) equal the engine's
three instances trade for trade (day, entry time and price, side, exit time, price and reason, stop, target, net) on ALL 42 in-sample
months of the box's walk-forward (883 days, 876 with a tape both sides; the same 7 gappy days skipped by both): 975 trades (nyam 184 /
mid 388 / pm 403; net +$48,489 / +$129,778 / +$65,038 = +$243,305, the store's own figure). The engine side was re-run from the
store's cell inputs (l2sim.run_many, ALLOW_WF_IS, the store's days) and first checked equal to the store (count, net, every entry).
Exact on the first round: nothing was changed to reach it.
"""
from __future__ import annotations

import datetime as dt
import math
from zoneinfo import ZoneInfo

from homebase.backtest.tape import early_close_et
from homebase.strategies.base import Strategy

SESSION = "pm"                                 # the one session of this instance: nyam | mid | pm
SESS = {"nyam": (34200, 39600), "mid": (39600, 48600), "pm": (48600, 57480)}     # seconds after 00:00 ET (l2sim.SESS)
ET = ZoneInfo("America/New_York")
NS = 1_000_000_000
TF = 5                                             # minutes
STEP = TF * 60 * NS
OPEN, OR_END = 34200, 34200 + 60 * 60              # the range: 1-minute bars 09:30 .. 10:30 (or_min 60)
STOP_X, TGT_R, MAX_TR, WARM = 1.5, 2.0, 1, 3       # box or_min60_own1p5-r2; the spec's max_tr; Template.WARM
DAY_FLAT_S, HALF_FLAT_S = 57480, 47580             # 15:58 / 13:13: the engine's flatten (l2sim.day_flat), for the entry cut
FLAT, HALF_FLAT = "15:58", "13:13"                 # when this copy flattens: the engine's day_flat


class NqOrbConfirmLong5(Strategy):
    id = "draft_nq_sk_orbcl_pm"
    name = "NQ ORB confirm long 5m, NY PM (stack, shadow)"
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
        self.cur = None                            # the 5-minute bar being built: [k, h, l, c]
        self.C, self.TR = [], []
        self.atr = None
        self.orh = self.orl = None                 # the range high / low
        self.vs = [0.0, 0.0, 0.0]                  # session VWAP sums: volume, volume x typical, volume x typical^2
        self.order, self.n_ent = None, 0

    def on_bar(self, ctx, bar):
        k = bar.start_ns // STEP
        if self.cur is not None and self.cur[0] != k:
            self._close(ctx)                       # the bucket's last minute had no print: it closes now, before this minute counts
        s = (bar.start_ns - self.t0) // NS
        if OPEN <= s and s + 60 <= OR_END:
            self.orh = bar.h if self.orh is None else max(self.orh, bar.h)
            self.orl = bar.l if self.orl is None else min(self.orl, bar.l)
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
        end = ((k + 1) * STEP - self.t0) // NS     # the bar's clock end, seconds after 00:00 ET
        if not self.s0 < end <= self.s1:
            return
        t = (k + 1) * STEP
        w = self._vwap()
        if w is not None:
            ctx.plot("session VWAP", t, w[0])
        if end <= OR_END or self.orh is None:
            return
        ctx.plot("range high", t, self.orh)
        ctx.plot("range low", t, self.orl)
        if (self.order is not None or not ctx.flat or self.n_ent >= MAX_TR or n < WARM
                or ctx.now_ns - self.t0 >= self.cut * NS or c <= self.orh):
            return
        if w is None or not w[1] or w[1] <= 0 or not (c - w[0]) / w[1] > 0.0:
            return                                 # the gate: the close above the session VWAP (flexind.VwapDev, gate_ok)
        d = max(max(abs(c - self.orl) * STOP_X, 0.25 * self.atr), 2 * ctx.tick)
        ctx.move_brackets_to_fill = True
        self.order = ctx.market("long", sl=c - d, tp=c + TGT_R * d, ref=c)

    def on_time(self, ctx, et_time):
        if et_time == FLAT or (et_time == HALF_FLAT and self.half):
            ctx.flatten("time")

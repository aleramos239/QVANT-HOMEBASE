"""NQ RVOL BREAK 15m, NY midday (stack, shadow): a 15-minute close beyond the 20 bars before it on at least 1.5x the volume that clock
window usually trades -> market with the break, stop at the break bar's other extreme (x 1.0), target 2R.

THE LAB COPY of vh_i17_rvbrk_15_ny-NQ-tf15 box m1p5_own1-r2: stack rule 2 of PREREG_HM40.md Amendment K (hm40/STACK.md, stack.json).
Engine family `rvol_break` (research/edge-library/engine/families/xflow.py RvolBreak, wrapped by families/blocks.py, on l2sim.Template);
spec hm40/specs/vh_i17_rvbrk_15_ny.json; store runs_wf/vh_i17_rvbrk_15_ny-NQ-tf15/is; inputs: tf 15, n 20, m 1.5, max_tr 3, dir both,
hold_to day, stop_mode own, stop_val 1.0, tgt_r 2.0, every filter / block / gate off. The engine runs nyam / mid / pm as three
INDEPENDENT instances (one session each, own max_tr, one position each); this file is the one for SESSION below. The three drafts
nq_sk_rvbrk15_nyam / _mid / _pm are the same code but for SESSION, `id` and `name`.

THE RULE, as the engine runs it (New York times):
  1. Bars: the trade date's 1-minute bars from 00:00, summed into 15-minute bars on the clock (:00 :15 :30 :45). A 15-minute bar whose
     last minute had no print closes when the next bucket's first minute arrives (the engine does the same). Every 15-minute bar since
     00:00 feeds the ATR and the 20-bar range; all of it restarts each day.
  2. ATR: the mean true range of the bars so far up to 14, then Wilder ((atr x 13 + tr) / 14); the day's first bar's tr = high - low.
  3. At a 15-minute close, with at least 21 bars since 00:00: close > the highest high of the 20 bars before it = long, close < their
     lowest low = short, AND its RVOL >= 1.5.
  4. RVOL = the bar's volume / the median, over the last 14 prior trade dates that have a tape, of the volume traded in the same clock
     window [bar start, bar end). No value (no trade) with fewer than 10 such dates or a median of 0 (avwap.vol_ref, xflow._Rvol).
  5. Entries only at a close whose clock end lies after the session start and at or before the session end, before the session end - 5
     minutes (and before the day's flatten - 5 minutes), at most 3 FILLED entries in the session, one position at a time, none while an
     entry still works.
  6. Market at the close. Stop distance = max(|close - the break bar's other extreme| x 1.0 (a long: close - the bar's low; a short: the
     bar's high - close), 0.25 x ATR, 2 ticks) from the signal close; target 2 x that distance; both moved to the fill (l2sim._dist,
     stop_mode own).
  7. Held to stop or target past the session end; flat at the day's flatten.

WHERE IT DIFFERS FROM THE ENGINE, AND WHY:
  * Flat at 15:58 like the engine, in the tester AND in shadow (a shadow day runs the strategy's own times). Only if ever BOOKED on an
    account does the Desk cap it at 15:55 (labcfg.FLAT_LATEST): then a trade still open 15:55-15:58 closes up to 3 minutes earlier.
    Entries keep the engine's cut (before 15:53 in pm). On a CME half day (homebase.backtest.tape.early_close_et, the same calendar as
    l2sim.EARLY_CLOSES) it is flat at 13:13 and takes no entry from 13:08 on, as the engine; pm never trades then.
  * The prior dates' minute volume comes from the feed (needs_minute_volume / ctx.minute_volume: the last 14 dates of ctx.daily's
    calendar, each date's own tape), not from the engine's cache/minvol_NQ.npz. Same sums; a date that is in one calendar and not the
    other changes which 14 dates are compared. No feed, or under 10 dates with a tape = no trade (fail closed; ctx.skip says so).
  * Today's bar volume is the tester's tape (print-identical to the engine's) or, on the Desk, the live prints: live volume can differ
    from the archive's (late prints), so RVOL near 1.5 can read the other way live.
  * The day window here is 00:00-16:00 (the engine replays to 16:10): nothing is decided after 15:53 in either.
  * Not copied because this box never uses them: trail / exit-bars exits (0), the filters / blocks / gate (all off), the cancel of a
    working entry at the session end - 5 min (a market entry fills at the next print), the prior-day levels and roll list (unused).
  * Fills and costs are the tester's (l2sim is its port) or the Desk's shadow fills; 1 contract of NQ (size set on the Desk).
  * Market entry only (no limit): the Desk can book it, but it is meant for shadow (the stack is judged in shadow).
Draws the 20-bar high / low during its session and marks every break it reads there with its RVOL (traded or not).

CHECKED (2026-10-21, round 1, no fix needed): each of the three drafts run in-process through homebase/backtest/runner.py
prepare/execute (the real TapeStore over ~/futures_derived, the minute-volume feed) on the store's own in-sample days (the 3:1
in-sample months 2021-10 .. 2026-04 of runs_wf/vh_i17_rvbrk_15_ny-NQ-tf15/is: 883 sessions, the same 7 gappy days skipped by both,
3 opening days with no RVOL in both) against the engine's trades of box m1p5_own1-r2 for that session (library.load_unit / unit_cell,
sess code): nyam 108 = 108 trades, net $26,478 = $26,478; mid 193 = 193, $50,358 = $50,358; pm 201 = 201, $32,531 = $32,531.
Every trade EXACT: same day, entry millisecond, side, stop distance (risk), exit reason, exit time (within the engine's whole-second
duration) and net. No test month was read.
"""
from __future__ import annotations

import datetime as dt
import statistics
from zoneinfo import ZoneInfo

from homebase.backtest.tape import early_close_et
from homebase.strategies.base import Strategy

SESSION = "mid"                                 # the one session of this instance: nyam | mid | pm
SESS = {"nyam": (34200, 39600), "mid": (39600, 48600), "pm": (48600, 57480)}     # seconds after 00:00 ET (l2sim.SESS)
ET = ZoneInfo("America/New_York")
NS = 1_000_000_000
TF = 15                                            # minutes
STEP = TF * 60 * NS
N, M = 20, 1.5                                     # bars before the signal bar; RVOL at least
STOP_OWN, ATR_FLOOR, TGT_R, MAX_TR = 1.0, 0.25, 2.0, 3     # box m1p5_own1-r2 (own stop x 1.0, floor 0.25 ATR); the spec's max_tr
DAY_FLAT_S, HALF_FLAT_S = 57480, 47580             # 15:58 / 13:13: the engine's flatten (l2sim.day_flat), for the entry cut
FLAT, HALF_FLAT = "15:58", "13:13"                 # when this copy flattens: the engine's day_flat
VOL_DAYS, VOL_MIN, MIN0, NMIN = 14, 10, -360, 1380     # avwap.VOL_DAYS / VOL_MIN, blocks.MIN0 / NMIN (the feed's minute index)


class NqSkRvolBreak15(Strategy):
    id = "draft_nq_sk_rvbrk15_mid"
    name = "NQ RVOL break 15m, NY midday (stack, shadow)"
    root = "NQ"
    session_window = ("00:00", "16:00")
    bar_minutes = 1
    session_independent = True
    max_trades_day = 3                             # the engine's max_tr: one session per instance

    def needs_minute_volume(self):
        return VOL_DAYS

    def times(self):
        return [HALF_FLAT, FLAT]

    def on_session(self, ctx):
        d = ctx.date
        self.t0 = int(dt.datetime(d.year, d.month, d.day, tzinfo=ET).timestamp()) * NS      # 00:00 ET of the trade date
        self.half = early_close_et(ctx.root, d) is not None
        self.s0, s1 = SESS[SESSION]
        self.cut = min(s1, HALF_FLAT_S if self.half else DAY_FLAT_S) - 300                 # no entry from here (seconds)
        self.cur = None                            # the 15-minute bar being built: [k, h, l, c, v]
        self.H, self.L, self.C, self.V, self.TR = [], [], [], [], []
        self.atr = None
        self.order, self.n_ent = None, 0
        mv = getattr(ctx, "minute_volume", None)
        self.mv = list(mv)[-VOL_DAYS:] if isinstance(mv, (list, tuple)) else []
        if sum(1 for r in self.mv if self._vol(r) is not None) < VOL_MIN:
            ctx.skip("no RVOL: fewer than %d of the last %d dates have minute volume" % (VOL_MIN, VOL_DAYS))

    @staticmethod
    def _vol(r):
        v = r.get("vol") if isinstance(r, dict) else None
        return v if v is not None and len(v) == NMIN else None

    def _rvol(self, b):
        """The closed bar's volume / the median volume of its clock window [b - 15 min, b) on the prior dates, or None."""
        i, j = (b - TF * 60) // 60 - MIN0, b // 60 - MIN0
        ref = [sum(v[i:j]) for v in (self._vol(r) for r in self.mv) if v is not None]
        if len(ref) < VOL_MIN:
            return None
        med = statistics.median(ref)
        return self.V[-1] / med if med > 0 else None

    def on_bar(self, ctx, bar):
        k = bar.start_ns // STEP
        if self.cur is not None and self.cur[0] != k:
            self._close(ctx)                       # the bucket's last minute had no print: it closes now (as the engine)
        c = self.cur
        if c is None:
            self.cur = [k, bar.h, bar.l, bar.c, bar.v]
        else:
            c[1], c[2], c[3], c[4] = max(c[1], bar.h), min(c[2], bar.l), bar.c, c[4] + bar.v
        if bar.end_ns % STEP == 0:
            self._close(ctx)

    def _close(self, ctx):
        k, h, l, c, v = self.cur
        self.cur = None
        self.TR.append(h - l if not self.C else max(h - l, abs(h - self.C[-1]), abs(l - self.C[-1])))
        self.H.append(h)
        self.L.append(l)
        self.C.append(c)
        self.V.append(v)
        n = len(self.C)
        self.atr = sum(self.TR) / n if n <= 14 else (self.atr * 13.0 + self.TR[-1]) / 14.0
        o = self.order
        if o is not None and o.status != "working":
            self.n_ent += o.status == "filled"
            self.order = None
        end = ((k + 1) * STEP - self.t0) // NS     # the bar's clock end, seconds after 00:00 ET
        if n < N + 1 or not self.s0 < end <= SESS[SESSION][1]:
            return
        hi, lo = max(self.H[-N - 1:-1]), min(self.L[-N - 1:-1])
        ctx.plot("20-bar high", (k + 1) * STEP, hi)
        ctx.plot("20-bar low", (k + 1) * STEP, lo)
        if self.order is not None or not ctx.flat or self.n_ent >= MAX_TR or ctx.now_ns - self.t0 >= self.cut * NS:
            return
        sd = 1 if c > hi else -1 if c < lo else 0
        if not sd:
            return
        r = self._rvol(end)
        side = "long" if sd > 0 else "short"
        ctx.mark("break", (k + 1) * STEP - 1, c, "RV %.1f" % r if r is not None else "RV none", side)
        if r is None or r < M:
            return
        struct = l if sd > 0 else h                # the break bar's other extreme (xflow.RvolBreak struct=)
        dist = max(abs(c - struct) * STOP_OWN, ATR_FLOOR * self.atr, 2 * ctx.tick)
        ctx.move_brackets_to_fill = True
        self.order = ctx.market(side, sl=c - sd * dist, tp=c + sd * TGT_R * dist, ref=c)

    def on_time(self, ctx, et_time):
        if et_time == FLAT or (et_time == HALF_FLAT and self.half):
            ctx.flatten("time")

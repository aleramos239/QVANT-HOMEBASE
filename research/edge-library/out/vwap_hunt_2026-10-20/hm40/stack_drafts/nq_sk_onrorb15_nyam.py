"""NQ OVERNIGHT-BIAS OPENING-RANGE BREAK 15m, New York 09:30-15:30 (stack, shadow): the 09:30 open in the top / bottom third
of the 01:00-09:30 range makes a long-only / short-only day; from the 10:30 close on, the first 15-minute close beyond the
09:30-09:45 range on that side with ADX(14) above 10 -> market with the break, stop 0.6 x A, target 2R, flat 15:30. One a day.

THE LAB COPY of the stack rule vh_i27_onrorb_15_ny-NQ-tf15, box adx_min10_own2-r2 (stack #7 of research/edge-library/out/
vwap_hunt_2026-10-20/hm40/STACK.md / stack.json; spec .../hm40/specs/vh_i27_onrorb_15_ny.json): engine family `onr_orb`
(research/edge-library/engine/families/onr.py OnrOrb: k 0.3, adx_min 10, ov_from 01:00, earliest 10:30), run as
families/blocks.py B_onr_orb on l2sim.Template; tf 15, dir both, max_tr 1, hold_to day, stop_mode own x 2.0 (Template._dist:
the structure level is the signal close -/+ k x A), tgt_r 2.0, every block and the open layer off (gate off). onr_orb runs ONE
instance only: the nyam pass, stretched by the family to 09:30-15:30 (OnrOrb.fam_sessions; mid / pm trade nothing,
fam_filter), so this is the only file. The store tags its trades nyam / mid / pm by entry clock; they are all this one pass.

THE RULE, as the engine runs it (New York times; the trade date's own 1-minute bars from 00:00):
  1. Bars: 15-minute bars on the ET clock. A bucket whose last minute had no print closes when the next bucket's first minute
     arrives (Template.on_bar), before that minute counts. Every 15-minute bar since 00:00 feeds the ATR (mean true range of
     the bars so far up to 14, then Wilder; the day's first bar's tr = high - low) and the ADX; all of it restarts each day.
  2. The overnight range: high / low of the 1-minute bars that start 01:00 .. 09:28 and end by 09:30 (Template.rng).
     The 09:30 open: the open of the first 1-minute bar that starts at / after 09:30; it must start by 09:35, else no trade.
     Open > low + 2/3 of the range -> LONG day; open < low + 1/3 -> SHORT day; else (the middle third, a flat range, no
     range) no trade today (OnrOrb.read_bias).
  3. The opening range: high / low of the 1-minute bars that start 09:30 .. 09:44 (Template.rng(09:30, 09:45)).
  4. At each 15-minute close whose nominal end is in 10:30 .. 15:30 (inside the stretched pass, >= `earliest`), when an entry
     could be placed (3+ bars since 00:00, flat, nothing working, no entry yet today, the clock before 15:25 -- the pass end
     - 5 min -- or 13:08 on a half day): LONG day and close > range high, or SHORT day and close < range low, AND Wilder's
     ADX(14) of the 15-minute bars since 00:00 (blocks.adx_last, the signal bar included) > 10 -> the signal. Anything else is
     no signal and does not end the day.
  5. A = the simple average of the last 15 daily Wilder ATR(14) values over the daily bars BEFORE the trade date (the whole
     list, Wilder from its first bar; OnrOrb.a_avg); fewer than 29 daily bars = no trade.
  6. Entry: a market order at that close. Stop = max(2 x |close - (close -/+ 0.3 x A)|, 0.25 x the 15m ATR including the
     signal bar, 2 ticks) -- in practice 0.6 x A; target = 2 x that distance. Both re-priced to the fill (Template._mkt,
     move_brackets_to_fill).
  7. Held to the stop or target; flat at 15:30 (OnrOrb.fam_time, reason "time"), 13:13 on a CME half day (l2sim.day_flat).

WHERE IT DIFFERS FROM THE ENGINE, AND WHY:
  * Flat at 15:30 like the engine (the family's own flatten, before the Template's 15:58; the task's "15:58" is the Template
    default this family overrides), in the tester AND in shadow; 13:13 on a CME half day (homebase.backtest.tape.
    early_close_et, the same calendar as l2sim.EARLY_CLOSES). The Desk's 15:55 cap (labcfg.FLAT_LATEST) never bites.
  * A reads ctx.daily (the tester's / the Desk's daily bars from the tape headers, as the engine's daily cache). The tester
    hands every daily bar from 2021-09-22 on (the archive's first session), the same list as the engine; the Desk hands the
    last ~400 days (labrun/host.daily_bars): Wilder's memory of the bars it leaves out is below 1e-8 of A after 250+
    sessions, and the brackets are rounded to the tick, so it moves nothing in practice.
  * Today's prints are the tester's tape (print-identical to the engine's) or, on the Desk, the live prints: a close within
    a tick of a range edge, the 09:30 open within a tick of a third line, or an ADX near 10 can read the other way live.
  * The day window here is 00:00-16:00 (the engine replays to 16:10): nothing is decided after 15:25 in either.
  * Not copied because this box never uses them: the k / adx_min / ov_from / earliest choices (fixed 0.3 / 10 / 01:00 /
    10:30), trail / exit-bars exits (0), every filter block and the open layer (off), prior-day levels, rolls.
  * Fills and costs are the tester's (l2sim is its port: $4.00 a round turn, 1 tick slip on market / stop fills) or the Desk's
    shadow fills; 1 contract of NQ (size set on the Desk). A market entry only: nothing rests, nothing here is shadow-only for
    want of a limit order.
Draws the opening range high / low, the overnight range's 1/3 and 2/3 lines and the ADX(14) during the pass, and marks a
break on the day's side that the ADX turned down.

CHECKED 2026-10-21: this file run in-process through homebase/backtest/runner.py (prepare / execute, the real TapeStore over
~/futures_derived) on the store's 42 in-sample months only (883 days, the same 7 days skipped by both: 2021-12-01, 2022-06-21,
2022-08-05, 2023-04-07, 2025-07-04, 2025-11-28, 2026-04-03) equals the store's box adx_min10_own2-r2 (library.load_unit of
runs_wf/vh_i27_onrorb_15_ny-NQ-tf15/is, unit_cell, every sess code: the store tags them nyam 237 / mid 86 / pm 33 by entry
clock, all of them this one pass) trade for trade (date, entry time to the ms, side, duration, exit reason, stop distance,
net): 356 / 356, +$147,211 both (exits: 311 at the 15:30 flatten, 40 stop, 5 target; 188 long / 168 short; entries at the
10:30 / 10:45 / 11:00 closes 198 / 39 / 18, the rest later). The first trade is 2021-11-03 in both (A needs 29 daily bars from
2021-09-22). First round, no fix needed. A from the Desk's 400-day daily list vs the full list, on every traded day: at most
2.3e-9 of A apart (well under a tick). No test month was run.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from homebase.backtest.tape import early_close_et
from homebase.strategies.base import Strategy

SESSION = "nyam"                                   # onr_orb's one pass (OnrOrb.fam_filter), stretched to 09:30-15:30
SESS = {"nyam": (34200, 55800)}                    # OnrOrb.fam_sessions: OPEN_S .. PASS_END_S, seconds after 00:00 ET
ET = ZoneInfo("America/New_York")
NS = 1_000_000_000
TF = 15                                            # minutes
STEP = TF * 60 * NS
OV_FROM, OPEN_S, OR_END_S = 3600, 34200, 35100     # overnight range from 01:00; the 09:30 open; the range 09:30-09:45
OPEN_TOL_S, EARLIEST_S = 300, 37800                # the 09:30 bar may start 5 min late; the first signal close 10:30
K, ADX_MIN, ADX_N, A_DAYS, ATR_N = 0.3, 10.0, 14, 15, 14
STOP_X, TGT_R, MAX_TR, WARM = 2.0, 2.0, 1, 3       # box own2-r2; the spec's max_tr; Template.WARM
DAY_FLAT_S, HALF_FLAT_S = 57480, 47580             # 15:58 / 13:13: the engine's day flatten (l2sim.day_flat), for the entry cut
FLAT, HALF_FLAT = "15:30", "13:13"                 # when this copy flattens: OnrOrb.fam_time / day_flat on a half day


def adx_last(H, L, C, n=ADX_N):
    """families/blocks.adx_last, line for line: Wilder's ADX(n) at the last bar, or None with fewer than 2 n bars."""
    N = len(C)
    if N < 2 * n:
        return None
    tr, pdm, mdm = [], [], []
    for i in range(1, N):
        up, dn = H[i] - H[i - 1], L[i - 1] - L[i]
        pdm.append(up if up > dn and up > 0 else 0.0)
        mdm.append(dn if dn > up and dn > 0 else 0.0)
        tr.append(max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1])))
    s_tr, s_p, s_m = sum(tr[:n]), sum(pdm[:n]), sum(mdm[:n])
    dxs = [_dx(s_tr, s_p, s_m)]
    for i in range(n, len(tr)):
        s_tr += tr[i] - s_tr / n
        s_p += pdm[i] - s_p / n
        s_m += mdm[i] - s_m / n
        dxs.append(_dx(s_tr, s_p, s_m))
    a = sum(dxs[:n]) / n
    for x in dxs[n:]:
        a = (a * (n - 1) + x) / n
    return a


def _dx(tr, p, m):
    if tr <= 0:
        return 0.0
    pi, mi = 100.0 * p / tr, 100.0 * m / tr
    return 0.0 if pi + mi == 0 else 100.0 * abs(pi - mi) / (pi + mi)


def a_avg(dl):
    """OnrOrb.a_avg: the simple average of the last 15 daily Wilder ATR(14) values over the daily bars dl; None below 29 bars."""
    if len(dl) < 1 + 2 * ATR_N:
        return None
    trs = [max(dl[i]["h"] - dl[i]["l"], abs(dl[i]["h"] - dl[i - 1]["c"]), abs(dl[i]["l"] - dl[i - 1]["c"])) for i in range(1, len(dl))]
    a = sum(trs[:ATR_N]) / ATR_N
    atrs = [a]
    for x in trs[ATR_N:]:
        a = (a * (ATR_N - 1) + x) / ATR_N
        atrs.append(a)
    return sum(atrs[-A_DAYS:]) / A_DAYS if len(atrs) >= A_DAYS else None


class NqStackOnrOrb15(Strategy):
    id = "draft_nq_sk_onrorb15_nyam"
    name = "NQ overnight-bias opening-range break 15m + ADX 10, NY 09:30-15:30, 0.6A stop 2R (stack, shadow)"
    root = "NQ"
    session_window = ("00:00", "16:00")
    bar_minutes = 1
    session_independent = True
    own_stop = True
    max_trades_day = 1                             # the engine's max_tr: one trade a day

    def needs_daily(self):
        return True                                # A: the daily ATR(14) of the sessions before today

    def times(self):
        return [HALF_FLAT, FLAT]

    def on_session(self, ctx):
        d = ctx.date
        self.t0 = int(dt.datetime(d.year, d.month, d.day, tzinfo=ET).timestamp()) * NS      # 00:00 ET of the trade date
        self.half = early_close_et(ctx.root, d) is not None
        self.s0, self.s1 = SESS[SESSION]
        self.cut = min(self.s1, HALF_FLAT_S if self.half else DAY_FLAT_S) - 300            # no entry from here (seconds)
        self.dl = ctx.daily
        self.cur = None                            # the 15-minute bar being built: [k, h, l, c]
        self.H, self.L, self.C, self.TR = [], [], [], []
        self.atr = None
        self.oh = self.ol = None                   # the overnight range 01:00-09:30
        self.o930 = self.first = None              # the open and start second of the first 1-minute bar from 09:30
        self.rh = self.rl = None                   # the opening range 09:30-09:45
        self.bias = None                           # None = not read yet; 0 = no trade today; +1 / -1
        self.a = None
        self.order, self.n_ent = None, 0

    def on_bar(self, ctx, bar):
        k = bar.start_ns // STEP
        if self.cur is not None and self.cur[0] != k:
            self._close(ctx)                       # the bucket's last minute had no print: it closes now, before this minute counts
        s = (bar.start_ns - self.t0) // NS
        if OV_FROM <= s and s + 60 <= OPEN_S:
            self.oh = bar.h if self.oh is None else max(self.oh, bar.h)
            self.ol = bar.l if self.ol is None else min(self.ol, bar.l)
        if s >= OPEN_S and self.first is None:
            self.o930, self.first = bar.o, s
        if OPEN_S <= s and s + 60 <= OR_END_S:
            self.rh = bar.h if self.rh is None else max(self.rh, bar.h)
            self.rl = bar.l if self.rl is None else min(self.rl, bar.l)
        c = self.cur
        if c is None:
            self.cur = [k, bar.h, bar.l, bar.c]
        else:
            c[1], c[2], c[3] = max(c[1], bar.h), min(c[2], bar.l), bar.c
        if bar.end_ns % STEP == 0:
            self._close(ctx)

    def _read_bias(self):
        """OnrOrb.read_bias: +1 / -1 / 0, or None while the 09:30 open is not known."""
        if self.o930 is None:
            return None
        if self.first - OPEN_S > OPEN_TOL_S or self.oh is None:
            return 0
        hi, lo = self.oh, self.ol
        if hi <= lo:
            return 0
        third = (hi - lo) / 3.0
        if self.o930 > lo + 2.0 * third:
            return 1
        if self.o930 < lo + third:
            return -1
        return 0

    def _close(self, ctx):
        k, h, l, c = self.cur
        self.cur = None
        self.TR.append(h - l if not self.C else max(h - l, abs(h - self.C[-1]), abs(l - self.C[-1])))
        self.H.append(h)
        self.L.append(l)
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
        if self.rh is not None and end > OR_END_S:
            ctx.plot("opening range high", t, self.rh)
            ctx.plot("opening range low", t, self.rl)
        if self.oh is not None and self.oh > self.ol:
            third = (self.oh - self.ol) / 3.0
            ctx.plot("overnight 2/3", t, self.ol + 2.0 * third)
            ctx.plot("overnight 1/3", t, self.ol + third)
        x = adx_last(self.H, self.L, self.C)
        if x is not None:
            ctx.plot("ADX(14) 15m", t, x)
        if (self.order is not None or not ctx.flat or self.n_ent >= MAX_TR or n < WARM
                or ctx.now_ns - self.t0 >= self.cut * NS):
            return                                 # Template.can_enter
        if end <= OR_END_S or end < EARLIEST_S:
            return                                 # OnrOrb.fam_signal from here
        if self.bias is None:
            self.bias = self._read_bias()
        if not self.bias:
            return
        if self.rh is None:
            self.bias = 0
            return
        side = 1 if c > self.rh else -1 if c < self.rl else 0
        if side == 0 or side != self.bias:
            return
        if x is None or not x > ADX_MIN:
            ctx.mark("break, ADX too low", t - 1, c, "ADX %.1f" % (x or 0.0), "long" if side > 0 else "short")
            return
        if self.a is None:
            self.a = a_avg(self.dl)
        if not self.a or self.a <= 0:
            return
        dk = K * self.a
        struct = c - dk if side > 0 else c + dk
        dist = max(max(abs(c - struct) * STOP_X, 0.25 * self.atr), 2 * ctx.tick)      # Template._dist, stop_mode own
        ctx.move_brackets_to_fill = True
        self.order = ctx.market("long" if side > 0 else "short", sl=c - side * dist, tp=c + side * TGT_R * dist, ref=c)

    def on_time(self, ctx, et_time):
        if et_time == FLAT or (et_time == HALF_FLAT and self.half):
            ctx.flatten("time")

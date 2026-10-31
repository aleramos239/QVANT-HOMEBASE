"""NQ DISPLACEMENT 15m on the VWAP side, NY PM instance (stack, shadow): a 15-minute body of at least 1 x ATR(14), on the side
of the session VWAP -> market with it, stop 2 x the candle's far extreme, target 2R. 1 NQ.

THE LAB COPY of the portfolio-hunt rule vh_i6_g_disp_15_ny-NQ-tf15, box k1_own2-r2 (stack #3, STACK.md / stack.json; spec
research/edge-library/out/vwap_hunt_2026-10-20/hm40/specs/vh_i6_g_disp_15_ny.json): engine family `displace`
(research/edge-library/engine/families/flex.py Displace: k 1.0, close_r 0, mode follow) on l2sim.Template, with the open layer's
gate (families/_flex.py + engine/flexind.py: gate vwap_dev, g_lvl 0, g_side with), tf 15, max_tr 3, dir both, hold_to day,
stop_mode own x 2.0 (families/blocks.py -> Template._dist), tgt_r 2.0. The engine runs nyam / mid / pm as three INDEPENDENT
instances, each with its own 3 entries and one position; this file is the one for SESSION below. nq_sk_disp15_nyam / _mid / _pm
are the same code but for SESSION, `id`, `name` and this docstring's first line.

THE RULE, as the engine runs it (New York times; the trade date's own 1-minute bars from 00:00):
  1. Bars: 15-minute bars on the clock. A bucket whose last minute had no print closes when the next bucket's first minute
     arrives (Template.on_bar). Every 15-minute bar since 00:00 feeds the ATR; all of it restarts each day.
  2. ATR(14): the mean true range of the bars so far up to 14, then Wilder ((atr x 13 + tr) / 14); the day's first bar's tr =
     high - low. The yardstick of a bar is the ATR BEFORE it (the bar is never in its own yardstick).
  3. SESSION VWAP (Template.vw): volume-weighted typical price (h + l + c) / 3 of the 1-minute bars of the current tester
     session (asia 00:00, london 03:00, nyam 09:30, mid 11:00, pm 13:30, by each minute's start; 08:25-09:30 and from 15:58
     belong to none and add nothing), restarted whenever a minute's session differs from the last minute's; its sigma = the
     volume-weighted stdev of the typical price. At a close it holds every minute up to that close.
  4. SIGNAL at a 15-minute close, with 14+ bars since 00:00: body |close - open| >= 1.0 x the ATR before it, the bar not a doji
     and its range > 0. Green -> long, red -> short (follow).
  5. GATE (vwap_dev, level 0, with): (close - session VWAP) / sigma > 0 for a long, < 0 for a short; no VWAP or sigma 0 =
     neither side.
  6. ENTRY: a market order at that close, only when the close is inside the session (start < bar end <= session end), the order
     goes out before the session end - 5 minutes (and before the day's flat time - 5 min), it is flat with no working entry,
     and fewer than 3 entries FILLED in this session.
  7. STOP: 2 x |close - the candle's low| (a long) / |close - its high| (a short), never under 0.25 x the ATR including the
     candle, nor 2 ticks. TARGET: 2 x that distance. Both re-priced to the fill (move_brackets_to_fill).
  8. Held to the stop / target past the session end; flattened at 15:58 (13:13 on a CME equity half day).

WHERE IT DIFFERS FROM THE ENGINE, AND WHY:
  * Flat at 15:58 like the engine, in the tester AND in shadow (a shadow day runs the strategy's own times). Only if ever
    BOOKED on an account does the Desk cap it at 15:55 (labcfg.FLAT_LATEST): then a trade still open 15:55-15:58 closes up to 3
    minutes earlier. Entries keep the engine's cut (before 15:53 in pm). On a CME half day it is flat at 13:13 and takes no
    entry from 13:08 on, as the engine; pm never trades then. The half-day calendar is l2sim.EARLY_CLOSES's rule copied below
    (Thanksgiving Friday, Dec 24 on a weekday, the July table; shortcut: the July table ends 2026 as the engine's does -- add a
    later July half day when the exchange lists it).
  * The session is read from on_time (start / end / flat), as the Template's flags; a 15-minute bar closed late (its last
    minute without a print) after the session end is refused by the 5-minute cut in both.
  * The day window here is 00:00-16:00 (the engine replays to 16:10): nothing is decided after 15:53 in either. Which days run
    is the tester's coverage rule over that window.
  * Not copied because this box never uses them: trail / exit-bars exits (0), every filter block (off), the cancel of a working
    entry at the session end - 5 min (a market entry fills at the next print), the prior-day levels, the roll list and the
    daily bars (displace reads none of them), the overnight range.
  * Today's bars are the tester's tape (print-identical to the engine's) or, on the Desk, the live prints: live bars can differ
    from the archive's (late prints), so a body near 1 ATR, or a close a tick from the VWAP, can read the other way live.
  * Fills and costs are the tester's (l2sim is its port: $4.00 a round turn, 1 tick slip on market / stop fills, 85 ms
    placement, the stop live from the print after the entry print) or the Desk's shadow fills; 1 contract of NQ (size set on
    the Desk). A market entry only: nothing rests, nothing here is shadow-only for want of a limit order.
Draws the session VWAP at each 15-minute close in its session, and marks each displacement the VWAP gate turned down.

CHECKED 2026-10-21: the three files run in-process through homebase/backtest/runner.py (prepare / execute, the real TapeStore)
on the store's 42 in-sample months only (883 days, the same 7 days skipped by both: 2021-12-01, 2022-06-21, 2022-08-05,
2023-04-07, 2025-07-04, 2025-11-28, 2026-04-03) equal the engine's three instances of box k1_own2-r2 trade for trade (date,
entry time to the ms, side, duration, exit reason, stop distance, net), first round, no fix needed: nyam 888 / 888 (+$276,398),
mid 590 / 590 (-$2,030), pm 453 / 453 (+$153); 1,931 trades, +$274,521. The half-day calendar equals l2sim.EARLY_CLOSES for
2017-2026. No test month was run.
"""
from __future__ import annotations

import datetime as dt
import math
from zoneinfo import ZoneInfo

from homebase.strategies.base import Strategy

SESSION = "pm"                                   # the one session of this instance: nyam | mid | pm

TAGS = (("asia", 0, 10800), ("london", 10800, 30300), ("nyam", 34200, 39600),
        ("mid", 39600, 48600), ("pm", 48600, 57480))               # l2sim SESS in ORDER: the session VWAP's minutes
SESS = {s: (a, b) for s, a, b in TAGS}
ET = ZoneInfo("America/New_York")
NS = 1_000_000_000
TF = 15 * 60 * NS                                  # 15-minute bars on the ET clock
K = 1.0                                            # box k1: body at least K x the ATR before the bar
STOP_X, TGT_R = 2.0, 2.0                           # box own2-r2: stop_mode own x 2, target 2R
MAX_TR, WARM = 3, 14                               # spec limits.max_tr; Displace.WARM
DAY_FLAT, HALF_FLAT = 57480, 47580                 # 15:58 / 13:13 ET (l2sim.day_flat)
_JULY_HALF = {2021: (7, 2), 2023: (7, 3), 2024: (7, 3), 2025: (7, 3), 2026: (7, 3)}   # l2sim._JULY_HALF


def _half_day(d: dt.date) -> bool:
    """l2sim.EARLY_CLOSES: the day after Thanksgiving, Dec 24 on a weekday, the July half day of the table."""
    nov1 = dt.date(d.year, 11, 1)
    return (d == nov1 + dt.timedelta(days=(3 - nov1.weekday()) % 7 + 22)
            or (d.month, d.day) == (12, 24) and d.weekday() < 5 or _JULY_HALF.get(d.year) == (d.month, d.day))


def _hms(s: int) -> str:
    return "%02d:%02d:%02d" % (s // 3600, s % 3600 // 60, s % 60)


def _tag(s: int):
    for name, a, b in TAGS:
        if a <= s < b:
            return name
    return None


class NqStackDisp15(Strategy):
    id = "draft_nq_sk_disp15_pm"
    name = "NQ displacement 15m on the VWAP side, NY PM, own stop x2 2R (stack, shadow)"
    root = "NQ"
    session_window = ("00:00", "16:00")
    bar_minutes = 1
    session_independent = True
    max_trades_day = 3                             # the engine's max_tr: one session per instance

    def times(self):
        a, b = SESS[SESSION]
        return sorted({_hms(a), _hms(b), _hms(HALF_FLAT), _hms(DAY_FLAT)})

    def on_session(self, ctx):
        d = ctx.date
        self.t0 = int(dt.datetime(d.year, d.month, d.day, tzinfo=ET).timestamp()) * NS      # 00:00 ET of the trade date
        self.flat_s = HALF_FLAT if _half_day(d) else DAY_FLAT
        self.cur = None                            # the 15-minute bar being built: [k, o, h, l, c]
        self.nb = 0                                # 15-minute bars closed since 00:00
        self.pc = None                             # the last closed bar's close
        self.trs = []
        self.atr = self.atr_p = None
        self.vsid, self.vs = None, [0.0, 0.0, 0.0]     # the session VWAP's session and sums (volume, v x tp, v x tp x tp)
        self.on = self.over = False                # inside the session / the session (or the day) is over
        self.n_ent = 0
        self.order = None

    def _vw(self):
        """Template.vw: (session VWAP, sigma) or None."""
        a = self.vs
        if a[0] <= 0:
            return None
        m = a[1] / a[0]
        return m, math.sqrt(max(a[2] / a[0] - m * m, 0.0))

    def _sync(self):
        """Template._sync: count a fill once, forget an order that is not working any more."""
        o = self.order
        if o is not None and o.status != "working":
            self.n_ent += o.status == "filled"
            self.order = None

    def on_bar(self, ctx, bar):
        k = bar.start_ns // TF
        if self.cur is not None and self.cur[0] != k:
            self._close(ctx)                       # the bucket's last minute had no print: it closes now, before this minute
        sid = _tag((bar.start_ns - self.t0) // NS)
        if sid != self.vsid:
            self.vsid, self.vs = sid, [0.0, 0.0, 0.0]
        if sid and bar.v > 0:
            v, tp = bar.v, (bar.h + bar.l + bar.c) / 3.0
            a = self.vs
            a[0] += v
            a[1] += v * tp
            a[2] += v * tp * tp
        c = self.cur
        if c is None:
            self.cur = [k, bar.o, bar.h, bar.l, bar.c]
        else:
            c[2], c[3], c[4] = max(c[2], bar.h), min(c[3], bar.l), bar.c
        if bar.end_ns % TF == 0:
            self._close(ctx)

    def _close(self, ctx):
        """Template._close of a 15-minute bar, can_enter, then Displace.fam_signal and the vwap_dev gate (FlexMods.allowed)."""
        k, o, h, l, c = self.cur
        self.cur = None
        t_end = (k + 1) * TF
        tr = h - l if self.pc is None else max(h - l, abs(h - self.pc), abs(l - self.pc))
        self.pc = c
        self.nb += 1
        if self.nb <= 14:
            self.trs.append(tr)
        self.atr_p = self.atr
        self.atr = sum(self.trs) / self.nb if self.nb <= 14 else (self.atr * 13.0 + tr) / 14.0
        self._sync()
        a, b = SESS[SESSION]
        end = (t_end - self.t0) // NS             # the nominal close: a late close never counts as later
        if not (self.on and a < end <= b):
            return
        w = self._vw()
        if w is not None:
            ctx.plot("Session VWAP", t_end, w[0])
        if self.nb < WARM or not ctx.flat or self.order is not None or self.n_ent >= MAX_TR \
                or ctx.now_ns - self.t0 >= (min(b, self.flat_s) - 300) * NS:
            return
        if c == o or not self.atr_p or h - l <= 0 or abs(c - o) < K * self.atr_p:
            return
        sd = 1 if c > o else -1
        side = "long" if sd > 0 else "short"
        if w is None or not w[1] or w[1] <= 0 or (c - w[0]) / w[1] * sd <= 0:
            ctx.mark("displacement, VWAP gate", t_end - 1, c, "against VWAP", side)
            return
        dist = max(abs(c - (l if sd > 0 else h)) * STOP_X, 0.25 * self.atr, 2 * ctx.tick)
        ctx.move_brackets_to_fill = True
        self.order = ctx.market(side, sl=c - sd * dist, tp=c + sd * TGT_R * dist, ref=c)

    def on_time(self, ctx, et_time):
        """Template.on_time with hold_to = day: the day's flat, the session's end, its start."""
        hh, mm, ss = (int(x) for x in et_time.split(":"))
        sec = hh * 3600 + mm * 60 + ss
        self._sync()
        a, b = SESS[SESSION]
        if sec == self.flat_s:
            ctx.flatten("time")
            self.on, self.over = False, True
        if sec == b:
            self.on, self.over = False, True
        if sec == a and not (self.over or sec >= self.flat_s):
            self.on, self.n_ent = True, 0

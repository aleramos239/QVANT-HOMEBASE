"""NQ VWAP TOUCH + ADX 30, one NY session, 1 NQ contract, for the Desk in SHADOW (paper only).

The Lab copy of the hunt rule vh_i10_adx_touch_5_ny-NQ-tf5, box g_lvl30_pts60-r2 (picked 2026-10-21; spec
research/edge-library/out/vwap_hunt_2026-10-20/hm40/specs/vh_i10_adx_touch_5_ny.json): the engine family vwap_touch
(research/edge-library/engine/families/vwap_touch.py: anchor us, away 160 ticks, near 3 ticks) with the open layer's ADX gate
(families/_flex.py + engine/flexind.py: gate adx, g_n 14, g_side with, g_lvl 30), 5-minute bars, stop 60 NQ points, target 2R,
max_tr 3, dir both, hold_to day, run inside the engine's Template (engine/l2sim.py) with strict_limit (SCREEN_RUN). The engine
runs nyam, mid and pm as three INDEPENDENT instances (run_idea.cell_specs): this file is one of three Lab drafts
(nq_vh_adxtouch_nyam / _mid / _pm), the same code with only SESSION (and the display name) apart.

THE RULE, as the engine runs it (ET; the trade date's own bars from 00:00):
  * VWAP: volume-weighted (h + l + c) / 3 of the 1-minute bars that START at or after 09:30, a minute added when it has ended.
  * ARM: a 1-minute close >= 40 points (160 ticks) above the VWAP (as of that minute's end) arms a LONG, <= 40 below a SHORT;
    the newest such close sets the side.
  * TOUCH: a 1-minute bar whose range comes within 0.75 points (3 ticks) of the VWAP as it stood BEFORE that minute uses the
    arm up, filled or not; a resting order is cancelled at that minute's close. Only a new 40-point close arms it again.
  * ADX: Wilder ADX(14) of the day's closed 5-minute bars since 00:00 (flexind.Adx, ported line by line); an order needs >= 30.
  * ORDER: at each 5-minute close inside the session (the bar ends after the session start and by its end), while flat, with
    fewer than 3 fills this session and before the session end - 5 min: the working order is cancelled; then, with an arm set,
    ADX >= 30 and the last print on the passive side of the VWAP, a LIMIT at the VWAP (rounded to the tick) is placed. It fills
    only on a print 1 tick through it, at its price. A resting order is also cancelled at the session end - 5 min.
  * EXITS: stop 60 points, target 120 points (2R) from the order price, moved to the fill. Held to stop / target or flattened
    at 15:58 ET (13:13 on a CME equity half day) -- NOT at the session end. One position at a time.
  Draws the VWAP and the ADX at each 5-minute close.

DIFFERENCES FROM THE ENGINE, and why:
  1. Flat time. The engine flattens at 15:58 (13:13 on a half day); so does this code, in the tester and in SHADOW (the shadow
     host runs the strategy's own times). Booked on an account, the Desk closes it at its own cap, 15:55 (labcfg.FLAT_LATEST):
     a trade still open then closes 3 minutes before the engine's. The half-day calendar is the engine's EARLY_CLOSES rule
     (Thanksgiving Friday, Dec 24 on a weekday, the July table) copied here; the July table ends 2026 as the engine's does.
  2. Stop arming. The engine ran with strict_limit = True (a limit entry's stop is live ON its fill print); the tester and the
     shadow host arm it one print later (their fill law; a draft cannot change it). With a 60-point stop a single print
     through both the limit and the stop does not happen in practice.
  3. Brackets: ctx.move_brackets_to_fill = True (as the ports). The engine's _lim does not set it, but a limit fills AT its price
     there and in the tester, so it changes nothing; a real fill with price improvement keeps 60 / 120 points from the fill.
  4. Window 00:00-16:00 (the engine's Template: 00:00-16:10): nothing happens after 15:58.
  5. No daily bars asked for (the engine's Template reads them for the prior-day levels, which vwap_touch never uses) and no
     volume feed: nothing to wait for from the day before.
  6. Unchanged: costs are the run's (engine: $4.00 round turn, 1 tick slip on stops / flatten, as the tester's defaults),
     placement latency 85 ms, the coverage rule (the tester's), 1 contract, the late close of a 5-minute bar whose last minute
     had no print (closed at the next minute's bar, as the Template does).
CHECKED 2026-10-21: the three files in the tester's engine equal the engine's three instances trade for trade (entry and exit
time, prices, reason, stop, target, net) on ALL 42 in-sample months of the box's walk-forward (883 days): 405 trades (nyam 263 /
mid 110 / pm 32; net +$61,168 / +$26,485 / -$2,953), strict_limit on and off alike; the half-day calendar equals
l2sim.EARLY_CLOSES for 2017-2026.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from homebase.strategies.base import Strategy

SESSION = (39600, 48600)            # mid 11:00-13:30 ET (l2sim SESS; seconds after 00:00 ET) -- the one setting of this file

ET = ZoneInfo("America/New_York")
NS = 1_000_000_000
TF = 5 * 60 * NS                    # 5-minute bars on the ET clock
ANCHOR = 34200                      # the "us" VWAP starts at 09:30
AWAY, NEAR = 160, 3                 # ticks
ADX_N, ADX_LVL = 14, 30.0
STOP_PTS, TGT_R = 60.0, 2.0         # box g_lvl30_pts60-r2
MAX_TR, WARM = 3, 3                 # entries per session; tf bars since 00:00 before any entry (Template.WARM)
DAY_FLAT, HALF_FLAT = 57480, 47580  # 15:58 / 13:13 (l2sim.day_flat)
_JULY_HALF = {2021: (7, 2), 2023: (7, 3), 2024: (7, 3), 2025: (7, 3), 2026: (7, 3)}   # l2sim._JULY_HALF


def _half_day(d: dt.date) -> bool:
    """l2sim.EARLY_CLOSES: the day after Thanksgiving, Dec 24 on a weekday, the July half day of the table."""
    nov1 = dt.date(d.year, 11, 1)
    return (d == nov1 + dt.timedelta(days=(3 - nov1.weekday()) % 7 + 22)
            or (d.month, d.day) == (12, 24) and d.weekday() < 5 or _JULY_HALF.get(d.year) == (d.month, d.day))


def _hms(s: int) -> str:
    return "%02d:%02d:%02d" % (s // 3600, s % 3600 // 60, s % 60)


class NqVwapTouchAdx(Strategy):
    id = "draft_nq_vh_adxtouch_mid"
    name = "NQ VWAP touch + ADX 30, NY midday, 60 pt stop 2R (shadow)"
    root = "NQ"
    session_window = ("00:00", "16:00")
    bar_minutes = 1
    session_independent = True
    max_trades_day = 3

    def times(self):
        a, b = SESSION
        return sorted({_hms(a), _hms(b - 300), _hms(b), _hms(HALF_FLAT - 300), _hms(HALF_FLAT), _hms(DAY_FLAT - 300), _hms(DAY_FLAT)})

    def on_session(self, ctx):
        d = ctx.date
        self.t0 = int(dt.datetime(d.year, d.month, d.day, tzinfo=ET).timestamp()) * NS
        self.flat_s = HALF_FLAT if _half_day(d) else DAY_FLAT
        self.cur = None                         # the 5-minute bar being built: [k, h, l, c]
        self.nb = 0                             # 5-minute bars closed since 00:00
        self.pc = self.ph = self.pl = self.adx = None
        self.k, self.s_tr, self.s_p, self.s_m, self.dxs = 0, 0.0, 0.0, 0.0, []
        self.vv = self.vp = 0.0                 # VWAP sums from 09:30
        self.arm = 0                            # +1 long (price came from above), -1 short, 0 none
        self.on = self.over = False             # inside the session / the session (or the day) is over
        self.n_ent = 0
        self.order = None
        ctx.move_brackets_to_fill = True

    def _vwap(self):
        return self.vp / self.vv if self.vv > 0 else None

    def _sync(self):
        """Template._sync: count a fill once, forget an order that is not working any more."""
        o = self.order
        if o is not None and o.status != "working":
            self.n_ent += o.status == "filled"
            self.order = None

    def _drop(self, ctx):
        self._sync()
        if self.order is not None:
            ctx.cancel(self.order)
            self.order = None

    def _adx_bar(self, h, l, c):
        """flexind.Adx(14) fed one closed 5-minute bar (Ind.update's true range, then Adx._step). Its value is self.adx."""
        tr = h - l if self.pc is None else max(h - l, abs(h - self.pc), abs(l - self.pc))
        self.pc = c
        if self.ph is None:
            self.ph, self.pl = h, l
            return
        up, dn = h - self.ph, self.pl - l
        pdm = up if up > dn and up > 0 else 0.0
        mdm = dn if dn > up and dn > 0 else 0.0
        self.ph, self.pl = h, l
        self.k += 1
        n = ADX_N
        if self.k <= n:
            self.s_tr, self.s_p, self.s_m = self.s_tr + tr, self.s_p + pdm, self.s_m + mdm
            if self.k < n:
                return
        else:
            self.s_tr += tr - self.s_tr / n
            self.s_p += pdm - self.s_p / n
            self.s_m += mdm - self.s_m / n
        if self.s_tr == 0:
            return
        pi, mi = 100.0 * self.s_p / self.s_tr, 100.0 * self.s_m / self.s_tr
        dx = 0.0 if pi + mi == 0 else 100.0 * abs(pi - mi) / (pi + mi)
        if self.adx is None:
            self.dxs.append(dx)
            if len(self.dxs) >= n:
                self.adx = sum(self.dxs) / n
        else:
            self.adx = (self.adx * (n - 1) + dx) / n

    def _minute(self, ctx, bar):
        """vwap_touch._read for one ended minute: the touch (against the VWAP before it), the VWAP, then the arm."""
        if (bar.start_ns - self.t0) // NS < ANCHOR:
            return
        tk = ctx.tick
        w0 = self._vwap()
        touched = w0 is not None and bar.l <= w0 + NEAR * tk and bar.h >= w0 - NEAR * tk
        if touched:
            self.arm = 0
        if bar.v > 0:
            self.vv += bar.v
            self.vp += bar.v * (bar.h + bar.l + bar.c) / 3.0
        w1 = self._vwap()
        if w1 is not None:
            if bar.c >= w1 + AWAY * tk:
                self.arm = 1
            elif bar.c <= w1 - AWAY * tk:
                self.arm = -1
        if touched:
            self._drop(ctx)

    def _close(self, ctx):
        """Template._close of a 5-minute bar, then can_enter and vwap_touch.fam_signal (the ADX gate in _lim's allowed)."""
        k, h, l, c = self.cur
        self.cur = None
        t_end = (k + 1) * TF
        self._adx_bar(h, l, c)
        self.nb += 1
        w = self._vwap()
        if self.adx is not None:
            ctx.plot("ADX(14) 5m", t_end, self.adx)
        if w is not None:
            ctx.plot("VWAP 09:30", t_end, w)
        self._sync()
        a, b = SESSION
        end = (t_end - self.t0) // NS           # the nominal close: a late close never counts as later
        if not (self.on and a < end <= b) or self.nb < WARM or not ctx.flat or self.n_ent >= MAX_TR \
                or ctx.now_ns - self.t0 >= (min(b, self.flat_s) - 300) * NS:
            return
        self._drop(ctx)                         # re-priced at this close, or dropped when the arm or the gate is gone
        lp = ctx.last_price
        if w is None or not self.arm or lp is None or self.adx is None or self.adx < ADX_LVL:
            return
        sd = self.arm
        if (lp - w) * sd <= 0:
            return                              # only on the passive side of the last print
        self.order = ctx.limit_entry("long" if sd > 0 else "short", w,
                                     sl=w - sd * STOP_PTS, tp=w + sd * TGT_R * STOP_PTS)

    def on_bar(self, ctx, bar):
        k = bar.start_ns // TF
        if self.cur is not None and self.cur[0] != k:
            self._close(ctx)                    # the bucket's last minute had no print: closed now, before this minute
        self._minute(ctx, bar)
        if self.cur is None:
            self.cur = [k, bar.h, bar.l, bar.c]
        else:
            self.cur[1], self.cur[2], self.cur[3] = max(self.cur[1], bar.h), min(self.cur[2], bar.l), bar.c
        if bar.end_ns % TF == 0:
            self._close(ctx)

    def on_time(self, ctx, et_time):
        """Template.on_time with hold_to = day: the day's flat, the session's end - 5 min / end (cancel only), its start."""
        hh, mm, ss = (int(x) for x in et_time.split(":"))
        sec = hh * 3600 + mm * 60 + ss
        self._sync()
        a, b = SESSION
        if sec == self.flat_s:
            ctx.flatten("time")
            self.order, self.on, self.over = None, False, True
        elif sec == self.flat_s - 300:
            self._drop(ctx)
        if sec == b:
            self._drop(ctx)
            self.on, self.over = False, True
        elif sec == b - 300 and self.on:
            self._drop(ctx)
        if sec == a and not (self.over or sec >= self.flat_s):
            self.on, self.n_ent = True, 0

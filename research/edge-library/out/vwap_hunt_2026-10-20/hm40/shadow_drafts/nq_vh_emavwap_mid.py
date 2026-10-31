"""NQ: EMA(13) crosses the 09:30 VWAP on 1.5x relative volume, 5-minute bars -- NY midday instance (11:00-13:30 ET). 1 NQ.

The Lab copy of the portfolio-hunt rule vh_i16_emavwap_rv_5_ny-NQ-tf5, box fast_n13_own1-r1p5
(research/edge-library/out/vwap_hunt_2026-10-20/hm40/specs/vh_i16_emavwap_rv_5_ny.json, picks_hm.json): engine family ma_x
(research/edge-library/engine/families/xflow.py MaX, every block off) on l2sim.Template, hold_to='day'. The engine runs the three
NY sessions as three independent instances, each with its own 3 trades and one position; this file is one of them. The nyam /
mid / pm files differ only in SESSION, the name, the id and this docstring's first line.

THE RULE (New York time; every value is the engine's):
  1. 5-minute bars on the clock, built from the trade date's 1-minute bars from 00:00. A bucket whose last minute had no print
     closes when the next bucket's first minute arrives (l2sim Template.on_bar). Every indicator restarts at 00:00.
  2. FAST = EMA(13) of the 5-minute closes, seeded with the day's first close; no value before the 13th bar.
     SLOW = Template.vwr, the "rth" VWAP of the 1-minute bars (typical price (h+l+c)/3 x volume). It restarts when a minute
     falls in asia (00:00), london (03:00) or nyam (09:30); minutes 08:25-09:30 and from 15:58 add nothing. So before 09:30 the
     slow line is the 03:00 VWAP, from the 09:35 close on the 09:30 VWAP.
  3. CROSS at a 5-minute close: the sign of FAST - SLOW differs from the sign at the last earlier close where both lines existed
     and were not equal (an equal close changes nothing). The sign runs all day: the 09:35 close compares the 09:30 VWAP with
     the sign against the 03:00 one, and a flip there is a cross in the engine and here.
  4. RVOL: the crossing bar's volume / the median, over the last 14 prior trade dates that have a tape (10 at least), of the
     volume in the same clock window [close - 5 min, close) -- from ctx.minute_volume (needs_minute_volume). 1.5 or more.
  5. ENTRY: a market order at that close with the cross (up = long), only when the close is inside the session (start < close
     <= end), the order goes out more than 5 minutes before the session end (and before the day's flat time - 5 min), 3+ bars
     exist since 00:00, it is flat with no working entry, and fewer than 3 entries filled in this session.
  6. STOP: the lowest low (a long) / highest high (a short) of the last 3 bars, distance x 1 from the close, never under
     0.25 x ATR(14) of the day's 5-minute bars (the mean of the true ranges up to 14 bars, then Wilder) nor under 2 ticks.
     TARGET: 1.5 x that distance. Both re-priced to the fill (move_brackets_to_fill).
  7. HELD to the stop / target, or flattened at 15:58 (13:13 on an equity half day): not at the session end.

WHERE IT DIFFERS FROM THE ENGINE, AND WHY:
  * RVOL's 14 days come from the Desk's feed (ctx.minute_volume) instead of the engine's minute-volume cache / research tape: a
    Lab strategy cannot read the research files. The feed gives the same numbers (every print of each prior date's own tape);
    a date whose stored tape differs from the research archive gives a different median. No feed, or an entry that is not 1380
    numbers, counts as no tape: fewer than 10 dates = no RVOL = no trade (fail closed; the engine would have traded).
  * Flat time: a strategy booked on accounts is flattened by the Desk at 15:55 at the latest (labcfg.FLAT_LATEST), so a trade
    still open then closes 3 minutes before the engine's. In shadow (no accounts) and in the Lab tester it is the engine's 15:58.
  * Half days: the engine's calendar (l2sim.EARLY_CLOSES) is copied below; its July list ends in 2026
    (shortcut: a July half day after 2026 is not known, add it to _JULY_HALF when the exchange lists it).
  * The session is read from the clock, not from the engine's on_time start / end flags. Same entries: the one bar the flags
    treat differently (a bucket closed late after the session end) is refused by the 5-minute cut in both.
  * Not copied, because this box never uses them: the cancel of resting entries 5 minutes before the session end / the flat
    time (the only entry is a market order, nothing rests), trail and bar exits, the book exits, every filter block, the side
    rule and the session VWAP (side off).
  * Fills and costs are the Lab tester's (the engine is its port: $4.00 a round turn, 1 tick slip on market / stop fills, 85 ms
    placement, the stop live from the print after the entry print); on the Desk the broker's, in shadow the paper fills. Which
    days run is the tester's coverage rule over 00:00-16:00 (the engine's over 00:00-16:10).
  * Size: 1 contract in the tester (the engine's qty 1); on the Desk the size set on the account.
Draws: EMA 13, the slow VWAP, and a mark at each in-session cross that RVOL turned down."""
from __future__ import annotations

import datetime as dt
import statistics
from zoneinfo import ZoneInfo

from homebase.strategies.base import Strategy

SESSION = "mid"                     # this file's NY instance: nyam | mid | pm (the line that differs between the three files)

ET = ZoneInfo("America/New_York")
NS = 1_000_000_000
SESS = {"asia": (0, 10800), "london": (10800, 30300), "nyam": (34200, 39600),
        "mid": (39600, 48600), "pm": (48600, 57480)}     # l2sim.SESS, seconds after 00:00 ET (the tag order of the 1-minute bars)
VWAP_RESTART = ("asia", "london", "nyam")                # Template.on_bar: the rth VWAP restarts when the minutes enter these
TF = 5                                                   # the bar, minutes
FAST_N, RVOL_M, SWING = 13, 1.5, 3                       # the spec's fixed settings + the box's fast_n
STOP_X, TGT_R = 1.0, 1.5                                 # the box own1-r1p5: stop_mode own x 1, target 1.5 R
MAX_TR, WARM = 3, 3                                      # spec limits.max_tr; Template.WARM
DAY_FLAT, HALF_FLAT = 57480, 47580                       # 15:58 / 13:13 ET (l2sim.day_flat)
VOL_DAYS, VOL_MIN = 14, 10                               # avwap.vol_ref
MIN0, NMIN = -360, 1380                                  # blocks.MIN0 / NMIN: index 0 = 18:00 ET the evening before
_JULY_HALF = {2021: dt.date(2021, 7, 2), 2023: dt.date(2023, 7, 3), 2024: dt.date(2024, 7, 3),
              2025: dt.date(2025, 7, 3), 2026: dt.date(2026, 7, 3)}


def half_day(d: dt.date) -> bool:
    """A CME equity half day (l2sim._early_closes): Thanksgiving Friday, a weekday Christmas Eve, the July list."""
    nov1 = dt.date(d.year, 11, 1)
    return (d == nov1 + dt.timedelta(days=(3 - nov1.weekday()) % 7 + 22)
            or (d.month == 12 and d.day == 24 and d.weekday() < 5) or d == _JULY_HALF.get(d.year))


def _sid(s: int):
    for k, (a, b) in SESS.items():
        if a <= s < b:
            return k
    return None


class NqVhEmaVwap(Strategy):
    id = "draft_nq_vh_emavwap_mid"
    name = "NQ EMA13 x 09:30 VWAP, RVOL 1.5, 5m - NY MID (hunt vh_i16)"
    root = "NQ"
    own_stop = True                  # it passes its own sl
    session_window = ("00:00", "16:00")
    bar_minutes = 1
    session_independent = True
    max_trades_day = 3               # the engine's max_tr: 3 entries in this instance's session

    def needs_minute_volume(self):
        return VOL_DAYS

    def times(self):
        return ["13:13", "15:58"]    # the day's flat time: 13:13 on a half day, else 15:58

    def on_session(self, ctx):
        d = ctx.date
        self.t0 = int(dt.datetime(d.year, d.month, d.day, tzinfo=ET).timestamp()) * NS
        self.flat_s = HALF_FLAT if half_day(d) else DAY_FLAT
        self.step = TF * 60 * NS
        self.cur = None                          # the 5-minute bar being built: [k, h, l, c, v]
        self.H, self.L, self.C, self.V = [], [], [], []
        self.atr, self.tr_sum = None, 0.0        # tr_sum: added left to right as the engine's sum() on its Python 3.9
        self.last_s = None                       # start second (after 00:00) of the newest 1-minute bar: Template.M[-1][0]
        self.vsid, self.vr = None, [0.0, 0.0]    # the rth VWAP: volume, volume x typical price
        self.ef, self.pd = None, 0               # the EMA; the sign of fast - slow at the last close where both were apart
        self.order, self.n_ent = None, 0
        self.vols = [e["vol"] for e in (getattr(ctx, "minute_volume", None) or [])[-VOL_DAYS:]
                     if isinstance(e, dict) and isinstance(e.get("vol"), list) and len(e["vol"]) == NMIN]

    def on_bar(self, ctx, bar):
        k = bar.start_ns // self.step
        if self.cur is not None and self.cur[0] != k:
            self._close(ctx)                     # the bucket's last minute had no print: it closes now
        s = (bar.start_ns - self.t0) // NS
        self.last_s = s
        sid = _sid(s)
        if sid != self.vsid:
            self.vsid = sid
            if sid in VWAP_RESTART:
                self.vr = [0.0, 0.0]
        if sid and bar.v > 0:
            tp = (bar.h + bar.l + bar.c) / 3.0
            self.vr[0] += bar.v
            self.vr[1] += bar.v * tp
        cur = self.cur
        if cur is None:
            self.cur = [k, bar.h, bar.l, bar.c, bar.v]
        else:
            cur[1], cur[2], cur[3] = max(cur[1], bar.h), min(cur[2], bar.l), bar.c
            cur[4] += bar.v
        if bar.end_ns % self.step == 0:
            self._close(ctx)

    def _close(self, ctx):
        """One 5-minute close: Template._close, MaX.fam_update, then can_enter and fam_signal."""
        k, h, l, c, v = self.cur
        self.cur = None
        end = ((k + 1) * self.step - self.t0) // NS             # nominal close, seconds after 00:00
        n = len(self.C)
        tr = h - l if n == 0 else max(h - l, abs(h - self.C[-1]), abs(l - self.C[-1]))
        self.H.append(h)
        self.L.append(l)
        self.C.append(c)
        self.V.append(v)
        n += 1
        self.tr_sum += tr
        self.atr = self.tr_sum / n if n <= 14 else (self.atr * 13.0 + tr) / 14.0
        self.ef = c if self.ef is None else self.ef + 2.0 / (FAST_N + 1) * (c - self.ef)
        f = self.ef if n >= FAST_N else None
        slow = self.vr[1] / self.vr[0] if self.vr[0] > 0 else None
        t_ns = (k + 1) * self.step
        if f is not None:
            ctx.plot("EMA 13", t_ns, f)
        if slow is not None:
            ctx.plot("VWAP 09:30 (03:00 / 00:00 before)", t_ns, slow)
        if f is None or slow is None or f == slow:
            return
        d = 1 if f > slow else -1
        cross = self.pd != 0 and d != self.pd
        self.pd = d
        if self.order is not None:               # Template._sync: a filled entry counts once
            if self.order.status == "filled":
                self.n_ent += 1
            if self.order.status != "working":
                self.order = None
        a, b = SESS[SESSION]
        if not (cross and a < end <= b):
            return
        cut = min(b, self.flat_s) - 300          # no entry in the last 5 minutes of the session / before the flat time
        if n < WARM or not ctx.flat or self.order is not None or self.n_ent >= MAX_TR or ctx.now_ns - self.t0 >= cut * NS:
            return
        r = self._rvol()
        if r is None or r < RVOL_M:
            ctx.mark("RVOL too low", t_ns, c, "rv %.2f" % r if r is not None else "rv none", "long" if d > 0 else "short")
            return
        ref = c
        struct = min(self.L[-SWING:]) if d > 0 else max(self.H[-SWING:])
        dist = max(max(abs(ref - struct) * STOP_X, 0.25 * self.atr), 2 * ctx.tick)
        ctx.move_brackets_to_fill = True
        self.order = ctx.market("long" if d > 0 else "short", sl=ref - d * dist, tp=ref + d * TGT_R * dist, ref=ref)

    def _rvol(self):
        """This bar's volume / the median volume of its clock window on the prior dates (avwap.vol_ref, xflow._Rvol.rvol)."""
        b = (self.last_s // (TF * 60) + 1) * TF * 60
        i, j = (b - TF * 60) // 60 - MIN0, b // 60 - MIN0
        if not 0 <= i < j <= NMIN:
            return None
        ref = [float(sum(vol[i:j])) for vol in self.vols]
        if len(ref) < VOL_MIN:
            return None
        med = statistics.median(ref)
        return self.V[-1] / med if med > 0 else None

    def on_time(self, ctx, et_time):
        h, m = et_time.split(":")
        if int(h) * 3600 + int(m) * 60 == self.flat_s:
            ctx.flatten("time")

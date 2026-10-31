"""NQ VWAP TOUCH WITH TWO ANCHORS (09:30 VWAP + Globex VWAP), one NY session, 1 NQ contract, for the Desk in SHADOW (paper only).

The Lab copy of the stack-B rule B-1 (PREREG_HM40.md Amendment L; STACKB_DRAFT.md section 3): vh_i11_touch_gx_5_ny-NQ-tf5, box
away160_pts60-r2 (spec research/edge-library/out/vwap_hunt_2026-10-20/hm40/specs/vh_i11_touch_gx_5_ny.json; store
research/edge-library/runs_wf/vh_i11_touch_gx_5_ny-NQ-tf5). Engine family `avwap_touch` (research/edge-library/engine/families/
avwap.py AvwapTouch on the _Touch / _Lines classes, run as families/blocks.py B_avwap_touch with every block off): line rth, also
globex, away 160 ticks, near 3 ticks, max_tr 3, dir both, 5-minute bars, stop_mode pts 60, tgt_r 2, hold_to day, run inside the
engine's Template (engine/l2sim.py) with strict_limit (SCREEN_RUN). The engine runs nyam, mid and pm as three INDEPENDENT instances
(run_idea.cell_specs): this file is one of three Lab drafts (nq_sb_touchgx_nyam / _mid / _pm), the same code with only SESSION
(and the id / display name) apart.

THE RULE, as the engine runs it (ET; the trade date's own bars from 00:00, plus the evening before for the Globex line):
  * THE LINE (rth): volume-weighted (h + l + c) / 3 of the 1-minute bars that START at or after 09:30, a minute added when it has
    ended (avwap.Line "rth").
  * THE SECOND LINE (also = globex): the same sum over every 1-minute bar from 18:00 ET of the calendar day before the trade date
    (the Globex day's open) to the last minute that has ended (avwap.Line "globex": the evening's minutes read from the session tape,
    then every minute from 00:00).
  * ARM: a 1-minute close >= 40 points (160 ticks) above the 09:30 VWAP (as of that minute's end) arms a LONG, <= 40 below a SHORT;
    the newest such close sets the side. The arm lives all day (it is not reset at a session start).
  * TOUCH: a 1-minute bar whose range comes within 0.75 points (3 ticks) of the 09:30 VWAP as it stood BEFORE that minute uses the
    arm up, filled or not; a resting order is cancelled at that minute's close. Only a new 40-point close arms it again.
  * ORDER: at each 5-minute close inside the session (the bar's clock end after the session start and by its end), while flat,
    with fewer than 3 fills this session, at least 3 five-minute bars since 00:00, and before the session end - 5 min (and the
    day's flatten - 5 min): the working order is cancelled; then, with an arm set, the 5-minute CLOSE on the trade's side of the
    Globex VWAP (above it for a long, below for a short; no Globex line = no order) and the last print on the passive side of the
    09:30 VWAP, a LIMIT at the 09:30 VWAP is placed. It fills only on a print 1 tick through it, at its price. A resting order
    is also cancelled at the session end - 5 min and at the session end.
  * EXITS: stop 60 points, target 120 points (2R) from the order price, moved to the fill. Held to stop / target or flattened
    at 15:58 ET (13:13 on a CME equity half day) -- NOT at the session end. One position at a time.
  Draws the 09:30 VWAP and the Globex VWAP at each 5-minute close.

DIFFERENCES FROM THE ENGINE, and why:
  1. The window starts the evening before: ("-18:00", "16:00"). The Lab hands a draft the evening's minutes only through such a
     window, and the Globex line needs them. Consequences: (a) on the Desk it is SHADOW ONLY (labcfg.evening / SAY_EVENING: never
     booked on an account), which is what stack B asks for; (b) the tester's coverage rule also checks the evening hours, so a
     trade date with an empty evening clock hour is skipped here while the engine (day window 00:00-16:10) trades it -- see
     CHECKED for how often that happened on the in-sample days. (A bar_window reaching back to 18:00 is no way around it:
     the tester builds a draft's bars from its session window's prints only, backtest/engine.run_session.) Evening minutes
     feed the Globex line only: the 5-minute bars,
     the bar count (WARM), the arm, the touch and the 09:30 VWAP start at 00:00 as in the engine.
  2. Flat time. The engine flattens at 15:58 (13:13 on a half day); so does this code, in the tester and in SHADOW (the shadow
     host runs the strategy's own times). The half-day calendar is the engine's EARLY_CLOSES rule (Thanksgiving Friday, Dec 24 on
     a weekday, the July table) copied here; the July table ends 2026 as the engine's does.
  3. Stop arming. The engine ran with strict_limit = True (a limit entry's stop is live ON its fill print); the tester and the
     shadow host arm it one print later (their fill law; a draft cannot change it). With a 60-point stop a single print
     through both the limit and the stop does not happen in practice.
  4. Brackets: ctx.move_brackets_to_fill = True (as the ports). The engine's _lim does not set it, but a limit fills AT its price
     there and in the tester, so it changes nothing; a real fill with price improvement keeps 60 / 120 points from the fill.
  5. The day window ends 16:00 (the engine's Template: 16:10): nothing happens after 15:58.
  6. No daily bars asked for (the engine's Template reads them for prior-day levels and rolls, which line rth / globex never use).
  7. Sums: the engine adds the evening's minutes in one numpy sum, this code one minute at a time: the Globex VWAP can differ in
     the last float digit, which only matters for a 5-minute close exactly on the line.
  8. Live (Desk shadow): today's prints are the live feed, not the archive; late prints can move the volume a little, so either
     VWAP can sit a tick apart from the backtest's on some days.
  9. Unchanged: costs are the run's (engine: $4.00 round turn, 1 tick slip on stops / flatten, as the tester's defaults),
     placement latency 85 ms, 1 contract, the late close of a 5-minute bar whose last minute had no print (closed at the next
     minute's bar, as the Template does).
CHECKED 2026-10-21 (the tester's runner.prepare / execute in-process, the real TapeStore, on the store's 883 in-sample days, vs
library.unit_cell of box away160_pts60-r2 per session; harness: the session scratchpad's touchgx/parity.py): on every day BOTH
ran, the three files equal the engine's three instances trade for trade (entry minute and side, exit time and reason, stop,
net): nyam 529 of 529 (net +$75,289), mid 408 of 408 (+$44,933), pm 306 of 306 (+$27,261) = 1,243 of the engine's 1,245
trades. The 2 missing trades are both on 2022-10-11: the tester skipped that date (no print 21:00-22:00 ET on the Columbus
Day evening) under the evening window's coverage rule; the engine (day window) ran it and took nyam short 10:33 (stop,
-$1,209) and pm long 14:45 (stop, -$1,209); mid had none there. Both sides ran the same 875 other days (the engine's 7 skips
are the tester's too). Engine nets: nyam +$74,080, mid +$44,933, pm +$26,052.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from homebase.strategies.base import Strategy

SESSION = "mid"                     # the one session of this instance: nyam | mid | pm
SESS = {"nyam": (34200, 39600), "mid": (39600, 48600), "pm": (48600, 57480)}     # seconds after 00:00 ET (l2sim.SESS)

ET = ZoneInfo("America/New_York")
NS = 1_000_000_000
TF = 5 * 60 * NS                    # 5-minute bars on the ET clock
OPEN = 34200                        # the "rth" line starts at 09:30
AWAY, NEAR = 160, 3                 # ticks
STOP_PTS, TGT_R = 60.0, 2.0         # box away160_pts60-r2
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


class NqVwapTouchGlobex(Strategy):
    id = "draft_nq_sb_touchgx_mid"
    name = "NQ VWAP touch + Globex VWAP side, NY midday, 60 pt stop 2R (stack B, shadow)"
    root = "NQ"
    session_window = ("-18:00", "16:00")
    bar_minutes = 1
    session_independent = True
    max_trades_day = 3

    def times(self):
        a, b = SESS[SESSION]
        return sorted({_hms(a), _hms(b - 300), _hms(b), _hms(HALF_FLAT - 300), _hms(HALF_FLAT), _hms(DAY_FLAT - 300), _hms(DAY_FLAT)})

    def on_session(self, ctx):
        d = ctx.date
        self.t0 = int(dt.datetime(d.year, d.month, d.day, tzinfo=ET).timestamp()) * NS      # 00:00 ET of the trade date
        self.flat_s = HALF_FLAT if _half_day(d) else DAY_FLAT
        self.cur = None                         # the 5-minute bar being built: [k, h, l, c]
        self.nb = 0                             # 5-minute bars closed since 00:00
        self.vv = self.vp = 0.0                 # 09:30 VWAP sums
        self.gv = self.gp = 0.0                 # Globex VWAP sums from 18:00 the evening before
        self.arm = 0                            # +1 long (price came from above), -1 short, 0 none
        self.on = self.over = False             # inside the session / the session (or the day) is over
        self.n_ent = 0
        self.order = None
        ctx.move_brackets_to_fill = True

    def _vwap(self):
        return self.vp / self.vv if self.vv > 0 else None

    def _gvwap(self):
        return self.gp / self.gv if self.gv > 0 else None

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

    def _minute(self, ctx, bar):
        """AvwapTouch._read for one ended minute: the touch (against the 09:30 VWAP before it), both lines, then the arm."""
        if bar.v > 0:                           # Line "globex": every minute since 18:00 the evening before
            self.gv += bar.v
            self.gp += bar.v * (bar.h + bar.l + bar.c) / 3.0
        if (bar.start_ns - self.t0) // NS < OPEN:
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
        """Template._close of a 5-minute bar, then can_enter and _Touch.fam_signal (the Globex side in agrees)."""
        k, h, l, c = self.cur
        self.cur = None
        t_end = (k + 1) * TF
        self.nb += 1
        w, g = self._vwap(), self._gvwap()
        if w is not None:
            ctx.plot("VWAP 09:30", t_end, w)
        if g is not None:
            ctx.plot("VWAP Globex 18:00", t_end, g)
        self._sync()
        a, b = SESS[SESSION]
        end = (t_end - self.t0) // NS           # the nominal close: a late close never counts as later
        if not (self.on and a < end <= b) or self.nb < WARM or not ctx.flat or self.n_ent >= MAX_TR \
                or ctx.now_ns - self.t0 >= (min(b, self.flat_s) - 300) * NS:
            return
        self._drop(ctx)                         # re-priced at this close, or dropped when the arm or the side is gone
        if w is None or not self.arm:
            return
        sd = self.arm
        if g is None or (c - g) * sd <= 0:
            return                              # the 5-minute close must be on the trade's side of the Globex VWAP
        lp = ctx.last_price
        if lp is None or (lp - w) * sd <= 0:
            return                              # only on the passive side of the last print
        self.order = ctx.limit_entry("long" if sd > 0 else "short", w,
                                     sl=w - sd * STOP_PTS, tp=w + sd * TGT_R * STOP_PTS)

    def on_bar(self, ctx, bar):
        if bar.start_ns < self.t0:
            self._minute(ctx, bar)              # the evening before: the Globex line only
            return
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
        a, b = SESS[SESSION]
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

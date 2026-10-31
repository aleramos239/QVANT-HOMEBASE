"""NQ VWAP-TOUCH MOMENTUM 5m, New York 09:35-15:00 (stack B, shadow): a 5-minute two-bar displacement (bar 2's body bigger than
bar 1's, the two bars opposite colours) whose bar 1 touched the session VWAP, closing on the trade's side of the VWAP, with the
VWAP higher (long) / lower (short) than 60 minutes before -> market with bar 2, stop 60 points, target 2R, flat 15:58.

THE LAB COPY of vh_i1_pb_5_ny-NQ-tf5, box vwap_slope60_pts60-r2 (stack B rule B-2 of research/edge-library/out/
vwap_hunt_2026-10-20/hm40/STACKB_DRAFT.md; spec .../hm40/specs/vh_i1_pb_5_ny.json): engine family `jj_fair`
(research/edge-library/engine/families/jj_fair.py, frozen copy .../hm40/frozen/jj_fair.py, sha256 04addad4...; on fvg_odir.FvgOdir,
on l2sim.Template), run as families/blocks.py B_jj_fair with the open layer off; tf 5, entry mom, fair vwap, min_room 0, opp on,
wick off, pullback on (near 0), vwap_slope 60, start 09:35, end 15:00, max_loss 99, cont off, max_tr 20, dir both, hold_to day,
stop_mode pts 60, tgt_r 2.0, every block off. jj_fair runs ONE instance only: the nyam pass, stretched by the family to
09:30-15:58 (FvgOdir.fam_sessions "t"; mid / pm trade nothing, fam_filter), so this is the only file. The store tags its trades
nyam / mid / pm by entry clock; they are all this one pass.

THE RULE, as the engine runs it (New York times; the trade date's own 1-minute bars from 00:00):
  1. Bars: 5-minute bars on the ET clock. A bucket whose last minute had no print closes when the next bucket's first minute
     arrives (Template.on_bar), before that minute counts.
  2. The VWAP (Template.vwr, the "rth anchor"): volume-weighted typical price (h + l + c) / 3 of the 1-minute bars, restarted
     at 00:00 (asia), 03:00 (london) and 09:30 (nyam) and NOT at 11:00 / 13:30, so from 09:30 on it is the day's VWAP since
     09:30. A minute counts only inside a tester session (asia 00:00-03:00, london 03:00-08:25, nyam/mid/pm 09:30-15:58) and
     with volume: 08:25-09:30 adds nothing and leaves the London VWAP standing.
  3. The VWAP 60 minutes ago: the VWAP as it stood after the newest minute that ENDED at or before (close - 60 min). Up to the
     10:30 close that is the London VWAP (03:00-08:25), from the 10:35 close the day's VWAP since 09:30 (the engine's vhist).
  4. At each 5-minute close whose clock end is after 09:35 and at or before 15:00 (bar 1 = the bar before, bar 2 = this one):
     |close2 - open2| > |close1 - open1| AND
       LONG:  close2 > VWAP, bar 2 green (close > open), bar 1 red (close < open), VWAP now > VWAP 60 minutes ago;
       SHORT: close2 < VWAP, bar 2 red, bar 1 green, VWAP now < VWAP 60 minutes ago;
     AND bar 1's low <= VWAP now <= bar 1's high (pullback on, near 0). The wick test is off; min_room 0 never blocks.
  5. Entry: a market order at that close, when 3+ bars since 00:00, flat, nothing working, fewer than 20 filled entries today
     and the clock before 15:53 (13:08 on a half day: Template.can_enter). Stop 60 points, target 120, both from the close and
     moved to the fill (Template._mkt, move_brackets_to_fill). Every signal after a trade has closed is the next entry.
  6. Held to the stop or target; flat at 15:58 (13:13 on a CME equity half day: l2sim.day_flat).

WHERE IT DIFFERS FROM THE ENGINE, AND WHY:
  * Flat at 15:58 like the engine, in the tester AND in shadow (a shadow day runs the strategy's own times). Only if ever BOOKED
    on an account does the Desk cap it at 15:55 (labcfg.FLAT_LATEST): a trade still open 15:55-15:58 would then close up to 3
    minutes earlier. The half-day calendar is l2sim.EARLY_CLOSES (Thanksgiving Friday, Dec 24 on a weekday, the July table to
    2026), copied here so the file stays stdlib only.
  * Today's prints are the tester's tape (print-identical to the engine's) or, on the Desk, the live prints: live volume can
    differ from the archive's (late prints), so the VWAP, a close within a tick of it, a bar 1 that just touches it, or a VWAP
    that barely moved in the hour can read the other way live.
  * The day window here is 00:00-16:00 (the engine replays to 16:10): nothing is decided after 15:00.
  * Not copied because this box never uses them: the fair price open / adapt / pre, the room and 80 % rule (min_room 0), the
    displacement-toward-fair, break-of-structure and swing reads (entry mom), the wick test (off), the opening continuation
    (cont off), the hours / start choices (all / 09:35), min_body / vwap_dir (off), the stop for the day after max_loss losses in
    a row (99: never reached with at most 20 entries), the session object of the Template (a close before 09:35 or after 15:00,
    or after the 13:13 half-day flatten, cannot enter here either), the cancel of a working entry at 15:53 (a market entry
    fills at the next print), the VWAP sigma, prior-day levels and rolls, every filter block and the open layer (off).
  * Fills and costs are the tester's (l2sim is its port: $4.00 a round turn, 1 tick slip on market / stop fills) or the Desk's
    shadow fills; 1 contract of NQ (size set on the Desk). A market entry only: nothing rests, no evening window.
Draws the VWAP and the VWAP of 60 minutes ago at each 5-minute close of the pass.

  * Worth knowing (the engine's own behaviour, copied as is): at the closes up to 10:30 the "VWAP 60 minutes ago" is the London
    VWAP (rule 3), not a 09:30 VWAP; 468 of the 893 in-sample entries (+$52,713 of +$83,978) are of that kind.

CHECKED 2026-10-21: this file run in-process through homebase/backtest/runner.py (prepare / execute, the real TapeStore, the class
registered in strategies.REGISTRY) on the store's 42 in-sample months only (883 days, the same 7 days skipped by both: 2021-12-01,
2022-06-21, 2022-08-05, 2023-04-07, 2025-07-04, 2025-11-28, 2026-04-03) equals the store's box vwap_slope60_pts60-r2
(library.load_unit of runs_wf/vh_i1_pb_5_ny-NQ-tf5/is, unit_cell, every sess code: the store tags them nyam 552 / mid 239 / pm
102 by entry clock, +$46,712 / +$53,859 / -$16,593, all of them this one pass) trade for trade (date, entry time to the ms, side,
duration, exit reason, stop distance, net): 893 / 893, +$83,978 both (exits: 480 stop, 244 target, 169 at the flatten; 470 long /
423 short; entries 09:45 .. 15:00, at most 5 a day; 6 trades on half days, flat 13:13 in both). The half-day calendar here equals
l2sim.EARLY_CLOSES for 2017-2026. The engine file read is the frozen jj_fair.py (sha256 04addad4..., the store's code stamp).
Exact on the first round: nothing was changed to reach it.
"""
from __future__ import annotations

import bisect
import datetime as dt
from zoneinfo import ZoneInfo

from homebase.strategies.base import Strategy

SESSION = "nyam"                                   # the one pass of this instance (jj_fair: nyam stretched to 09:30-15:58)
PASS = (34200, 57480)                              # 09:30 .. 15:58 ET, seconds after 00:00 (FvgOdir.fam_sessions "t")
ET = ZoneInfo("America/New_York")
NS = 1_000_000_000
TF = 5                                             # minutes
STEP = TF * 60 * NS
REV0, LAST = 34500, 54000                          # signals at closes after 09:35 and at or before 15:00 (start 09:35, end 15:00)
SLOPE_S = 60 * 60                                  # vwap_slope 60 minutes
STOP_PTS, TGT_R, MAX_TR, WARM = 60.0, 2.0, 20, 3   # box vwap_slope60_pts60-r2; the spec's max_tr; Template.WARM
DAY_FLAT_S, HALF_FLAT_S = 57480, 47580             # 15:58 / 13:13 (l2sim.day_flat), for the entry cut
FLAT, HALF_FLAT = "15:58", "13:13"
VW_SESS = (("asia", 0, 10800), ("london", 10800, 30300), ("nyam", 34200, 39600), ("mid", 39600, 48600), ("pm", 48600, 57480))
VW_RESET = ("asia", "london", "nyam")              # l2sim.Template.on_bar: the rth anchor restarts here only
_JULY_HALF = {2021: (7, 2), 2023: (7, 3), 2024: (7, 3), 2025: (7, 3), 2026: (7, 3)}   # l2sim._JULY_HALF


def _half_day(d: dt.date) -> bool:
    """l2sim.EARLY_CLOSES: the day after Thanksgiving, Dec 24 on a weekday, the July half day of the table."""
    nov1 = dt.date(d.year, 11, 1)
    return (d == nov1 + dt.timedelta(days=(3 - nov1.weekday()) % 7 + 22)
            or (d.month, d.day) == (12, 24) and d.weekday() < 5 or _JULY_HALF.get(d.year) == (d.month, d.day))


def _vsid(s: int):
    """The tester session a 1-minute bar starting s seconds after 00:00 ET belongs to (l2sim._sid_at, ORDER), or None."""
    for k, a, b in VW_SESS:
        if a <= s < b:
            return k
    return None


class NqVwapPullbackMom5(Strategy):
    id = "draft_nq_sb_pb5_nyam"
    name = "NQ VWAP-touch momentum 5m, NY 09:35-15:00 (stack B, shadow)"
    root = "NQ"
    session_window = ("00:00", "16:00")
    bar_minutes = 1
    session_independent = True
    max_trades_day = 20                            # = MAX_TR (a literal: the catalog reads drafts without running them)

    def times(self):
        return [HALF_FLAT, FLAT]

    def on_session(self, ctx):
        d = ctx.date
        self.t0 = int(dt.datetime(d.year, d.month, d.day, tzinfo=ET).timestamp()) * NS      # 00:00 ET of the trade date
        self.half = _half_day(d)
        self.cut = min(PASS[1], HALF_FLAT_S if self.half else DAY_FLAT_S) - 300             # no entry from here (seconds)
        self.cur = None                            # the 5-minute bar being built: [k, o, h, l, c]
        self.bars = []                             # closed 5-minute bars since 00:00: (o, h, l, c)
        self.vr, self.vsid = [0.0, 0.0], None      # VWAP sums (volume, volume x typical) and the session they belong to
        self.vt, self.vv = [], []                  # the VWAP after each 1-minute bar: its end (seconds), its value
        self.order, self.n_ent = None, 0

    def _vwap(self):
        a = self.vr
        return a[1] / a[0] if a[0] > 0 else None

    def on_bar(self, ctx, bar):
        k = bar.start_ns // STEP
        if self.cur is not None and self.cur[0] != k:
            self._close(ctx)                       # the bucket's last minute had no print: it closes now, before this minute counts
        s = (bar.start_ns - self.t0) // NS
        sid = _vsid(s)
        if sid != self.vsid:
            self.vsid = sid
            if sid in VW_RESET:
                self.vr = [0.0, 0.0]
        if sid and bar.v > 0:
            v, tp = bar.v, (bar.h + bar.l + bar.c) / 3.0
            self.vr[0] += v
            self.vr[1] += v * tp
        c = self.cur
        if c is None:
            self.cur = [k, bar.o, bar.h, bar.l, bar.c]
        else:
            c[2], c[3], c[4] = max(c[2], bar.h), min(c[3], bar.l), bar.c
        if bar.end_ns % STEP == 0:
            self._close(ctx)
        w = self._vwap()
        if w is not None:                          # after the close, as jj_fair's on_bar (vhist): the close reads older minutes only
            self.vt.append(s + 60)
            self.vv.append(w)

    def _close(self, ctx):
        k, o, h, l, c = self.cur
        self.cur = None
        self.bars.append((o, h, l, c))
        od = self.order
        if od is not None and od.status != "working":
            self.n_ent += od.status == "filled"
            self.order = None
        end = ((k + 1) * STEP - self.t0) // NS     # the bar's clock end, seconds after 00:00 ET
        if not PASS[0] < end <= PASS[1]:
            return
        w = self._vwap()
        i = bisect.bisect_right(self.vt, end - SLOPE_S)
        back = self.vv[i - 1] if i else None
        t = (k + 1) * STEP
        if w is not None:
            ctx.plot("VWAP", t, w)
        if back is not None:
            ctx.plot("VWAP 60 min ago", t, back)
        if end <= REV0 or end > LAST or len(self.bars) < 2 or w is None or back is None:
            return
        o1, h1, l1, c1 = self.bars[-2]
        if not abs(c - o) > abs(c1 - o1) or not l1 <= w <= h1:
            return                                 # bar 2 must out-size bar 1, and bar 1 must have touched the VWAP
        if c > w and c > o and c1 < o1 and w > back:
            side = "long"
        elif c < w and c < o and c1 > o1 and w < back:
            side = "short"
        else:
            return
        if (self.order is not None or not ctx.flat or self.n_ent >= MAX_TR or len(self.bars) < WARM
                or ctx.now_ns - self.t0 >= self.cut * NS):
            return
        sd = 1 if side == "long" else -1
        d = max(STOP_PTS, 2 * ctx.tick)
        ctx.move_brackets_to_fill = True
        self.order = ctx.market(side, sl=c - sd * d, tp=c + sd * TGT_R * d, ref=c)

    def on_time(self, ctx, et_time):
        if et_time == FLAT or (et_time == HALF_FLAT and self.half):
            ctx.flatten("time")

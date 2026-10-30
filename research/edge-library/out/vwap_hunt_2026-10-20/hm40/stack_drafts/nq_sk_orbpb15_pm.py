"""NQ ORB VWAP PULLBACK 15m, one NY session (stack, shadow): once a 15-minute close breaks the 09:30-09:45 range, a LIMIT at the
09:30 VWAP the way of the break, for the first pullback to it; stop 60 NQ points, target 2R. One arm a day, one trade a session.

THE LAB COPY of the stack rule vh_i12_orbpb_15_ny-NQ-tf15, box or_min15_pts60-r2 (stack #5 of research/edge-library/out/
vwap_hunt_2026-10-20/hm40/STACK.md; engine family `orb_vwap_pb`: research/edge-library/engine/families/avwap.py OrbVwapPb, run as
families/blocks.py B_orb_vwap_pb with every block off and no gate, on l2sim.Template; spec .../hm40/specs/
vh_i12_orbpb_15_ny.json: or_min 15, near 0, max_tr 1, dir both, tf 15, hold_to day, stop_mode pts 60, tgt_r 2, run with
strict_limit = True). The engine runs nyam / mid / pm as three INDEPENDENT instances (run_idea.cell_specs); this file is the one
for SESSION below. nq_sk_orbpb15_nyam / _mid / _pm are the same code but for SESSION, `id` and `name`.

THE RULE, as the engine runs it (New York times; the trade date's own bars from 00:00):
  1. Bars: 1-minute bars summed into 15-minute bars on the clock. A 15-minute bar whose last minute had no print closes when the
     next bucket's first minute arrives (the engine does the same).
  2. The range: high / low of the 1-minute bars that start 09:30 .. 09:44.
  3. The VWAP: volume-weighted (h + l + c) / 3 of the 1-minute bars that start at or after 09:30, a minute added when it has ended
     (avwap.Line "rth").
  4. The arm (every 15-minute close of the day, in or out of the session): the first close whose clock end is after 09:45 and
     that is above the range high arms a LONG, below the range low a SHORT. Only once a day.
  5. The touch: the first 1-minute bar after the arm whose range reaches the VWAP as it stood BEFORE that minute (near 0) uses
     the arm up, filled or not; a working order is cancelled at that minute's close. No second arm that day. All three instances
     see the same arm and touch: so the mid / pm copies only ever trade a break whose first pullback has not come by their start.
  6. The order: at each 15-minute close inside the session (clock end after the session start and at or before its end), flat,
     no fill yet this session (max_tr 1), at least 3 bars since 00:00, before the session end - 5 min (and the day's flatten
     - 5 min): the working order is cancelled; then, with the arm set, a LIMIT at the VWAP if the last print is on the passive side
     of it (above for a long). It fills only on a print 1 tick through it, at its price. Working orders are also cancelled at the
     session end - 5 min and at the session end.
  7. Exits: stop 60 points, target 120 points (2R) from the order price, moved to the fill. Held to stop / target past the
     session end; flattened at 15:58 ET (13:13 on a CME half day: l2sim.day_flat).
  Draws the VWAP and the range high / low.

WHERE IT DIFFERS FROM THE ENGINE, AND WHY:
  * Flat at 15:58 like the engine, in the tester AND in shadow (a shadow day runs the strategy's own times). Only if ever BOOKED
    on an account does the Desk cap it at 15:55 (labcfg.FLAT_LATEST): a trade still open 15:55-15:58 would then close up to 3
    minutes earlier. Entries keep the engine's cut (none at or after the session end - 5 min / 15:53 / 13:08 on a half day). On a
    CME half day (homebase.backtest.tape.early_close_et, the same calendar as l2sim.EARLY_CLOSES) it is flat at 13:13; pm never
    trades then.
  * Stop arming: the engine ran with strict_limit = True (a limit entry's stop is live ON its fill print); the tester and the shadow
    host arm it one print later (their fill law; a draft cannot change it). With a 60-point stop one print through both the limit
    and the stop does not happen in practice.
  * ctx.move_brackets_to_fill = True (as the ports); the engine's _lim does not set it, but a limit fills AT its price in both.
  * A LIMIT entry: on the Desk this runs in SHADOW only (paper fills).
  * Today's prints are the tester's tape (print-identical to the engine's) or, on the Desk, the live prints: live volume can differ
    from the archive's (late prints), so the VWAP can sit a tick apart live.
  * The day window here is 00:00-16:00 (the engine replays to 16:10): nothing is decided after 15:53 in either.
  * Not copied because this box never uses them: trail / exit-bars exits (0), every filter block (off), the gate (off), `also`
    (off), the ATR (pts stop; the engine only needs it to exist, from the first bar on), prior-day levels and rolls.
  * Fills and costs are the tester's (l2sim is its port) or the Desk's shadow fills; 1 contract of NQ (size set on the Desk).

CHECKED 2026-10-21: the three files in the tester's engine (homebase/backtest/runner.execute in-process, the real TapeStore over
~/futures_derived) equal the engine's three instances of the box (library.load_unit('is', the store) / unit_cell) trade for trade
(day, entry minute, side, stop distance 60, exit reason, exit time to the second, net) on ALL 42 in-sample months of the box's
walk-forward (883 days, 876 with a tape both sides; the same 7 gappy days skipped by both): 485 trades (nyam 259 / mid 175 /
pm 51; net +$55,889 / +$25,295 / +$3,941 = +$85,125), the store's own count. Exact on the first round, with the tester's
one-print-later stop arming against the engine's strict_limit: nothing was changed to reach it. No test month was run.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from homebase.backtest.tape import early_close_et
from homebase.strategies.base import Strategy

SESSION = "pm"                                   # the one session of this instance: nyam | mid | pm
SESS = {"nyam": (34200, 39600), "mid": (39600, 48600), "pm": (48600, 57480)}     # seconds after 00:00 ET (l2sim.SESS)
ET = ZoneInfo("America/New_York")
NS = 1_000_000_000
STEP = 15 * 60 * NS                                # 15-minute bars on the ET clock
OPEN, OR_END = 34200, 34200 + 15 * 60              # the range: 1-minute bars 09:30 .. 09:44 (or_min 15); the VWAP from 09:30
STOP_PTS, TGT_R, MAX_TR, WARM = 60.0, 2.0, 1, 3    # box or_min15_pts60-r2; the spec's max_tr; Template.WARM
DAY_FLAT, HALF_FLAT = 57480, 47580                 # 15:58 / 13:13 (l2sim.day_flat)


def _hms(s: int) -> str:
    return "%02d:%02d:%02d" % (s // 3600, s % 3600 // 60, s % 60)


class NqOrbVwapPb15(Strategy):
    id = "draft_nq_sk_orbpb15_pm"
    name = "NQ ORB VWAP pullback 15m, NY PM, 60 pt stop 2R (stack, shadow)"
    root = "NQ"
    session_window = ("00:00", "16:00")
    bar_minutes = 1
    session_independent = True
    max_trades_day = 1                             # the engine's max_tr: one session per instance

    def times(self):
        a, b = SESS[SESSION]
        return sorted({_hms(a), _hms(b - 300), _hms(b), _hms(HALF_FLAT - 300), _hms(HALF_FLAT), _hms(DAY_FLAT - 300),
                       _hms(DAY_FLAT)})

    def on_session(self, ctx):
        d = ctx.date
        self.t0 = int(dt.datetime(d.year, d.month, d.day, tzinfo=ET).timestamp()) * NS      # 00:00 ET of the trade date
        self.flat_s = HALF_FLAT if early_close_et(ctx.root, d) is not None else DAY_FLAT
        self.cur = None                            # the 15-minute bar being built: [k, h, l, c]
        self.nb = 0                                # 15-minute bars closed since 00:00
        self.vv = self.vp = 0.0                    # VWAP sums from 09:30
        self.hi = self.lo = None                   # the range
        self.arm = self.brk = 0                    # +1 long / -1 short; brk: the day's one break has come
        self.used = False                          # the arm's touch has come (filled or not)
        self.on = self.over = False                # inside the session / the session (or the day) is over
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

    def _minute(self, ctx, bar):
        """OrbVwapPb._read for one ended minute: the range, the touch (against the VWAP before it), then the VWAP."""
        s = (bar.start_ns - self.t0) // NS
        if s < OPEN:
            return
        if s < OR_END:
            self.hi = bar.h if self.hi is None else max(self.hi, bar.h)
            self.lo = bar.l if self.lo is None else min(self.lo, bar.l)
        w0 = self._vwap()
        touched = bool(self.arm) and w0 is not None and bar.l <= w0 <= bar.h
        if touched:
            self.arm, self.used = 0, True
        if bar.v > 0:
            self.vv += bar.v
            self.vp += bar.v * (bar.h + bar.l + bar.c) / 3.0
        if touched:
            self._drop(ctx)

    def _close(self, ctx):
        """Template._close of a 15-minute bar: OrbVwapPb.fam_update (the break), then can_enter and _Touch.fam_signal."""
        k, h, l, c = self.cur
        self.cur = None
        t_end = (k + 1) * STEP
        end = (t_end - self.t0) // NS              # the nominal close: a late close never counts as later
        self.nb += 1
        if not (self.brk or self.used or self.hi is None or end <= OR_END):
            if c > self.hi:
                self.brk = self.arm = 1
            elif c < self.lo:
                self.brk = self.arm = -1
        w = self._vwap()
        if w is not None:
            ctx.plot("VWAP 09:30", t_end, w)
        if self.hi is not None and end > OR_END:
            ctx.plot("range high", t_end, self.hi)
            ctx.plot("range low", t_end, self.lo)
        self._sync()
        a, b = SESS[SESSION]
        if not (self.on and a < end <= b) or self.nb < WARM or not ctx.flat or self.n_ent >= MAX_TR \
                or ctx.now_ns - self.t0 >= (min(b, self.flat_s) - 300) * NS:
            return
        self._drop(ctx)                            # re-priced at this close, or dropped when the arm is gone
        lp = ctx.last_price
        if w is None or not self.arm or lp is None:
            return
        sd = self.arm
        if (lp - w) * sd <= 0:
            return                                 # only on the passive side of the last print
        self.order = ctx.limit_entry("long" if sd > 0 else "short", w,
                                     sl=w - sd * STOP_PTS, tp=w + sd * TGT_R * STOP_PTS)

    def on_bar(self, ctx, bar):
        k = bar.start_ns // STEP
        if self.cur is not None and self.cur[0] != k:
            self._close(ctx)                       # the bucket's last minute had no print: closed now, before this minute
        self._minute(ctx, bar)
        if self.cur is None:
            self.cur = [k, bar.h, bar.l, bar.c]
        else:
            self.cur[1], self.cur[2], self.cur[3] = max(self.cur[1], bar.h), min(self.cur[2], bar.l), bar.c
        if bar.end_ns % STEP == 0:
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

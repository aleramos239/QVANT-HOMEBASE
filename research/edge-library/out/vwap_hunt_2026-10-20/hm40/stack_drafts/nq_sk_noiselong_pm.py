"""NQ NOISE BAND LONG 5m, NY PM (stack, shadow): a 5-minute close above the 09:30 open + 0.3 x the daily ATR(14) AND above the
VWAP since 09:30 -> market long, stop 60 points, target 120 points (2R). One trade.

THE LAB COPY of the stack rule vh_i9_noise_long_5_ny-NQ-tf5, box k0p3_pts60-r2 (stack #8 of research/edge-library/out/
vwap_hunt_2026-10-20/hm40/STACK.md; engine family `noise_band`: research/edge-library/engine/families/noise.py NoiseBand, run as
families/blocks.py B_noise_band with the open layer families/_flex.py, on l2sim.Template; spec .../hm40/specs/
vh_i9_noise_long_5_ny.json; k 0.3, anchor rth, dir long, max_tr 1, tf 5, hold_to day, stop_mode pts 60, tgt_r 2.0, gate off, every
other block off). The engine runs nyam / mid / pm as three INDEPENDENT instances (run_idea.cell_specs); this file is the one for
SESSION below. nq_sk_noiselong_nyam / _mid / _pm are the same code but for SESSION, `id` and `name`.

THE RULE, as the engine runs it (New York times):
  1. Bars: the trade date's 1-minute bars from 00:00, summed into 5-minute bars on the clock. A 5-minute bar whose last minute had
     no print closes when the next bucket's first minute arrives (the engine does the same), before that minute counts.
  2. The anchor: the OPEN of the first 1-minute bar that starts at or after 09:30. If it starts more than 5 minutes late, the day
     has no anchor and no trade (every session). The anchor does not depend on the session: mid and pm read the same band.
  3. A = Wilder ATR(14) of the daily bars BEFORE today (whole archive days; seeded with the mean of the first 14 true ranges of
     ctx.daily, the same history as the engine's: both start at the archive's first day); none below 15 daily bars.
     The band: up = anchor open + 0.3 x A, set once for the day.
  4. The VWAP since 09:30: volume-weighted typical price (h + l + c) / 3 of the 1-minute bars from the anchor on, the bar just
     closed included.
  5. At a 5-minute close whose clock end lies after the session start and at or before its end: close > up AND close > VWAP ->
     market long at the close. At least 3 bars since 00:00, flat, nothing working, no entry yet in this session (max_tr 1 counts
     FILLED entries), and the close before the session end - 5 min (and before the day's flatten - 5 min).
  6. Stop 60 points below the close, target 120 above it (2R); both moved to the fill (Template._mkt / _dist, stop_mode pts).
  7. Held to stop or target past the session end; flat at 15:58 (13:13 on a CME half day: l2sim.day_flat).

WHERE IT DIFFERS FROM THE ENGINE, AND WHY:
  * Flat at 15:58 like the engine, in the tester AND in shadow (a shadow day runs the strategy's own times). Only if ever BOOKED on
    an account does the Desk cap it at 15:55 (labcfg.FLAT_LATEST): a trade still open 15:55-15:58 would then close up to 3 minutes
    earlier. In-sample 351 of the box's 902 trades end at the flatten (nyam 44 / mid 102 / pm 205); a 15:55 flatten moved the
    nets by +$1,160 nyam / +$1,695 mid / -$335 pm (+$2,520 in all). Entries keep the engine's cut (no close at or after 10:55 in nyam, 13:25 in mid, 15:53 in pm). On a CME half day
    (homebase.backtest.tape.early_close_et, the same calendar as l2sim.EARLY_CLOSES) it is flat at 13:13 and takes no entry from
    13:08 on, as the engine; pm never trades then.
  * The daily bars are the tester's store.daily (the engine's daily cache is built from the same tape headers) or, on the Desk,
    its daily feed: a daily bar that differs there moves A, so the band.
  * Today's prints are the tester's tape (print-identical to the engine's) or, on the Desk, the live prints: live volume can differ
    from the archive's (late prints), so the VWAP, and a close within a tick of it or of the band, can read the other way live.
  * The day window here is 00:00-16:00 (the engine replays to 16:10): nothing is decided after 15:53 in either.
  * Not copied because this box never uses them: the tf ATR (a fixed 60-point stop needs none; the engine's 2-tick floor never
    binds), trail / exit-bars exits (0), every filter block and the gate (off), the cancel of a working entry at the session end
    - 5 min (a market entry fills at the next print), prior-day levels and rolls (unused by noise_band), the short side (dir
    long), the globex anchor.
  * Fills and costs are the tester's (l2sim is its port) or the Desk's shadow fills; 1 contract of NQ (size set on the Desk).
  * A market entry: no limit order, so nothing here is shadow-only for an order type.
Draws the band and the VWAP since 09:30 during its session.

CHECKED 2026-10-21: the three files in the tester's engine (homebase/backtest/runner.execute in-process, the real TapeStore over
~/futures_derived) equal the engine's three instances trade for trade (day, entry time to the millisecond, side, exit time, exit
reason, stop distance, net; the store keeps no prices, the same entry millisecond on the same tape and the same net pin them) on ALL 42 in-sample months of the box's walk-forward (883 days, 876
with a tape both sides; the same 7 gappy days skipped by both): 902 trades (nyam 254 / mid 310 / pm 338; net +$1,874 / +$57,135 /
+$32,868 = +$91,877, the store's own figure, library.unit_cell of runs_wf/vh_i9_noise_long_5_ny-NQ-tf5/is). The first 8 days
(2021-10-01 .. 10-12) have under 15 daily bars: no trade in either. Exact on the first round: nothing was changed to reach it.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from homebase.backtest.tape import early_close_et
from homebase.strategies.base import Strategy

SESSION = "pm"                                 # the one session of this instance: nyam | mid | pm
SESS = {"nyam": (34200, 39600), "mid": (39600, 48600), "pm": (48600, 57480)}     # seconds after 00:00 ET (l2sim.SESS)
ET = ZoneInfo("America/New_York")
NS = 1_000_000_000
TF = 5                                             # minutes
STEP = TF * 60 * NS
ANCHOR, OPEN_TOL = 34200, 300                      # rth anchor 09:30; its first minute bar may start at most 5 minutes late
K, STOP_PTS, TGT_R, MAX_TR, WARM = 0.3, 60.0, 2.0, 1, 3     # box k0p3_pts60-r2; the spec's max_tr; Template.WARM
DAY_FLAT_S, HALF_FLAT_S = 57480, 47580             # 15:58 / 13:13: the engine's flatten (l2sim.day_flat), for the entry cut
FLAT, HALF_FLAT = "15:58", "13:13"                 # when this copy flattens: the engine's day_flat


def datr(dl):
    """Wilder ATR(14) of the daily bars before today (l2sim.Template.datr), or None below 15 bars."""
    if len(dl) < 15:
        return None
    trs = [max(dl[i]["h"] - dl[i]["l"], abs(dl[i]["h"] - dl[i - 1]["c"]), abs(dl[i]["l"] - dl[i - 1]["c"])) for i in range(1, len(dl))]
    a = sum(trs[:14]) / 14.0
    for x in trs[14:]:
        a = (a * 13.0 + x) / 14.0
    return a


class NqNoiseBandLong5(Strategy):
    id = "draft_nq_sk_noiselong_pm"
    name = "NQ noise band long 5m, NY PM (stack, shadow)"
    root = "NQ"
    session_window = ("00:00", "16:00")
    bar_minutes = 1
    session_independent = True
    own_stop = True
    max_trades_day = 1                             # the engine's max_tr: one session per instance

    def needs_daily(self):
        return True

    def times(self):
        return [HALF_FLAT, FLAT]

    def on_session(self, ctx):
        d = ctx.date
        self.t0 = int(dt.datetime(d.year, d.month, d.day, tzinfo=ET).timestamp()) * NS      # 00:00 ET of the trade date
        self.half = early_close_et(ctx.root, d) is not None
        self.s0, self.s1 = SESS[SESSION]
        self.cut = min(self.s1, HALF_FLAT_S if self.half else DAY_FLAT_S) - 300            # no entry from here (seconds)
        self.cur = None                            # the 5-minute bar being built: [k, c]
        self.n = 0                                 # 5-minute bars since 00:00
        a = datr(ctx.daily or [])
        self.atr_d = a if a and a > 0 else None
        self.ref = self.up = None                  # the anchor's open, the band
        self.no_anchor = False
        self.vv = self.vp = 0.0                    # VWAP sums since the anchor: volume, volume x typical price
        self.order, self.n_ent = None, 0
        if self.atr_d is None:
            ctx.skip("no daily ATR(14): fewer than 15 daily bars before today")

    def on_bar(self, ctx, bar):
        k = bar.start_ns // STEP
        if self.cur is not None and self.cur[0] != k:
            self._close(ctx)                       # the bucket's last minute had no print: it closes now, before this minute counts
        s = (bar.start_ns - self.t0) // NS
        if s >= ANCHOR:
            if self.ref is None and not self.no_anchor:
                if s - ANCHOR > OPEN_TOL:
                    self.no_anchor = True
                else:
                    self.ref = bar.o
                    if self.atr_d is not None:
                        self.up = self.ref + K * self.atr_d
            if self.ref is not None and bar.v > 0:
                self.vv += bar.v
                self.vp += bar.v * (bar.h + bar.l + bar.c) / 3.0
        if self.cur is None:
            self.cur = [k, bar.c]
        else:
            self.cur[1] = bar.c
        if bar.end_ns % STEP == 0:
            self._close(ctx)

    def _close(self, ctx):
        k, c = self.cur
        self.cur = None
        self.n += 1
        o = self.order
        if o is not None and o.status != "working":
            self.n_ent += o.status == "filled"
            self.order = None
        end = ((k + 1) * STEP - self.t0) // NS     # the bar's clock end, seconds after 00:00 ET
        if not self.s0 < end <= self.s1 or self.up is None or self.vv <= 0:
            return
        t, w = (k + 1) * STEP, self.vp / self.vv
        ctx.plot("noise band up", t, self.up)
        ctx.plot("VWAP 09:30", t, w)
        if (self.order is not None or not ctx.flat or self.n_ent >= MAX_TR or self.n < WARM
                or ctx.now_ns - self.t0 >= self.cut * NS):
            return
        if c > self.up and c > w:
            ctx.move_brackets_to_fill = True
            self.order = ctx.market("long", sl=c - STOP_PTS, tp=c + TGT_R * STOP_PTS, ref=c)

    def on_time(self, ctx, et_time):
        if et_time == FLAT or (et_time == HALF_FLAT and self.half):
            ctx.flatten("time")

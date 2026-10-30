"""Writes the four Desk copies of the evening boxes (ideas 15-16 and 23, entry 5 min after 18:00) to ~/.homebase/strategies/ (one template, four constant sets)."""
import os

TEMPLATE = '''"""NQ EVENING, one trade a night, decided at 18:05 ET (the owner, 2026-10-30). The Lab copy of the engine family `eve_rule`
(research/edge-library/engine/families/eve_rules.py), rule `%(rule)s`, box "%(cell)s" of idea %(idea)s-NQ-tf5 (entry 5 minutes after 18:00,
%(stopdesc)s, target %(r)sR). Micros.
THE RULE, as the engine runs it (New York times; the evening belongs to the NEXT trade date, as on the chart):
%(ruletext)s
  ENTRY: at the close of the 18:00-18:05 five-minute bar (the 1-minute bar that ends 18:05 has closed; a bar whose last minute had no print
    closes late and takes no trade, as in the engine) the side above, market at the last print. One trade a night.
  STOP: %(stoptext)s (never under 2 ticks). TARGET: %(r)s x the stop. Both are re-priced to the fill. Flat 23:55.
WHERE IT DIFFERS FROM THE ENGINE:
  * "Daily bars" are Globex days ending 17:00 ET (no day-session split); the tester's or, on the Desk, its live feed's. The engine skips a trade
    date whose DAY window (to 16:10) has an empty clock hour; this copy needs only the evening, so a few holiday evenings may trade here only.
  * An evening window (it starts the evening before its date) is SHADOW ONLY on the Desk (labrun host EVENING_DESK): it cannot be booked on an
    account as the Desk is today.
  * Evidence is a lead, not an approval: see Findings 2026-10-30 (15-16 and 23 test months, Monte Carlo).
%(drawtext)s"""
from __future__ import annotations

from homebase.strategies.base import Input, Strategy

NS = 1_000_000_000
STEP = 5 * 60 * NS                                 # the 5-minute bars the stop ATR counts
ANCHOR, OPEN_TOL = -21600, 300                     # 18:00 ET, seconds after 00:00 of the trade date; its first minute may start 5 minutes late
DECIDE_S = ANCHOR + 5 * 60                         # 18:05: the clock end of the first 5-minute bar
FLAT = "-23:55:00"
TICK = 0.25
RULE = "%(rule)s"                                  # loc10 (ideas 15-16) | newext (idea 23)


class %(cls)s(Strategy):
    name = "%(title)s"
    root = "NQ"
    own_stop = True
    exec_root = "MNQ"
    session_window = ("-18:00", "00:00")
    bar_minutes = 1
    session_independent = True
    max_trades_day = 1

    @classmethod
    def inputs(cls):
        return [%(inputs)s]

    def needs_daily(self):
        return True

    def times(self):
        return [FLAT]

    def on_session(self, ctx):
        self.t0 = ctx.now_ns + 21600 * NS          # 00:00 ET of the trade date (the session opens at 18:00 the evening before)
        self.cur = None                            # the 5-minute bar being built: [bucket, h, l, c]
        self.n = 0                                 # 5-minute bars since 18:00
        self.pc = None
        self.trs = []
        self.atr = None
        self.ref = None
        self.no_anchor = False
        self.order = None
        self.side = 0
        dl = ctx.daily or []
        self.side = self._side(ctx, dl)

    def _side(self, ctx, dl):
        """+1 long / -1 short / 0 no trade, from the daily bars before today (decided before 18:00, nothing of tonight used)."""
        if not dl:
            ctx.skip("no daily bars")
            return 0
%(sidecode)s

    def on_bar(self, ctx, bar):
        k = bar.start_ns // STEP
        if self.cur is not None and self.cur[0] != k:
            self._close(ctx, False)                # the bucket's last minute had no print: it closes now, late (no decision)
        s = (bar.start_ns - self.t0) // NS
        if s >= ANCHOR and self.ref is None and not self.no_anchor:
            if s - ANCHOR > OPEN_TOL:
                self.no_anchor = True
            else:
                self.ref = bar.o
        if self.cur is None:
            self.cur = [k, bar.h, bar.l, bar.c]
        else:
            c = self.cur
            c[1], c[2], c[3] = max(c[1], bar.h), min(c[2], bar.l), bar.c
        if bar.end_ns %% STEP == 0:
            self._close(ctx, True, bar.c)

    def _close(self, ctx, on_time, last=None):
        k, h, l, c = self.cur
        self.cur = None
        tr = h - l if self.pc is None else max(h - l, abs(h - self.pc), abs(l - self.pc))
        self.pc = c
        self.n += 1
        if self.n <= 14:
            self.trs.append(tr)
            self.atr = sum(self.trs) / self.n
        else:
            self.atr = (self.atr * 13.0 + tr) / 14.0
        end = ((k + 1) * STEP - self.t0) // NS
        if not on_time or end != DECIDE_S or self.order is not None or not self.side or self.no_anchor or self.ref is None or not ctx.flat:
            return
        sd = self.side
        d = %(distcode)s
        ctx.move_brackets_to_fill = True
        self.order = ctx.market("long" if sd > 0 else "short", sl=last - sd * d, tp=last + sd * self.p["rr"] * d, ref=last)

    def on_time(self, ctx, et_time):
        if et_time == FLAT:
            ctx.flatten("time")
'''

LOC10 = '''  RULE loc10 (ideas 15-16): the last daily bar (the Globex day that ended 17:00 ET) closed in the top 10 % of its range -> LONG; in the bottom
    10 % -> SHORT; anywhere between (or a zero range) -> no trade tonight.'''
NEWEXT = '''  RULE newext (idea 23): the last daily bar's high is at or above the highest high of the last 20 daily bars (itself included), i.e. the day
    made a 20-day high -> LONG; otherwise no trade tonight. Never short.'''
SIDE_LOC = '''        d1 = dl[-1]
        rg = d1["h"] - d1["l"]
        pos = (d1["c"] - d1["l"]) / rg if rg > 0 else 0.5
        ctx.hline("prior day close 90% line", d1["l"] + 0.9 * rg, role="level")
        ctx.hline("prior day close 10% line", d1["l"] + 0.1 * rg, role="level")
        return 1 if pos >= 0.9 else -1 if pos <= 0.1 else 0'''
SIDE_NEW = '''        if len(dl) < 20:
            ctx.skip("fewer than 20 daily bars before today")
            return 0
        top = max(x["h"] for x in dl[-20:])
        ctx.hline("20-day high", top, role="level")
        return 1 if dl[-1]["h"] >= top else 0'''
DIST_PTS = 'max(self.p["stop"], 2 * TICK)'
DIST_ATR = 'max(self.p["stop"] * self.atr, 2 * TICK)'

BOXES = [  # file, class, title, idea, cell, rule, stop mode, stop value, R
    ("nq_eve_cl_e5_p15_r2", "NqEveCloseLoc", "NQ Evening Close Location Follow · 15 pts · 2R", "i15_16_close_loc_follow", "off_min5_pts15-r2", "loc10", "pts", 15, 2),
    ("nq_eve_nh_e5_a15_r15", "NqEveNewHigh", "NQ Evening 20-Day-High Long · ATR x1.5 · 1.5R", "i23_new_high_long", "off_min5_atr1p5-r1p5", "newext", "atr", 1.5, 1.5),
    ("nq_eve_nh_e5_p25_r05", "NqEveNewHigh", "NQ Evening 20-Day-High Long · 25 pts · 0.5R", "i23_new_high_long", "off_min5_pts25-r0p5", "newext", "pts", 25, 0.5),
    ("nq_eve_nh_e5_a15_r1", "NqEveNewHigh", "NQ Evening 20-Day-High Long · ATR x1.5 · 1R", "i23_new_high_long", "off_min5_atr1p5-r1", "newext", "atr", 1.5, 1),
]
out = os.path.expanduser("~/.homebase/strategies")
for f, cls, title, idea, cell, rule, sm, sv, r in BOXES:
    pts = sm == "pts"
    code = TEMPLATE % dict(
        rule=rule, cell=cell, idea=idea, cls=cls, title=title, r=("%g" % r), rr=r,
        stopdesc=("stop %g points" % sv) if pts else ("stop %g x the 5-minute ATR" % sv),
        stoptext=("%g points from the fill reference" % sv) if pts else
                 "%g x the 5-minute ATR(14) at the 18:05 close (the first 18:00-18:05 bar's high - low: mean of the true ranges up to 14 bars, then Wilder; it restarts at 18:00)" % sv,
        ruletext=LOC10 if rule == "loc10" else NEWEXT,
        drawtext="Draws the prior-day 90/10 % lines (15-16) or the 20-day high (23).",
        inputs=('Input("stop", "Stop (%s)", "float", %g, 0.25, 200.0, 0.25), Input("rr", "Target (x the stop)", "float", %g, 0.25, 3.0, 0.05)' % ("points" if pts else "x 5-min ATR", sv, r)),
        sidecode=SIDE_LOC if rule == "loc10" else SIDE_NEW,
        distcode=DIST_PTS if pts else DIST_ATR)
    open(os.path.join(out, f + ".py"), "w").write(code)
    print("wrote", f)

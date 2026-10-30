"""Writes the four Desk copies of the fvg_lab ovw15 boxes to ~/.homebase/strategies/ (one template, four constant sets)."""
import os, sys

TEMPLATE = '''"""NQ: 15-minute fair value gap, limit at its near edge, on the side where the 09:30 open and the 09:30 VWAP agree; fixed-point stop and
target, up to 3 trades a day (the owner, 2026-10-29). Micros. The Lab copy of the engine family `fvg_lab` (research/edge-library/engine/
families/fvg_lab.py), box "%(box)s" of idea f100_ovw15-NQ-tf15 (min gap %(g)s x ATR, stop %(s)s points, target %(r)sR).
  * GAP: three 15-minute bars that all start at or after 09:30 (the first at the 10:15 close); up = bar 3's low above bar 1's high (near
    edge bar 3's low), down the mirror; size at least %(g)s x the ATR(14) of the 15-minute bars counted from 00:00 ET (simple mean of the first
    14 true ranges, then Wilder; the study's engine counts the night's bars too). A 15-minute close through the far edge kills the gap.
  * SIDE, at the gap's close: price above BOTH the 09:30 open and the 09:30 VWAP (typical price x volume of the 1-minute bars) = longs
    only, below both = shorts only, they disagree = no trade.
  * ORDER: a LIMIT at the near edge, only for the gap that has just formed (never an older one); it replaces a resting order and is cancelled
    when its gap dies. A gap formed while a trade is open is used up. A resting order is cancelled at the first close after 15:00.
  * STOP: %(s)s points from the entry. TARGET: %(r)s x the stop. One position at a time, 3 trades a day at most. Flat 15:55 (the Desk's cap;
    the study flattened at 15:58).
Orders go to MNQ (the micro); prices are NQ's. Draws each gap's near edge."""
from __future__ import annotations

from homebase.strategies.base import Input, Strategy

MIN = 60_000_000_000


class %(cls)s(Strategy):
    name = "%(title)s"
    root = "NQ"
    own_stop = True
    exec_root = "MNQ"
    session_window = ("00:00", "16:00")      # the study counts the 15-minute ATR from 00:00 ET; it enters from 10:15
    bar_minutes = 1
    session_independent = True

    @classmethod
    def inputs(cls):
        return [Input("min_gap", "Smallest gap (x ATR 15-min)", "float", %(g)s, 0.0, 2.0, 0.05),
                Input("stop", "Stop (points)", "float", %(s)s, 5.0, 200.0, 0.25),
                Input("rr", "Target (x the stop)", "float", %(r)s, 0.25, 3.0, 0.05),
                Input("max_trades", "Trades a day at most", "int", 3, 1, 20, 1)]

    def times(self):
        return ["09:30:00", "15:00", "15:55"]

    def on_session(self, ctx):
        self.open_ns = self.open_px = None
        self.cf = None              # the 15-minute bar being built: [bucket, o, h, l, c]
        self.raw = []               # the closed 15-minute bars since 00:00 ET before 09:30: (start_ns, o, h, l, c), for the ATR
        self.bf = []                # closed 15-minute bars (o, h, l, c) from 09:30
        self.tr = []                # true ranges of the 15-minute bars since 00:00 ET
        self.atr = None
        self.vw = [0.0, 0.0]        # [sum(typical x volume), sum(volume)] since 09:30
        self.og = None              # [side, far edge, dead] of the gap the current order belongs to
        self.order = None
        self.fills = 0

    def _tick(self, ctx, px):
        return round(round(px / ctx.tick) * ctx.tick, 6)

    def _drop(self, ctx):
        if self.order is not None and self.order.status == "working":
            ctx.cancel(self.order)
        self.order = None

    def _side(self, c):
        """+1 / -1 = the allowed side, 0 = none: the 09:30 open and the 09:30 VWAP must agree."""
        if self.open_px is None or self.vw[1] <= 0:
            return 0
        a = (c > self.open_px) - (c < self.open_px)
        b = (c > self.vw[0] / self.vw[1]) - (c < self.vw[0] / self.vw[1])
        return a if a == b else 0

    def _atr_add(self, h, l, pc):
        tr = h - l if pc is None else max(h - l, abs(h - pc), abs(l - pc))
        self.tr.append(tr)
        n = len(self.tr)
        self.atr = sum(self.tr) / n if n <= 14 else (self.atr * 13.0 + tr) / 14.0

    def _close15(self, ctx, t_ns, bar):
        """One 15-minute close (the family's fam_update, then its fam_signal)."""
        if self.open_ns is None:
            self.raw.append(bar)
            return
        pc = self.bf[-1][3] if self.bf else (self.raw[-1][4] if self.raw else None)
        self.bf.append(bar[1:])
        o, h, l, c = bar[1:]
        self._atr_add(h, l, pc)
        if t_ns > self.open_ns + 330 * MIN:          # past the 15:00 close: no new order; a resting one goes
            if ctx.flat:
                self._drop(ctx)
            return
        if len(self.bf) < 3:
            return
        og = self.og
        if og is not None and not og[2] and (c - og[1]) * og[0] < 0:
            og[2] = True                                   # a close through the far edge kills the gap
        if og is not None and og[2] and ctx.flat:
            self._drop(ctx)
        (_, h1, l1, _), (_, h2, l2, _), (_, h3, l3, _) = self.bf[-3:]
        for sd, near, far in ((1, l3, h1), (-1, h3, l1)):
            if (near - far) * sd <= 0 or abs(near - far) < max(self.p["min_gap"] * self.atr, ctx.tick):
                continue
            ctx.hline("FVG %%s near edge" %% ("up" if sd > 0 else "down"), near, role="entry")
            if self._side(c) != sd:
                continue
            if ctx.flat:
                self._drop(ctx)
            self.og = [sd, far, False]
            if not ctx.flat or self.order is not None or self.fills >= self.p["max_trades"]:
                continue                                   # a gap formed during a trade is used up
            lp = ctx.last_price
            if lp is not None and (lp - near) * sd > 0:     # only on the passive side of the last print
                d = max(self.p["stop"], 2 * ctx.tick)
                ctx.move_brackets_to_fill = True
                self.order = ctx.limit_entry("long" if sd > 0 else "short", near, sl=self._tick(ctx, near - sd * d),
                                             tp=self._tick(ctx, near + sd * self.p["rr"] * d))

    def on_bar(self, ctx, bar):
        if self.order is not None and self.order.status == "filled":
            self.fills += 1
            self.order = None
        elif self.order is not None and self.order.status != "working":
            self.order = None
        k = bar.start_ns // (15 * MIN)
        if self.cf is not None and self.cf[0] != k:       # the bucket's last minute had no print
            cf, self.cf = self.cf, None
            self._close15(ctx, (cf[0] + 1) * 15 * MIN, (cf[0] * 15 * MIN,) + tuple(cf[1:]))
        if self.open_ns is not None and bar.start_ns >= self.open_ns:
            if self.open_px is None:
                self.open_px = bar.o
            if bar.v > 0:
                self.vw[0] += (bar.h + bar.l + bar.c) / 3.0 * bar.v
                self.vw[1] += bar.v
        if self.cf is None:
            self.cf = [k, bar.o, bar.h, bar.l, bar.c]
        else:
            self.cf[2], self.cf[3], self.cf[4] = max(self.cf[2], bar.h), min(self.cf[3], bar.l), bar.c
        if bar.end_ns %% (15 * MIN) == 0:
            cf, self.cf = self.cf, None
            self._close15(ctx, bar.end_ns, (cf[0] * 15 * MIN,) + tuple(cf[1:]))

    def on_time(self, ctx, et_time):
        if et_time == "09:30:00":
            self.open_ns = ctx.now_ns - ctx.now_ns %% MIN
            pc = None
            for b in self.raw:                          # the engine counts the ATR from 00:00 ET
                if b[0] >= self.open_ns - 570 * MIN:
                    self._atr_add(b[2], b[3], pc)
                    pc = b[4]
            self.raw = [b for b in self.raw if b[0] >= self.open_ns - 570 * MIN][-1:]
        elif et_time == "15:55":
            self._drop(ctx)
            ctx.flatten("time")
'''

BOXES = [  # file, class, title, box, min_gap, stop, rr
    ("nq_fvg15_ovw_g25_s60_r1", "NqFvg15OvwG25S60R1", "NQ 15m FVG, open+VWAP side, 60 pts, 1R", "min_gap0p25_pts60-r1", "0.25", "60.0", "1.0"),
    ("nq_fvg15_ovw_g25_s25_r2", "NqFvg15OvwG25S25R2", "NQ 15m FVG, open+VWAP side, 25 pts, 2R", "min_gap0p25_pts25-r2", "0.25", "25.0", "2.0"),
    ("nq_fvg15_ovw_g10_s60_r075", "NqFvg15OvwG10S60R075", "NQ 15m FVG (small gaps), open+VWAP side, 60 pts, 0.75R", "min_gap0p1_pts60-r0p75", "0.1", "60.0", "0.75"),
    ("nq_fvg15_ovw_g10_s25_r15", "NqFvg15OvwG10S25R15", "NQ 15m FVG (small gaps), open+VWAP side, 25 pts, 1.5R", "min_gap0p1_pts25-r1p5", "0.1", "25.0", "1.5"),
]
out = os.path.expanduser("~/.homebase/strategies")
for f, cls, title, box, g, s, r in BOXES:
    path = os.path.join(out, f + ".py")
    if os.path.exists(path) and "--force" not in sys.argv:
        sys.exit("exists: " + path)
    open(path, "w").write(TEMPLATE % dict(cls=cls, title=title, box=box, g=g, s=s, r=r))
    print("wrote", path)

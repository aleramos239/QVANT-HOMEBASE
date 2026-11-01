"""NQ 9:30 straddle, how far from the 9:30 print the two stop orders sit (2026-11-01).

Same as nq_930_straddle (cancel the other side at the first fill; stop/target from the run controls; unfilled legs
cancelled 12:55; flat 15:55) with the distance chosen by a rule, times the multiplier k:
  pts      k points
  pct      k percent of the 9:30 print
  preopen  k x the 09:00-09:30 high-low range (the last print of each minute, so a touch under the true range)
  rv       k x the std of the 1-minute moves 09:00-09:30 (same samples)
  rvd      k x the std of the last 20 daily close-to-close moves (the sessions before today)
gap: both | with | against -- with / against trade only the side of / opposite to the gap (9:30 print minus the
previous daily close); no gap = no trade.
A DRAFT strategy for the Homebase Strategy Tester.
"""
from __future__ import annotations

import statistics

from homebase.strategies.base import Input, Strategy

PRE = [f"09:{m:02d}:00" for m in range(30)]


class NQ930StraddleDist(Strategy):
    id = "draft_nq_930_straddle_dist"
    name = "NQ 9:30 Straddle, distance rules"
    root = "NQ"
    own_stop = True
    session_window = ("09:00", "16:00")
    session_independent = True
    fire, cancel_et, flat_et = "09:30:00", "12:55", "15:55"

    @classmethod
    def inputs(cls):
        return [
            Input("dist", "Distance rule", "choice", "pts", None, None, None, ("pts", "pct", "preopen", "rv", "rvd")),
            Input("k", "Multiplier (pts / % / x)", "float", 5.0, 0.0, 1000.0, 0.001),
            Input("gap", "Side by gap", "choice", "both", None, None, None, ("both", "with", "against")),
            Input("sl_pts", "Stop loss (pts)", "float", 5.0, 0.25, 500.0, 0.25),
            Input("tp_pts", "Take profit (pts)", "float", 7.5, 0.25, 500.0, 0.25),
        ]

    def times(self):
        pre = PRE if self.p["dist"] in ("preopen", "rv") else []
        return pre + [self.fire, self.cancel_et, self.flat_et]

    def needs_daily(self):
        return self.p["dist"] == "rvd" or self.p["gap"] != "both"

    def on_session(self, ctx):
        self.entries, self.samples = (), []

    def offset(self, ctx, anchor):
        mode, k = self.p["dist"], self.p["k"]
        if mode == "pts":
            return k
        if mode == "pct":
            return anchor * k / 100
        if mode in ("preopen", "rv"):
            s = self.samples + [anchor]
            if len(s) < 20:
                return None
            if mode == "preopen":
                return k * (max(s) - min(s))
            return k * statistics.stdev([b - a for a, b in zip(s, s[1:])])
        c = [float(b["c"]) for b in ctx.daily[-21:]]
        if len(c) < 21:
            return None
        return k * statistics.stdev([b - a for a, b in zip(c, c[1:])])

    def on_time(self, ctx, et_time):
        if et_time in PRE:
            if ctx.last_price is not None:
                self.samples.append(ctx.last_price)
        elif et_time == self.fire:
            anchor = ctx.last_price
            if anchor is None:
                ctx.skip(f"no print before {self.fire}")
                return
            off = self.offset(ctx, anchor)
            if off is None:
                ctx.skip("not enough history for the distance rule")
                return
            off = max(off, 0.25)
            long_ok = short_ok = True
            if self.p["gap"] != "both":
                if not ctx.daily:
                    ctx.skip("no previous close")
                    return
                gap = anchor - float(ctx.daily[-1]["c"])
                if gap == 0:
                    ctx.skip("no gap")
                    return
                up_side = (gap > 0) == (self.p["gap"] == "with")
                long_ok, short_ok = up_side, not up_side
            sl, tp = self.p["sl_pts"], self.p["tp_pts"]
            up, dn = anchor + off, anchor - off
            ctx.plot("offset", ctx.now_ns, off)
            ctx.hline("anchor", anchor, role="anchor")
            ctx.move_brackets_to_fill = True
            legs = []
            if long_ok:
                ctx.hline("Long entry", up, role="entry")
                legs.append(ctx.stop_entry("long", up, sl=up - sl, tp=up + tp))
            if short_ok:
                ctx.hline("Short entry", dn, role="entry")
                legs.append(ctx.stop_entry("short", dn, sl=dn + sl, tp=dn - tp))
            self.entries = tuple(legs)
            if len(legs) == 2:
                ctx.oco(*legs)
        elif et_time == self.cancel_et:
            for o in self.entries:
                ctx.cancel(o)
        elif et_time == self.flat_et:
            ctx.flatten("time")

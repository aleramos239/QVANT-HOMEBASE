"""10:00 TREND CHECK variant (2026-11-01): at 10:00 the first 30 minutes are read from one-minute prints: efficiency = |move 9:30->10:00| / (high-low of those prints).
Below eff_min (0 = off) the day is not a trend day: cancel what is unfilled and flat what is open. Everything else is the plain 9:30 straddle.

NQ 9:30 straddle, rebuilt as a Lab strategy (2026-10-20; was the Desk's built-in nq930).

Same rule as the built-in: at 09:30:00 the anchor is the last print; a buy stop at anchor + offset and a sell stop at
anchor - offset, one cancels the other; stop and target re-priced to the fill; unfilled legs cancelled 12:55; an open
position flat 15:55. The ADX(14) trend gate on the daily bars (off by default, as on the Desk; min 20): no trade when ADX <= min.
Defaults = the built-in's: offset 5 / stop 5 / target 7.5 (the Desk's config.json: rr 1.5, gate off).
A DRAFT strategy for the Homebase Strategy Tester.
"""
from __future__ import annotations

from homebase.gate import trend_gate
from homebase.strategies.base import Input, Strategy

MIN_GATE_BARS, GATE_BARS = 110, 250


class NQ930Straddle(Strategy):
    id = "draft_nq_930_straddle_trend"
    name = "NQ 9:30 Straddle, 10:00 trend check"
    root = "NQ"
    own_stop = True     # it passes its own sl: the heat map gets the 4 own-stop rows (2026-10-21)
    session_window = ("09:25", "16:00")
    session_independent = True           # day state resets in on_session; the gate reads ctx.daily
    fire, cancel_et, flat_et = "09:30:00", "12:55", "15:55"

    @classmethod
    def inputs(cls):
        return [
            Input("offset_pts", "Entry offset (pts)", "float", 5.0, 0.0, 500.0, 0.25),
            Input("sl_pts", "Stop loss (pts)", "float", 5.0, 0.25, 500.0, 0.25),
            Input("tp_pts", "Take profit (pts)", "float", 7.5, 0.25, 500.0, 0.25),
            Input("eff_min", "10:00 trend check: min efficiency (0 = off)", "float", 0.0, 0.0, 1.0, 0.05),
            Input("adx_gate", "ADX(14) trend gate", "bool", False),
            Input("adx_min", "ADX threshold", "float", 20.0, 0.0, 100.0, 0.5),
        ]

    def times(self):
        mins = ["09:%02d:00" % m for m in range(31, 60)] + ["10:00:00"] if self.p["eff_min"] > 0 else []
        return [self.fire] + mins + [self.cancel_et, self.flat_et]

    def needs_daily(self):
        return bool(self.p["adx_gate"])

    def on_session(self, ctx):
        self.entries = ()
        self.px = []                      # last print at 09:30, 09:31 ... 10:00

    def on_time(self, ctx, et_time):
        if self.p["eff_min"] > 0 and self.entries and ("09:30:00" < et_time <= "10:00:00"):
            if ctx.last_price is not None:
                self.px.append(ctx.last_price)
            if et_time == "10:00:00" and len(self.px) >= 25:
                p = [self.anchor] + self.px
                rng = max(p) - min(p)
                eff = abs(p[-1] - p[0]) / rng if rng > 0 else 0.0
                ctx.plot("10:00 efficiency", ctx.now_ns, eff)
                if eff < self.p["eff_min"]:
                    for o in self.entries:
                        ctx.cancel(o)
                    ctx.flatten("time")
            return
        if et_time == self.fire:
            if self.p["adx_gate"]:
                bars = ctx.daily[-GATE_BARS:]
                if len(bars) < MIN_GATE_BARS:
                    ctx.skip("trend gate unknown (under 110 daily bars)")
                    return
                ok, adx = trend_gate(bars, self.p["adx_min"])
                ctx.plot("ADX(14)", ctx.now_ns, adx)
                ctx.plot("ADX gate min", ctx.now_ns, self.p["adx_min"])
                if not ok:
                    ctx.skip(f"trend gate: ADX {adx} <= {self.p['adx_min']:g}")
                    return
            anchor = self.anchor = ctx.last_price
            if anchor is None:
                ctx.skip(f"no print before {self.fire}")
                return
            off, sl, tp = self.p["offset_pts"], self.p["sl_pts"], self.p["tp_pts"]
            up, dn = anchor + off, anchor - off
            ctx.hline("anchor", anchor, role="anchor")
            ctx.hline("Long entry", up, role="entry")
            ctx.hline("Short entry", dn, role="entry")
            ctx.move_brackets_to_fill = True
            self.entries = (ctx.stop_entry("long", up, sl=up - sl, tp=up + tp),
                            ctx.stop_entry("short", dn, sl=dn + sl, tp=dn - tp))
            ctx.oco(*self.entries)
        elif et_time == self.cancel_et:
            for o in self.entries:
                ctx.cancel(o)
        elif et_time == self.flat_et:
            ctx.flatten("time")

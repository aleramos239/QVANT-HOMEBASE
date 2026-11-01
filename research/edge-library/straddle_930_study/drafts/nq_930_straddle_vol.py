"""NQ 9:30 straddle with volume-based offsets, stops and an exit (2026-11-01).

Same straddle as nq_930_straddle (cancel the other side at the first fill, unfilled legs cancelled 12:55, flat 15:55). Reads 5-minute
bars 08:10-09:30 (price and volume) and the volume of the 14 earlier sessions (ctx.minute_volume).
  off_mode  pts         k points
            rvol_wide   k pts x RVOL          RVOL = volume 08:30-09:30 / its median over the 14 earlier sessions, held to 0.5-2
            rvol_tight  k pts / RVOL          (busy pre-open = tighter, thin = wider)
            vwapdev     k x |9:30 price - volume-weighted price 08:30-09:30|, at least 2 pts
            vband       k x the volume-weighted std of the 5-minute typical prices 08:30-09:30, at least 2 pts
  stop_kind ctl         the run's own ATR stop (ctl.stop_atr), as in the other drafts
            atr         sl_mult x the mean true range of the last 14 five-minute bars (read at 9:30)
            vwatr       sl_mult x the same bars' true range weighted by each bar's volume
            rvol_up     atr x RVOL (busy day = wider stop)
            rvol_dn     atr / RVOL (busy day = tighter stop)
  dryup     0 = off; f = flat the trade when a 5-minute bar after the entry bar trades less than f x the entry bar's volume
Not exact: the stop is sized at 9:30 (the run controls size theirs at the fill), and bars are 5 minutes.
A DRAFT strategy for the Homebase Strategy Tester.
"""
from __future__ import annotations

import datetime as dt
import statistics
from zoneinfo import ZoneInfo

from homebase.strategies.base import Input, Strategy

ET = ZoneInfo("America/New_York")
NS = 1_000_000_000
MIN0, NMIN = -360, 1380                  # ctx.minute_volume: index 0 = 18:00 ET the evening before
V_FROM = 8 * 3600 + 30 * 60              # volume window starts 08:30 (seconds after 00:00 ET)


class NQ930StraddleVol(Strategy):
    id = "draft_nq_930_straddle_vol"
    name = "NQ 9:30 Straddle, volume rules"
    root = "NQ"
    own_stop = True
    session_window = ("08:10", "16:00")
    bar_minutes = 5
    session_independent = True
    fire, cancel_et, flat_et = "09:30:00", "12:55", "15:55"

    @classmethod
    def inputs(cls):
        return [
            Input("off_mode", "Offset rule", "choice", "pts", None, None, None, ("pts", "rvol_wide", "rvol_tight", "vwapdev", "vband")),
            Input("k", "Offset multiplier (pts / x)", "float", 5.0, 0.0, 1000.0, 0.001),
            Input("stop_kind", "Stop rule", "choice", "ctl", None, None, None, ("ctl", "atr", "vwatr", "rvol_up", "rvol_dn")),
            Input("sl_mult", "Stop multiple (stop_kind other than ctl)", "float", 4.0, 0.25, 50.0, 0.25),
            Input("dryup", "Volume dry-up exit (0 = off)", "float", 0.0, 0.0, 5.0, 0.05),
            Input("sl_pts", "Stop loss when the run sets it (pts)", "float", 10.0, 0.25, 500.0, 0.25),
            Input("tp_pts", "Take profit when the run sets it (pts)", "float", 15.0, 0.25, 500.0, 0.25),
        ]

    def times(self):
        return [self.fire, self.cancel_et, self.flat_et]

    def needs_minute_volume(self):
        return 14

    def on_session(self, ctx):
        d = ctx.date
        self.t0 = int(dt.datetime(d.year, d.month, d.day, tzinfo=ET).timestamp()) * NS
        self.bars = []                       # (start_s, end_s, h, l, c, v), seconds after 00:00 ET
        self.entries, self.entry_vol, self.fired = (), None, False
        self.vols = [e["vol"] for e in (getattr(ctx, "minute_volume", None) or [])
                     if isinstance(e, dict) and isinstance(e.get("vol"), list) and len(e["vol"]) == NMIN]

    def on_bar(self, ctx, bar):
        s, e = (bar.start_ns - self.t0) // NS, (bar.end_ns - self.t0) // NS
        if e <= 9 * 3600 + 30 * 60 and not self.fired:
            self.bars.append((s, e, bar.h, bar.l, bar.c, bar.v))
            return
        f = self.p["dryup"]
        if not (f and self.entries):
            return
        if self.entry_vol is None:
            if any(o.status == "filled" for o in self.entries):
                self.entry_vol = max(bar.v, 1)      # the bar the fill happened in
        elif bar.v < f * self.entry_vol:
            ctx.flatten("time")

    def rvol(self):
        win = [b for b in self.bars if b[0] >= V_FROM]
        if not win:
            return None
        mine = sum(b[5] for b in win)
        i0, i1 = V_FROM // 60 - MIN0, win[-1][1] // 60 - MIN0
        base = [sum(v[i0:i1]) for v in self.vols[-14:]]
        base = [x for x in base if x > 0]
        if len(base) < 5 or mine <= 0:
            return None
        return min(max(mine / statistics.median(base), 0.5), 2.0)

    def atr_pair(self):
        b = self.bars[-15:]
        if len(b) < 15:
            return None
        trs = [max(h - l, abs(h - pc[4]), abs(l - pc[4])) for (_, _, h, l, _, _), pc in zip(b[1:], b)]
        vs = [x[5] for x in b[1:]]
        return sum(trs) / 14, (sum(t * v for t, v in zip(trs, vs)) / sum(vs) if sum(vs) else None)

    def on_time(self, ctx, et_time):
        if et_time == self.fire:
            self.fired = True
            anchor = ctx.last_price
            if anchor is None:
                ctx.skip("no print before 09:30")
                return
            mode, k, sk = self.p["off_mode"], self.p["k"], self.p["stop_kind"]
            win = [b for b in self.bars if b[0] >= V_FROM]
            rv = self.rvol() if (mode.startswith("rvol") or sk.startswith("rvol")) else 1.0
            if rv is None:
                ctx.skip("no RVOL baseline")
                return
            if mode == "pts":
                off = k
            elif mode == "rvol_wide":
                off = k * rv
            elif mode == "rvol_tight":
                off = k / rv
            else:
                vol = sum(b[5] for b in win)
                if not win or vol <= 0:
                    ctx.skip("no pre-open volume")
                    return
                tps = [(b[2] + b[3] + b[4]) / 3 for b in win]
                vw = sum(t * b[5] for t, b in zip(tps, win)) / vol
                if mode == "vwapdev":
                    off = k * abs(anchor - vw)
                else:
                    off = k * (sum(b[5] * (t - vw) ** 2 for t, b in zip(tps, win)) / vol) ** 0.5
                off = max(off, 2.0)
            sl, tp = self.p["sl_pts"], self.p["tp_pts"]
            if sk != "ctl":
                ap = self.atr_pair()
                if ap is None or (sk == "vwatr" and ap[1] is None):
                    ctx.skip("not enough bars for the stop")
                    return
                x = {"atr": ap[0], "vwatr": ap[1], "rvol_up": ap[0] * (rv or 1), "rvol_dn": ap[0] / (rv or 1)}[sk]
                sl = max(self.p["sl_mult"] * x, 1.0)
                tp = sl                       # placeholder: the run's target_rr re-derives it
            up, dn = anchor + off, anchor - off
            ctx.plot("offset", ctx.now_ns, off)
            ctx.hline("anchor", anchor, role="anchor")
            ctx.move_brackets_to_fill = True
            ctx.hline("Long entry", up, role="entry")
            ctx.hline("Short entry", dn, role="entry")
            self.entries = (ctx.stop_entry("long", up, sl=up - sl, tp=up + tp), ctx.stop_entry("short", dn, sl=dn + sl, tp=dn - tp))
            ctx.oco(*self.entries)
        elif et_time == self.cancel_et:
            for o in self.entries:
                ctx.cancel(o)
        elif et_time == self.flat_et:
            ctx.flatten("time")

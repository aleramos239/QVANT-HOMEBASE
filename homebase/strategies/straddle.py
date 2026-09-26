"""Open straddles: OCO stop entries at anchor +/- offset, brackets re-priced to the fill.

Mirrors the desk: the anchor is the last print BEFORE the fire time (the timer
fires at 09:30:00.000 on the last trade it has seen); the legs are exactly
engine._legs (buy stop at anchor + offset with SL trigger - sl / TP trigger + tp,
sell stop mirrored); after the fill both brackets move to the fill, like
engine._move_brackets; unfilled entries are cancelled at cancel_et; an open
position is flattened at flat_et.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..gate import THRESHOLD, trend_gate
from .base import Input, Strategy

MIN_GATE_BARS = 110       # = homebase.timer.MIN_GATE_BARS (pinned by a test)
GATE_BARS = 250           # = homebase.timer.GATE_BARS


def desk_cfg(name: str):
    """The desk's StrategyCfg as the desk would load it (config.json over the
    frozen defaults). Read at call time, so the tester follows the desk file."""
    from ..config import load
    return load().strategies[name]


@dataclass(frozen=True)
class Leg:
    side: str             # "long" | "short"
    trigger: float
    sl: float
    tp: float


class OpenStraddle(Strategy):
    fire = "09:30:00"
    cancel_et = "12:55"
    flat_et = "15:55"

    def legs(self, anchor: float) -> list[Leg]:
        off, sl, tp = self.p["offset_pts"], self.p["sl_pts"], self.p["tp_pts"]
        up, dn = anchor + off, anchor - off
        return [Leg("long", up, up - sl, up + tp), Leg("short", dn, dn + sl, dn - tp)]

    def times(self) -> list[str]:
        return [self.fire, self.cancel_et, self.flat_et]

    def needs_daily(self) -> bool:
        return bool(self.p.get("adx_gate"))

    def on_session(self, ctx) -> None:
        self.entries = ()

    def on_time(self, ctx, et_time: str) -> None:
        if et_time == self.fire:
            if self.p.get("adx_gate"):
                bars = ctx.daily[-GATE_BARS:]
                ok, adx = trend_gate(bars, self.p["adx_min"]) if len(bars) >= MIN_GATE_BARS \
                    else (None, None)
                if ok is None:
                    ctx.skip("trend gate unknown (under 110 daily bars)")
                    return
                if not ok:
                    ctx.skip(f"trend gate: ADX {adx} <= {self.p['adx_min']:g}")
                    return
            anchor = ctx.last_price
            if anchor is None:
                ctx.skip(f"no print before {self.fire}")
                return
            ctx.hline("anchor", anchor)
            ctx.move_brackets_to_fill = True
            self.entries = tuple(ctx.stop_entry(g.side, g.trigger, sl=g.sl, tp=g.tp)
                                 for g in self.legs(anchor))
            ctx.oco(*self.entries)
        elif et_time == self.cancel_et:
            for o in self.entries:
                ctx.cancel(o)
        elif et_time == self.flat_et:
            ctx.flatten("time")


class DeskStraddle(OpenStraddle):
    """A straddle the desk runs: defaults, cancel and flat come from its config."""
    desk_key = ""
    max_pts = 500.0

    def __init__(self, params: dict | None = None):
        cfg = desk_cfg(self.desk_key)
        self.cancel_et, self.flat_et = cfg.cancel_et, cfg.flat_et
        super().__init__(params)

    @classmethod
    def inputs(cls) -> list[Input]:
        c = desk_cfg(cls.desk_key)
        m = cls.max_pts
        return [
            Input("offset_pts", "Entry offset (pts)", "float", c.offset_pts, 0.0, m, 0.25),
            Input("sl_pts", "Stop loss (pts)", "float", c.sl_pts, 0.25, m, 0.25),
            Input("tp_pts", "Take profit (pts)", "float", c.tp_pts, 0.25, m, 0.25),
            Input("adx_gate", "ADX(14) trend gate", "bool", bool(c.gated)),
            Input("adx_min", "ADX threshold", "float", THRESHOLD, 0.0, 100.0, 0.5),
        ]

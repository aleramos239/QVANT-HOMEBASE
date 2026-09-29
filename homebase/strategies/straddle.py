"""Open straddles: OCO stop entries at anchor +/- offset, brackets re-priced to the fill.

Mirrors the desk: the anchor is the last print BEFORE the fire time (the timer
fires at 09:30:00.000 on the last trade received before it); the legs are exactly
engine._legs (buy stop at anchor + offset with SL trigger - sl / TP trigger + tp,
sell stop mirrored); after the fill both brackets move to the fill, like
engine._move_brackets; unfilled entries are cancelled at cancel_et; an open
position is flattened at flat_et.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from ..gate import THRESHOLD, trend_gate
from .base import Input, Strategy

MIN_GATE_BARS = 110       # = homebase.timer.MIN_GATE_BARS (pinned by a test)
GATE_BARS = 250           # = homebase.timer.GATE_BARS
MINUS = "\u2212"          # U+2212 MINUS SIGN: "Short entry -2" reads as a level, not a hyphen


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

    def session_tag(self, ctx) -> str:
        """A label for the session the anchor line carries (gc_nfpcpi: its event day).
        Empty = the anchor keeps its bare name."""
        return ""

    def on_session(self, ctx) -> None:
        self.entries = ()
        self.geometry = ()     # ((entry order, "Long"|"Short", [its hline records]), ...)

    def on_time(self, ctx, et_time: str) -> None:
        if et_time == self.fire:
            if self.p.get("adx_gate"):
                bars = ctx.daily[-GATE_BARS:]
                ok, adx = trend_gate(bars, self.p["adx_min"]) if len(bars) >= MIN_GATE_BARS \
                    else (None, None)
                if ok is None:
                    ctx.skip("trend gate unknown (under 110 daily bars)")
                    return
                # Display only (plots never reach an order): the reading the gate just judged and the
                # line it was judged against, so a skipped day says on the chart why.
                ctx.plot("ADX(14)", ctx.now_ns, adx)
                ctx.plot("ADX gate min", ctx.now_ns, self.p["adx_min"])
                if not ok:
                    ctx.skip(f"trend gate: ADX {adx} <= {self.p['adx_min']:g}")
                    return
            anchor = ctx.last_price
            if anchor is None:
                ctx.skip(f"no print before {self.fire}")
                return
            tag = self.session_tag(ctx)
            ctx.hline("anchor" + (f" \u00b7 {tag}" if tag else ""), anchor, role="anchor")
            # The whole plan, both legs, BEFORE anything fills: the entry offsets first, then each
            # leg's bracket as computed from its trigger. What the leg actually became -- the moved
            # bracket, or a " (not filled)" mark -- is written at cancel_et, once the day has ruled.
            legs = self.legs(anchor)
            off = self.p["offset_pts"]
            recs = [[ctx.hline(f"{g.side.capitalize()} entry {'+' if g.side == 'long' else MINUS}{off:g}",
                               g.trigger, role="entry")] for g in legs]
            for g, rec in zip(legs, recs):
                rec.append(ctx.hline(f"{g.side.capitalize()} SL (planned)", g.sl, role="sl"))
                rec.append(ctx.hline(f"{g.side.capitalize()} TP (planned)", g.tp, role="tp"))
            ctx.move_brackets_to_fill = True
            self.entries = tuple(ctx.stop_entry(g.side, g.trigger, sl=g.sl, tp=g.tp) for g in legs)
            ctx.oco(*self.entries)
            self.geometry = tuple(zip(self.entries, (g.side.capitalize() for g in legs), recs))
        elif et_time == self.cancel_et:
            self._resolve(ctx)
            for o in self.entries:
                ctx.cancel(o)
        elif et_time == self.flat_et:
            ctx.flatten("time")

    def _resolve(self, ctx) -> None:
        """Recording only: the day has ruled, so say so on the levels. The leg that filled gains its
        FINAL bracket -- the one the engine re-priced to the fill, exactly as the desk's
        engine._move_brackets does -- beside the "(planned)" one it was given at the trigger; the leg
        that never triggered has its three levels renamed " (not filled)"."""
        for o, side, recs in self.geometry:
            if o.status == "filled":
                # ... and the moved bracket exists from the FILL, not from this end-of-day recording
                if o.fill_sl is not None:
                    ctx.hline(f"{side} SL", o.fill_sl, role="sl")["t_ms"] = o.fill_ms
                if o.fill_tp is not None:
                    ctx.hline(f"{side} TP", o.fill_tp, role="tp")["t_ms"] = o.fill_ms
            else:
                for rec in recs:
                    rec["name"] = rec["name"].replace(" (planned)", "") + " (not filled)"
        self.geometry = ()

    def provenance(self) -> dict:
        """Item 4: the times a run actually fired/cancelled/flattened at -- the
        base class values for a research-only straddle (gc_nfpcpi); DeskStraddle
        overrides with the desk's config.json-resolved times."""
        return {"fire": self.fire, "cancel_et": self.cancel_et, "flat_et": self.flat_et}


class DeskStraddle(OpenStraddle):
    """A straddle the desk runs: defaults, cancel and flat come from its config."""
    desk_key = ""
    max_pts = 500.0

    def __init__(self, params: dict | None = None):
        cfg = desk_cfg(self.desk_key)
        self.cancel_et, self.flat_et = cfg.cancel_et, cfg.flat_et
        self._desk_cfg = cfg
        super().__init__(params)

    def provenance(self) -> dict:
        """Item 4: OpenStraddle's fire/cancel/flat times, plus the full desk
        config.json StrategyCfg this run resolved at call time -- everything
        `desk_cfg` read that is not already in the run's own `inputs`."""
        return {**super().provenance(), "desk_cfg": asdict(self._desk_cfg)}

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

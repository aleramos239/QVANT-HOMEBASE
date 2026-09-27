"""NQ 10:00 continuation — the desk's `nq10am`, through the desk's own rule.

The signal is homebase.rules.nq_10am_continuation itself (one definition): it
reads the 1-minute bars of 09:30-10:00 and, on the 09:59 bar's close, returns a
market entry with an absolute stop and a target re-derived from the fill at
RR 1:0.75. The rule has no tunable inputs, so neither does this strategy.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict
from zoneinfo import ZoneInfo

from ..feed import Bar as FeedBar
from ..rules import RULES
from .base import Strategy
from .straddle import desk_cfg

UTC = dt.timezone.utc
ET = ZoneInfo("America/New_York")


class NQ10am(Strategy):
    id = "nq10am"
    session_independent = True   # checked 2026-09-27: on_session resets its bars; config is fixed per run
    name = "NQ 10:00 Continuation"
    root = "NQ"
    desk_key = "nq10am"
    session_window = ("09:25", "16:00")
    bar_minutes = 1
    bar_window = ("09:30", "10:00")

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        self.cfg = desk_cfg(self.desk_key)
        self.rule = RULES[self.cfg.rule]

    def times(self) -> list[str]:
        return [self.cfg.flat_et]

    def on_session(self, ctx) -> None:
        self.bars: list[FeedBar] = []

    def on_bar(self, ctx, bar) -> None:
        start = dt.datetime.fromtimestamp(bar.start_ns // 1_000_000_000, UTC)
        self.bars.append(FeedBar(start, bar.o, bar.h, bar.l, bar.c, bar.v, self.root, self.bar_minutes))
        end_et = dt.datetime.fromtimestamp(bar.end_ns // 1_000_000_000, ET)
        sig = self.rule(self.bars, end_et, self.cfg)
        self._plot_gate(ctx, bar, end_et)
        if sig is None:
            return
        side = "long" if sig.side == "Buy" else "short"
        ctx.market(side, sl=sig.sl_px, tp=sig.tp_px, tp_rr=sig.tp_rr, ref=sig.ref_px)
        # The rule's own three numbers: where it decided (the 09:59 close it enters from), its
        # absolute stop, and the target it sized -- the engine re-derives that target from the
        # actual fill at RR 1:0.75, so the trade's own TP line may sit a tick or two off this one.
        ctx.hline("signal", sig.ref_px, role="entry")
        ctx.hline("stop", sig.sl_px, role="sl")
        ctx.hline("target", sig.tp_px, role="tp")

    def _plot_gate(self, ctx, bar, end_et) -> None:
        """Recording only: where the 09:30-10:00 candle CLOSED inside its own range, plotted once
        per session at 10:00 with the two quarter thresholds beside it -- the rule takes a long only
        at >= 0.75 and a short only at <= 0.25, so a no-trade day says on the chart why."""
        if (end_et.hour, end_et.minute) != (10, 0) or len(self.bars) < 25:
            return
        hi = max(b.h for b in self.bars)
        lo = min(b.l for b in self.bars)
        if hi <= lo:
            return
        ctx.plot("Close position", bar.end_ns, round((self.bars[-1].c - lo) / (hi - lo), 4))
        ctx.plot("Top quarter", bar.end_ns, 0.75)
        ctx.plot("Bottom quarter", bar.end_ns, 0.25)

    def on_time(self, ctx, et_time: str) -> None:
        if et_time == self.cfg.flat_et:
            ctx.flatten("time")

    def provenance(self) -> dict:
        """Item 4: the rule this run called plus the whole desk config.json
        StrategyCfg it resolved at call time (flat_et, warmup_bars, etc.) --
        R12 gives this strategy no tunable inputs, so this is its only runtime
        configuration, and a bundle needs it to be reproducible."""
        return {"flat_et": self.cfg.flat_et, "rule": self.cfg.rule, "desk_cfg": asdict(self.cfg)}

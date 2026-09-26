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
        sig = self.rule(self.bars, dt.datetime.fromtimestamp(bar.end_ns // 1_000_000_000, ET), self.cfg)
        if sig is None:
            return
        side = "long" if sig.side == "Buy" else "short"
        ctx.market(side, sl=sig.sl_px, tp=sig.tp_px, tp_rr=sig.tp_rr, ref=sig.ref_px)
        ctx.hline("stop", sig.sl_px)

    def on_time(self, ctx, et_time: str) -> None:
        if et_time == self.cfg.flat_et:
            ctx.flatten("time")

    def provenance(self) -> dict:
        """Item 4: the rule this run called plus the whole desk config.json
        StrategyCfg it resolved at call time (flat_et, warmup_bars, etc.) --
        R12 gives this strategy no tunable inputs, so this is its only runtime
        configuration, and a bundle needs it to be reproducible."""
        return {"flat_et": self.cfg.flat_et, "rule": self.cfg.rule, "desk_cfg": asdict(self.cfg)}

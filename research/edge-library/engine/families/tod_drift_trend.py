"""tod_drift_trend -- THE TRADE-DATE DRIFT, ONLY IN AN UPTREND (owner's /goal, 2026-10-25: "something for Asia or overnight").

tod_drift's clock entry (session start + off_min, a fixed side) with one gate and a long hold, written BEFORE any result:
  * sma_d (the main setting): the prior daily close is above (long) / at or below (short) the mean of the last sma_d daily closes.
    The daily bars are the engine's own (`ctx.daily`: the days BEFORE the trade date, sealed by month like every prior-data read), so no
    look-ahead. sma_d 0 = no gate (the control); fewer than sma_d daily bars = no trade.
  * exit_bars 400 by default (the family holds until the card's w_flat, e.g. 04:00, or the stop); tod_drift's own 6 bars cap a trade at 3 hours.
Why: the overnight drift (NY Fed SR 917) is long-biased dealer-inventory unwinding; on the in-sample months it is NQ's up-trend beta
(2022 loses, 2024-26 carry it), so the idea is to take that beta only while the trend is up, and stay flat otherwise.
tod_drift itself is untouched (test_port2 holds its methods AST-identical). Registration as ema_vwap_pb.py: join_blocks()."""
from __future__ import annotations

from .port2 import TodDrift


class TodDriftTrend(TodDrift):
    DEFAULTS = {**TodDrift.DEFAULTS, "exit_bars": 400, "sma_d": 50}
    SCHEMA = {**TodDrift.SCHEMA, "sma_d": ("int", 0, 300), "exit_bars": ("int", 1, 1000)}

    def fam_time(self, ctx, sec):
        n = int(self.p["sma_d"])
        if n and sec == self.fam_times_sec():
            cl = [d["c"] for d in self.dl[-n:]]
            if len(cl) < n or (cl[-1] > sum(cl) / n) != (self.p["dir"] == "long"):
                return
        super().fam_time(ctx, sec)

    def fam_times_sec(self):
        from l2sim import SESS
        s = self.sid
        return None if s is None else SESS[s][0] + int(self.p["off_min"]) * 60


FAMILIES = {
    "tod_drift_trend": (TodDriftTrend, {}, False,
                        "tod_drift_trend: market `dir` at session start + off_min only when the prior daily close is above (long) / at or "
                        "below (short) the mean of the last sma_d daily closes; held to the card's w_flat; 1 per session",
                        {"rationale": "The overnight drift is dealer-inventory unwinding into the first real liquidity, a long bias that on "
                                      "NQ is up-trend beta: hold the night only while the daily trend is up. Who loses: the sellers who dump "
                                      "into the thin night and the traders short against an up-trend.",
                         "complexity": 4,
                         "variants": [{"sma_d": 0}, {"sma_d": 50}, {"sma_d": 100}],
                         "roots": ("NQ",)}),
}


def join_blocks() -> None:
    """Put the family into families/blocks.py's BASES and WRAPPED (as ema_vwap_pb.py)."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()

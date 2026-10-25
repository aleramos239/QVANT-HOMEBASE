"""eve_gap_follow -- FOLLOW THE REOPEN GAP (owner's /goal, 2026-10-25: "something for Asia or overnight"; nightly trade).

tod_drift's clock entry (session start + off_min) with the side taken from the gap, written BEFORE any engine result:
  * gap = the last price at the entry minus the prior daily close (`ctx.daily`: the days BEFORE the trade date, sealed by month, so no
    look-ahead; its last bar ends 17:00 ET, the evening session reopens 18:00). gap > 0 -> long, gap < 0 -> short (it FOLLOWS the gap).
  * gap_pts (the main setting): the gap must be at least this many points either way; 0 = every night with a gap (the control).
  * exit_bars 400 by default (held to the card's w_flat or the stop), 1 per session.
Why: the news that moves the market while the book is shut or thin (the 17:00-18:00 break, the weekend) is taken up slowly by the next
session. On the in-sample months a barstore screen (pooled Sun-Thu nights, 18:00 -> 23:55, one contract, $12 cost) read +$121 a trade,
t 2.2, 5 of 6 years; the fade lost. The side was flipped from "fade" to "follow" AFTER that screen: a post-hoc direction, said here.
tod_drift itself is untouched (test_port2 keeps its methods AST-identical). Registration as tod_drift_trend.py: join_blocks()."""
from __future__ import annotations

from .port2 import TodDrift


class EveGapFollow(TodDrift):
    DEFAULTS = {**TodDrift.DEFAULTS, "dir": "both", "exit_bars": 400, "gap_pts": 0.0}
    SCHEMA = {**TodDrift.SCHEMA, "dir": ("choice", ("both", "long", "short")), "gap_pts": ("float", 0, 500), "exit_bars": ("int", 1, 1000)}

    def fam_time(self, ctx, sec):
        s, lp = self.sid, ctx.last_price
        if s is None or lp is None or not self.dl or sec != self.fam_times_sec() or not self.can_enter(ctx):
            return
        gap = lp - self.dl[-1]["c"]
        if gap == 0 or abs(gap) < float(self.p["gap_pts"]):
            return
        self._mkt(ctx, "long" if gap > 0 else "short", ref=lp)

    def fam_times_sec(self):
        from l2sim import SESS
        s = self.sid
        return None if s is None else SESS[s][0] + int(self.p["off_min"]) * 60


FAMILIES = {
    "eve_gap_follow": (EveGapFollow, {}, False,
                       "eve_gap_follow: market at session start + off_min in the direction of (last price - prior daily close) when that "
                       "gap is at least gap_pts; held to the card's w_flat; 1 per session",
                       {"rationale": "News that arrives while the book is shut or thin (the 17:00-18:00 break, the weekend) is taken up "
                                     "slowly by the next session, so the reopen gap continues. Who loses: the traders who fade the gap "
                                     "against slow-moving institutional flow.",
                        "complexity": 3,
                        "variants": [{"gap_pts": 0}, {"gap_pts": 5}, {"gap_pts": 10}],
                        "roots": ("NQ",)}),
}


def join_blocks() -> None:
    """Put the family into families/blocks.py's BASES and WRAPPED (as tod_drift_trend.py)."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()

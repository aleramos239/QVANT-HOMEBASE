"""GC 08:30 NFP straddle — the desk's `gc_nfp` (verified 2026-10-01, research/nfp-2026-10-02).

The tester twin of the desk strategy: its inputs, cancel and flat come from the desk config
(DeskStraddle), the fire moment from the config's fire_et (08:30:00). Event days: the NFP rows of
data/gc_0830_redfolder_days_2021_2026.csv, plus the config's only_dates (2026-10-02, the BLS date
that file does not hold yet) -- the same days the desk's timer trades.
"""
from __future__ import annotations

import datetime as dt

from .gc_nfpcpi import calendar
from .straddle import DeskStraddle


class GCNfp(DeskStraddle):
    id = "gc_nfp"
    session_independent = True   # day state resets in on_session; event days come from a calendar file and the config
    name = "GC 8:30 NFP Straddle"
    root = "GC"
    desk_key = "gc_nfp"
    session_window = ("08:20", "09:56")
    max_pts = 100.0

    def trades_on(self, d: dt.date) -> bool:
        return "NFP" in calendar().get(d, frozenset()) or d.isoformat() in self._desk_cfg.only_dates

    def session_tag(self, ctx) -> str:
        return "NFP"

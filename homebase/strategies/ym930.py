"""YM 9:30 straddle — the desk's `ym930`."""
from __future__ import annotations

from .straddle import DeskStraddle


class YM930(DeskStraddle):
    id = "ym930"
    session_independent = True   # checked 2026-09-27: day state resets in on_session; the ADX gate reads ctx.daily (the store)
    name = "YM 9:30 Straddle"
    root = "YM"
    desk_key = "ym930"
    session_window = ("09:25", "16:00")
    max_pts = 2000.0

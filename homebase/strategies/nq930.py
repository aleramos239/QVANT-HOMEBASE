"""NQ 9:30 straddle — the desk's `nq930`."""
from __future__ import annotations

from .straddle import DeskStraddle


class NQ930(DeskStraddle):
    id = "nq930"
    session_independent = True   # checked 2026-09-27: day state resets in on_session; the ADX gate reads ctx.daily (the store)
    name = "NQ 9:30 Straddle"
    root = "NQ"
    desk_key = "nq930"
    session_window = ("09:25", "16:00")

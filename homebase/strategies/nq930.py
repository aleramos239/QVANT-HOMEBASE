"""NQ 9:30 straddle — the desk's `nq930`."""
from __future__ import annotations

from .straddle import DeskStraddle


class NQ930(DeskStraddle):
    id = "nq930"
    name = "NQ 9:30 Straddle"
    root = "NQ"
    desk_key = "nq930"
    session_window = ("09:25", "16:00")

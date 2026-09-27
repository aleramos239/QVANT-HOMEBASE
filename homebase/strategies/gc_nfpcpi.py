"""GC 08:30 NFP + CPI straddle (research/gc_0830_redfolder_straddle_ticks.py).

Not on the desk: its defaults are the research spec — off 2 / SL 3 / TP 6,
anchor = last print before 08:30:00.000 ET, live 85 ms later, unfilled
cancelled 08:45, open position flat 09:55 — and it trades only on the event
days of data/gc_0830_redfolder_days_2021_2026.csv (ForexFactory USD high-impact
08:30 events, scraped 2026-09-25; a day's tag may join several, e.g. CLAIMS+CPI).
"""
from __future__ import annotations

import csv
import datetime as dt
from functools import lru_cache
from pathlib import Path

from .base import Input
from .straddle import OpenStraddle

CALENDAR = Path(__file__).resolve().parent / "data" / "gc_0830_redfolder_days_2021_2026.csv"
EVENTS = {"NFP+CPI": {"NFP", "CPI"}, "NFP": {"NFP"}, "CPI": {"CPI"}}


@lru_cache(maxsize=1)
def calendar() -> dict[dt.date, frozenset]:
    with open(CALENDAR, newline="") as fh:
        return {dt.date.fromisoformat(r["date"]): frozenset(r["tag"].split("+"))
                for r in csv.DictReader(fh)}


class GCNfpCpi(OpenStraddle):
    id = "gc_nfpcpi"
    session_independent = True   # checked 2026-09-27: day state resets in on_session; event days come from a fixed calendar file
    name = "GC 8:30 NFP + CPI Straddle"
    root = "GC"
    session_window = ("08:20", "09:56")
    fire, cancel_et, flat_et = "08:30:00", "08:45", "09:55"

    @classmethod
    def inputs(cls) -> list[Input]:
        return [
            Input("offset_pts", "Entry offset (pts)", "float", 2.0, 0.0, 100.0, 0.1),
            Input("sl_pts", "Stop loss (pts)", "float", 3.0, 0.1, 100.0, 0.1),
            Input("tp_pts", "Take profit (pts)", "float", 6.0, 0.1, 200.0, 0.1),
            Input("events", "Events", "choice", "NFP+CPI", choices=tuple(EVENTS)),
        ]

    def trades_on(self, d: dt.date) -> bool:
        return bool(calendar().get(d, frozenset()) & EVENTS[self.p["events"]])

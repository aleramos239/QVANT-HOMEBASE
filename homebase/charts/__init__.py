"""Live charts: the chart half of the homebase terminal (Build 1).

Runs as its OWN process (python -m homebase.charts, port 8852) so chart work
can never delay an order or crash the trading engine. Nothing in this
package talks to the broker's order API: trading from the chart goes to the
desk (:8850) through desk.py, which holds the only key.
Spec: docs/superpowers/specs/2026-09-25-live-charts-design.md
"""
from __future__ import annotations

import datetime as dt
import os

PORT = 8852
# ET wall-clock window around the 9:30 fire in which this process sends no
# optional md requests (gap refills, refused-symbol retries)
QUIET = (dt.time(9, 20), dt.time(9, 35))
# the live recorder captures the nightly tick archive's symbols
# (homebase.ticks.ROOTS), so the two can be compared and the nightly job can
# later shrink to a gap-filler — plus Bitcoin, which trades 24/7: the nightly
# job's weekday 18:00 -> 17:00 fetch cannot capture it, so this service is
# its only recorder
DEFAULT_ROOTS = ("NQ", "ES", "YM", "RTY", "GC", "SI", "CL", "ZN", "NG", "HG", "BTC")
# whose md socket feeds the charts: "demo" = the Apex eval login (default;
# confirmed by the Task 14 spike), "live" = the live account's login
# ("LIVE" or " live" means live; anything unrecognised is "demo", which is what
# it always silently got)
MD_ENV = os.environ.get("HOMEBASE_CHARTS_MD", "demo").strip().lower()
if MD_ENV not in ("live", "demo"):
    MD_ENV = "demo"


def parse_depth_roots(value: str | None) -> tuple[str, ...]:
    """HOMEBASE_DEPTH_ROOTS: comma-separated roots; unset = NQ, ES; "" = none."""
    if value is None:
        value = "NQ,ES"
    return tuple(r.strip().upper() for r in value.split(",") if r.strip())


# Level 2: the roots whose depth is recorded to ~/futures_depth (and so always
# subscribed). Other roots get depth only while a page shows them.
# Spec: docs/superpowers/specs/2026-09-27-charts-depth-design.md
DEPTH_RECORD_ROOTS = parse_depth_roots(os.environ.get("HOMEBASE_DEPTH_ROOTS"))

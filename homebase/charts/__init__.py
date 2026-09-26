"""Live charts: the chart half of the homebase terminal (Build 1).

Runs as its OWN process (python -m homebase.charts, port 8852) so chart work
can never delay an order or crash the trading engine. Nothing in this
package places, modifies or cancels orders.
Spec: docs/superpowers/specs/2026-09-25-live-charts-design.md
"""
from __future__ import annotations

import os

PORT = 8852
# the live recorder captures the same symbols as the nightly tick archive
# (homebase.ticks.ROOTS), so the two can be compared and the nightly job can
# later shrink to a gap-filler
DEFAULT_ROOTS = ("NQ", "ES", "YM", "RTY", "GC", "SI", "CL", "ZN", "NG", "HG")
# whose md socket feeds the charts: "demo" = the Apex eval login (default;
# confirmed by the Task 14 spike), "live" = the live account's login
MD_ENV = os.environ.get("HOMEBASE_CHARTS_MD", "demo")

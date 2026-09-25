"""Live charts: the chart half of the homebase terminal (Build 1).

Runs as its OWN process (python -m homebase.charts, port 8852) so chart work
can never delay an order or crash the trading engine. Nothing in this
package places, modifies or cancels orders.
Spec: docs/superpowers/specs/2026-09-25-live-charts-design.md
"""
from __future__ import annotations

import os

PORT = 8852
DEFAULT_ROOTS = ("NQ", "ES", "YM")
# whose md socket feeds the charts: "demo" = the Apex eval login (default;
# confirmed by the Task 14 spike), "live" = the live account's login
MD_ENV = os.environ.get("HOMEBASE_CHARTS_MD", "demo")

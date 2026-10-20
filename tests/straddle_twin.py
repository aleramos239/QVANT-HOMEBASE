"""The old built-in NQ 9:30 straddle (nq930), kept for the tests only: the tester engine's golden and fill tests run on it.

The app no longer ships it (the owner, 2026-10-20: the Desk's straddles are Lab strategies now). Its defaults are the old
shipped ones (offset 5 / stop 5 / target 15, ADX gate on); conftest.py registers it as "nq930" for every test.
"""
from __future__ import annotations

from homebase.gate import THRESHOLD
from homebase.strategies.base import Input
from homebase.strategies.straddle import OpenStraddle


class NQ930(OpenStraddle):
    id = "nq930"
    session_independent = True
    name = "NQ 9:30 Straddle"
    root = "NQ"
    session_window = ("09:25", "16:00")

    @classmethod
    def inputs(cls) -> list[Input]:
        return [
            Input("offset_pts", "Entry offset (pts)", "float", 5.0, 0.0, 500.0, 0.25),
            Input("sl_pts", "Stop loss (pts)", "float", 5.0, 0.25, 500.0, 0.25),
            Input("tp_pts", "Take profit (pts)", "float", 15.0, 0.25, 500.0, 0.25),
            Input("adx_gate", "ADX(14) trend gate", "bool", True),
            Input("adx_min", "ADX threshold", "float", THRESHOLD, 0.0, 100.0, 0.5),
        ]

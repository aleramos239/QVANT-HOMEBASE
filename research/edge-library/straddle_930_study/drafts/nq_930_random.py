"""NQ 9:30 random-direction control for the 9:30 straddle (2026-10-31). A DRAFT strategy for the Homebase Strategy Tester.

Same clock, same ATR stop and RR target (set as run controls), same 12:55 cancel and 15:55 flat as draft_nq_930_straddle,
but the side is a coin flip per day (seeded by the date and `seed`, so a run repeats).
mode market : a market order at 09:30:00 in the coin's direction.
mode stop   : one stop entry only, offset_pts past the last print at 09:30:00, in the coin's direction (fills only if price gets there).
"""
from __future__ import annotations

import random

from homebase.strategies.base import Input, Strategy


class NQ930Random(Strategy):
    id = "draft_nq_930_random"
    name = "NQ 9:30 Random Side"
    root = "NQ"
    own_stop = False
    session_window = ("09:25", "16:00")
    session_independent = True
    fire, cancel_et, flat_et = "09:30:00", "12:55", "15:55"

    @classmethod
    def inputs(cls):
        return [
            Input("mode", "Entry", "choice", "market", None, None, None, ("market", "stop")),
            Input("seed", "Coin seed", "int", 1, 0, 1000, 1),
            Input("offset_pts", "Stop entry offset (pts, mode stop)", "float", 5.0, 0.0, 500.0, 0.25),
        ]

    def times(self):
        return [self.fire, self.cancel_et, self.flat_et]

    def on_session(self, ctx):
        self.entry = None

    def on_time(self, ctx, et_time):
        if et_time == self.fire:
            anchor = ctx.last_price
            if anchor is None:
                ctx.skip(f"no print before {self.fire}")
                return
            side = "long" if random.Random(f"{self.p['seed']}-{ctx.date}").random() < 0.5 else "short"
            if self.p["mode"] == "market":
                ctx.market(side)
            else:
                off = self.p["offset_pts"]
                ctx.move_brackets_to_fill = True
                self.entry = ctx.stop_entry(side, anchor + off if side == "long" else anchor - off)
        elif et_time == self.cancel_et:
            if self.entry is not None:
                ctx.cancel(self.entry)
        elif et_time == self.flat_et:
            ctx.flatten("time")

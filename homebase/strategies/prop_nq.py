"""The 3 NQ prop strategies (research 2026-09-29/30, desk review 2026-10-01), as tester strategies.

Same definitions the desk fires (homebase/levels.py + homebase/atrbars.py + config kind "levels"), so a
backtest and a live fire cannot drift apart:

  nq_nyam_flex / nq_nyam_pro   09:30:00  buy/sell stop at the last print before the open +/- 0.25 x ATR30,
                               stop 3 x ATR30 from the trigger, cancel 10:55, flat 11:00
  nq_orb_pro                   11:05:00  buy stop 11:00-11:05 high + 1 tick / sell stop low - 1 tick,
                               stop 3 x ATR5 from the trigger, cancel 13:25, flat 13:30
  nq_pm_flex                   13:30:00  last print +/- 1.0 x ATR30, stop 3 x ATR30, cancel 15:53, flat 15:58

ATR(14, Wilder) over the N-minute bars of the ET day so far, restarting at 00:00 ET (so the session window
opens at 00:00).  One OCO pair per day; after the fill the stop and the take move to the fill.  The TAKE is the
daily rule: a net-dollar target (`take_usd`, after the round-trip fee) turned into points from the fill for the
run's qty (risk.take_points).  The desk's day_take is the same price; the tester's limit needs one tick of
penetration where the desk's watcher acts on a touch, and the desk sizes target_take per account from its eval
standing -- the tester has no account, so a "target_take" strategy's take_usd is its first-day level (the eval
target).  NQ minis only: the tester's $4 round trip per contract is the mini's.

The tester's order qty is the run's qty (the tester sizes the account); the desk takes qty from the book.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
from dataclasses import asdict

from ..atrbars import TickBars
from ..contracts import point_value, tick_size
from ..levels import compute_geometry, is_early_close_skip
from ..dayrules import ceil_to_tick, take_points
from .base import Input, Strategy
from .straddle import desk_cfg

DEFAULT_PRO_FIRST_DAY_TAKE = 3000.0     # LucidPro 50K target: a target_take-only strategy's day-1 level


class LevelsStrategy(Strategy):
    root = "NQ"
    desk_key = ""
    session_window = ("00:00", "16:10")      # the ATR restarts at 00:00 ET
    bar_minutes = 1
    session_independent = True               # on_session resets every piece of day state (each subclass says so too)

    def __init__(self, params: dict | None = None):
        c = self._desk = desk_cfg(self.desk_key)
        self.fire, self.cancel_et, self.flat_et = c.fire_et, c.cancel_et, c.flat_et
        super().__init__(params)
        # the run's inputs over the desk's StrategyCfg: compute_geometry reads the same field names
        self.cfg = dataclasses.replace(
            c, off_atr=self.p.get("off_atr", c.off_atr), sl_atr=self.p["sl_atr"], atr_tf=self.p["atr_tf"],
            or_min=self.p.get("or_min", c.or_min), fee_rt=self.p["fee_rt"])

    @classmethod
    def inputs(cls) -> list[Input]:
        c = desk_cfg(cls.desk_key)
        out = []
        if c.shape == "atr_straddle":
            out.append(Input("off_atr", "Entry offset (x ATR)", "float", c.off_atr, 0.0, 10.0, 0.05))
        else:
            out.append(Input("or_min", "Opening range (min)", "int", c.or_min, 1, 60, 1))
        take = c.day_take if c.day_take > 0 else DEFAULT_PRO_FIRST_DAY_TAKE
        out += [
            Input("atr_tf", "ATR bar (min)", "int", c.atr_tf, 1, 60, 1),
            Input("sl_atr", "Stop (x ATR from the trigger)", "float", c.sl_atr, 0.25, 20.0, 0.25),
            Input("take_usd", "Take, net $ after fees (day_take / target_take)", "float", take, 0.0, 20000.0, 50.0),
            Input("fee_rt", "Fee per contract per round turn ($)", "float", c.fee_rt, 0.0, 20.0, 0.5),
        ]
        return out

    def times(self) -> list[str]:
        return [self.fire, self.cancel_et, self.flat_et]

    def trades_on(self, d: dt.date) -> bool:
        return not (self._desk.skip_early_close and is_early_close_skip(self.root, d, self._desk.flat_et))

    def on_session(self, ctx) -> None:
        self.tb = TickBars(ctx.date)
        self.entries = ()

    def on_bar(self, ctx, bar) -> None:
        self.tb.add_minute(bar.start_ns // 1_000_000, bar.o, bar.h, bar.l, bar.c, bar.v)

    def on_time(self, ctx, et_time: str) -> None:
        if et_time == self.fire:
            self._arm(ctx)
        elif et_time == self.cancel_et:
            for o in self.entries:
                ctx.cancel(o)
        elif et_time == self.flat_et:
            ctx.flatten("time")

    def _arm(self, ctx) -> None:
        tick = tick_size(self.root) or 0.25
        fire_ms = ctx.now_ns // 1_000_000
        geo, why = compute_geometry(self.cfg, self.tb, fire_ms, tick)
        if geo is None:
            ctx.skip(why)
            return
        take = self.p["take_usd"]
        pv = point_value(self.root) or 20.0
        tp = (take_points(take, ctx.qty, pv, self.p["fee_rt"], tick) if take > 0
              else ceil_to_tick(self._desk.tgt_r * geo.sl_pts, tick))
        if geo.anchor is not None:
            ctx.hline("anchor", geo.anchor, role="anchor")
        else:
            ctx.hline("range high", geo.range_hi, role="level")
            ctx.hline("range low", geo.range_lo, role="level")
        ctx.hline("Long entry", geo.upper, role="entry")
        ctx.hline("Short entry", geo.lower, role="entry")
        ctx.hline("Long SL (planned)", geo.upper - geo.sl_pts, role="sl")
        ctx.hline("Short SL (planned)", geo.lower + geo.sl_for("Sell"), role="sl")
        ctx.hline("Long take (planned)", geo.upper + tp, role="tp")
        ctx.hline("Short take (planned)", geo.lower - tp, role="tp")
        ctx.plot("ATR", ctx.now_ns, geo.atr)
        ctx.move_brackets_to_fill = True
        buy = ctx.stop_entry("long", geo.upper, sl=geo.upper - geo.sl_pts, tp=geo.upper + tp)
        sell = ctx.stop_entry("short", geo.lower, sl=geo.lower + geo.sl_for("Sell"), tp=geo.lower - tp)
        ctx.oco(buy, sell)
        self.entries = (buy, sell)

    def provenance(self) -> dict:
        return {"fire": self.fire, "cancel_et": self.cancel_et, "flat_et": self.flat_et,
                "desk_cfg": asdict(self._desk)}


class NQNyamFlex(LevelsStrategy):
    id, name, desk_key = "nq_nyam_flex", "NQ NYAM Straddle (Flex eval)", "nq_nyam_flex"
    session_independent = True   # checked 2026-10-01: on_session builds a fresh TickBars; the ATR restarts at 00:00 ET


class NQNyamPro(LevelsStrategy):
    id, name, desk_key = "nq_nyam_pro", "NQ NYAM Straddle (Pro eval)", "nq_nyam_pro"
    session_independent = True   # checked 2026-10-01: on_session builds a fresh TickBars; the ATR restarts at 00:00 ET


class NQOrbPro(LevelsStrategy):
    id, name, desk_key = "nq_orb_pro", "NQ 11:05 ORB (Pro funded)", "nq_orb_pro"
    session_independent = True   # checked 2026-10-01: on_session builds a fresh TickBars; the ATR restarts at 00:00 ET


class NQPmFlex(LevelsStrategy):
    id, name, desk_key = "nq_pm_flex", "NQ PM Straddle (Flex funded)", "nq_pm_flex"
    session_independent = True   # checked 2026-10-01: on_session builds a fresh TickBars; the ATR restarts at 00:00 ET

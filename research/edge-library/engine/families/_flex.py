"""_flex -- THE OPEN LAYER (owner 2026-10-11: "use any timeframe, any indicator in any setting, any time window, everything").

Nine settings are put on EVERY wrapped family (families/blocks.py WRAPPED, the classes a pipeline card runs), by adding `FlexMods` to the
front of each class's bases at import. Nothing of a hashed file is edited (l2sim, l2ref, blocks, the family's module, indicators ... are
what runner.code() stamps): no earlier store or lock is marked "written by other code", and every setting is OFF by default, so a
family without them is trade for trade what it was (engine/tests/test_flex.py holds that, family by family, against a fresh wrap).

  w_start, w_end   "HH:MM" Globex-day clock (18:00-23:59 = the evening before; "" = none). An entry is DECIDED (a market order at a tf
                   close, a bracket or a limit at its placement) at or after w_start and before w_end. It clips the family's own
                   window; it cannot widen it: the session pass is the outer edge, and the table that judges a trade is its entry's pass.
  days             a day rule of flexind.DAY_RULES (news, nonews, tier1, nfp, cpi, fomc, mon .. fri, month_end, opex ...). A day outside
                   the rule is not run at all (trades_on): fewer tape loads, and the random controls draw on the same days by construction.
  gate             off | an indicator of flexind.KINDS, read at the decision on the closed tf bars since the restart, with g_n (its main
                   period), g_m (the slow period: ema_x, macd), g_s (the macd signal), g_lvl (the line: flexind's table), g_side with | against.
                   No value yet (too few bars): both sides blocked, as the filter blocks do.
  rel_dir          off | with | against (owner 2026-10-15). On the SECOND inflation release of a week (CPI after PPI or PPI after CPI,
                   flexind.first_release) only the side of the FIRST release's candle may trade: `with` = its direction, `against` = the
                   other. The candle is the price move from just before 08:30:00 to `rel_min` (1 | 5 | 15 | 30) minutes after, read from
                   cache/relcandle_<ROOT>.npz (relcandle.py: build days only). Any other day is not run; a first candle that did not move,
                   or a first-release day with no tape, blocks both sides. Off: nothing changes.

HOMEBASE_FLEX=0 in the environment switches the layer off (the parity tests and a store check use it); the settings then do not exist.
"""
from __future__ import annotations

import os

import flexind as FI
import relcandle as RC
from l2sim import NS, clock_sec

KEYS = ("w_start", "w_end", "days", "gate", "g_n", "g_m", "g_s", "g_lvl", "g_side", "rel_dir", "rel_min")


def window(txt: str, what: str):
    """A window edge "HH:MM" -> seconds after 00:00 ET of the trade date (negative: the evening before); "" -> None."""
    t = (txt or "").strip()
    if not t:
        return None
    try:
        return clock_sec(t if t.count(":") else f"{t}:00")
    except Exception as e:                               # noqa: BLE001 - one message for every bad shape
        raise ValueError(f"{what}: a clock time HH:MM on the Globex day (got {txt!r}): {e}") from None


class FlexMods:
    """The settings of the open layer (module docstring), in front of a wrapped family class."""
    DEFAULTS = {"w_start": "", "w_end": "", "days": "all", "gate": "off", "g_n": 14, "g_m": 26, "g_s": 9, "g_lvl": 0.0, "g_side": "with",
                "rel_dir": "off", "rel_min": 5}
    SCHEMA = {"w_start": ("str",), "w_end": ("str",), "days": ("choice", FI.DAY_RULES), "gate": ("choice", ("off",) + FI.KINDS),
              "g_n": ("int", 1, 500), "g_m": ("int", 1, 500), "g_s": ("int", 1, 500), "g_lvl": ("float", -1000.0, 1000.0),
              "g_side": ("choice", ("with", "against")), "rel_dir": ("choice", ("off", "with", "against")),
              "rel_min": ("choice", RC.MINUTES)}

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        p = self.p
        self._fx_a, self._fx_b = window(p["w_start"], "w_start"), window(p["w_end"], "w_end")
        if self._fx_a is not None and self._fx_b is not None and self._fx_b <= self._fx_a:
            raise ValueError(f"w_end {p['w_end']!r} is not after w_start {p['w_start']!r}")
        self._fx_gi = None
        self._fx_rel = 0                                 # the first release's direction on a rel_dir day (on_session)
        if p["gate"] != "off":
            FI.make(p["gate"], p["g_n"], p["g_m"], p["g_s"])     # a bad period is refused at construction

    def trades_on(self, d) -> bool:
        iso = d.isoformat()
        return (super().trades_on(d) and FI.day_ok(iso, self.p["days"])
                and (self.p["rel_dir"] == "off" or FI.first_release(iso) is not None))

    def on_session(self, ctx):
        super().on_session(ctx)
        p = self.p
        self._fx_gi = FI.make(p["gate"], p["g_n"], p["g_m"], p["g_s"]) if p["gate"] != "off" else None
        self._fx_rel = 0
        if p["rel_dir"] != "off":
            first = FI.first_release(ctx.date.isoformat())
            self._fx_rel = (RC.direction(ctx.root, first, int(p["rel_min"])) or 0) if first is not None else 0

    def fam_update(self, ctx):
        super().fam_update(ctx)
        g = self._fx_gi
        if g is not None:                                # one closed tf bar at a time: the value at a decision never sees an open bar
            g.update(self.O[-1], self.H[-1], self.L[-1], self.C[-1], self.V[-1], self.vw() if self.p["gate"] == "vwap_dev" else None)

    def allowed(self, side):
        if not super().allowed(side):
            return False
        if self._fx_a is not None or self._fx_b is not None:
            t = (self._cx.now_ns - self.t0) // NS
            if (self._fx_a is not None and t < self._fx_a) or (self._fx_b is not None and t >= self._fx_b):
                return False
        if self.p["rel_dir"] != "off":
            r = self._fx_rel                             # 0 = the first candle did not move / has no tape: neither side
            if r == 0 or (side == "long") != ((r > 0) == (self.p["rel_dir"] == "with")):
                return False
        g = self._fx_gi
        return g is None or FI.gate_ok(g, side, self.p["g_side"], self.p["g_lvl"])


def apply() -> int:
    """Put FlexMods in front of every wrapped class that has not got it yet -> how many were changed. Idempotent; a class keeps its module,
    its qualified name and its pickle reference, so a store's fingerprint (class path + inputs) is what it was."""
    if os.environ.get("HOMEBASE_FLEX") == "0":
        return 0
    from . import blocks
    n = 0
    for cls in blocks.WRAPPED.values():
        if FlexMods not in cls.__mro__:
            cls.__bases__ = (FlexMods,) + cls.__bases__
            n += 1
    return n

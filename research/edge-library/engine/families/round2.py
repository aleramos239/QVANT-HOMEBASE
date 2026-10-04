"""round2 -- EDGE_SPEC "STAGE 4 -- EVENT ENTRY VARIANTS": two ways into a scheduled release burst, written from the spec text
before any result. No Level-2 feature is read (FEATURES = ()): NQ, ES and GC, 1 contract, hold_to = 'day' (flat 15:58 ET).
Both run on EVERY trading day at the clock time; the release-day filter (groups A / B / C) is laid on later by the analyst.

    W straddle_wide   time-fired (tf 30)   one registry entry per clock time: straddle_wide_0830 / _1000
    D event_dir       time-fired (tf 30)   one registry entry per clock time: event_dir_0830 / _1000

HOW EACH WRITTEN RULE IS READ (fixed here, before any run; nothing below was chosen after a result):
  * W  "the same OCO bracket, farther away" = round1's straddle_tight with the written offsets (OFF, A / B / C / D per
       root). Placed at the clock time minus 1 second around the last print before that instant; live after the engine's
       order delay (85 ms). "unfilled legs cancel after 5 min" = 5 minutes after it was placed (as N7). Entries only until
       the next listed time / session end (08:30 -> 09:30, 10:00 -> 11:00).
       "stop {0.5, 1, 1.5} x offset" = the stop distance from the fill is that multiple of the cell's own entry offset
       in points (stop_mode 'offx', this class only: stop_val = the multiple). 4 offsets x (3 stops x 3 targets) = 36 cells.
       NULL (`shift_seed` 1, 2): the same bracket at a seeded random minute within +/- 90 min (l2ref.StraddleT).
  * D  anchor = the last print STRICTLY BEFORE the release time T (read at the T event; none in the day window -> no trade).
       Decision instant = T + X. Decision price = the last print stamped AT OR BEFORE T + X. No print in [T, T + X] ->
       the decision price is the anchor print itself -> no move -> no trade. A move = any difference (prices sit on the
       tick grid: at least 1 tick). Up -> ONE market long, down -> ONE market short, sent at T + X: it is live after the
       engine's order delay (85 ms; 250 ms under stress) and fills at the first print from then on. One decision per day
       per clock time, max 1 trade, no retry. The stop reference price is the decision price; ATR stops use ATR30
       (time-fired). X <= 2 s = "tick direction", 5 s / 15 s = "lower timeframe candle close", 60 s = the 1-minute candle
       close: each is simply the decision at T + X.
       NULL (`shift_seed` 1, 2 -- the engine's name for the seed of a time-fired family's null, as late_mom): the SAME
       entry at the SAME instant on the SAME days (a day without a move stays without a trade), direction = a seeded coin
       flip per (seed, date, clock time): the same for every X and every exit cell.
  * SUB-SECOND CLOCK. X = 0.25 s / 0.5 s need an event between two whole seconds: l2sim.et_ns keeps a fraction of a second
       ('HH:MM:SS.ffffff'; a whole-second time gives the value it always gave). The decision time is always written with
       its fraction, so the Template's whole-second clock never sees it (EventDir.on_time takes it).

COMPLEXITY = rules + free parameters (as round1). Tests: tests/test_round2.py."""
from __future__ import annotations

import random

import numpy as np

import l2ref
import l2sim as S
from l2sim import Template, _hms

EVENT_TIMES = ("08:30", "10:00")                    # EDGE_SPEC STAGE 4 clock times, ET
WIDE_OFFS = ("A", "B", "C", "D")
EVENT_X = (0.25, 0.5, 1.0, 2.0, 5.0, 15.0, 60.0)    # seconds after the release time


# ---- W straddle_wide ------------------------------------------------------------------------------------------------------
class StraddleWide(l2ref.StraddleT):
    """W (module docstring): the engine's clock straddle (l2ref.StraddleT: OCO stop entries around the last print, the
    time-shuffle null through shift_seed) placed 1 second before the clock time, entry offset `off` = A / B / C / D points
    of the root (OFF), unfilled legs cancelled 5 minutes later, its own exit cells (unit_exits): stop = STOP_X x the
    offset (stop_mode 'offx'), target TGT x the stop."""
    OFF = {"NQ": (10.0, 15.0, 20.0, 30.0), "ES": (2.5, 4.0, 5.0, 8.0), "GC": (2.0, 3.0, 4.0, 6.0)}
    STOP_X = (0.5, 1.0, 1.5)
    TGT = (1.0, 2.0, 3.0)
    DEFAULTS = {"off": "B", "cancel_min": 5, "stop_mode": "offx", "stop_val": 1.0}
    SCHEMA = {"off": ("choice", WIDE_OFFS), "stop_mode": ("choice", ("atr", "pts", "struct", "pct", "offx"))}

    @classmethod
    def unit_exits(cls, root):
        return [{"stop_mode": "offx", "stop_val": m, "tgt_r": r} for m in cls.STOP_X for r in cls.TGT]

    def on_session(self, ctx):
        self.p["off_mode"], self.p["off_val"] = "pts", self.OFF[ctx.root][WIDE_OFFS.index(self.p["off"])]
        super().on_session(ctx)

    def _dist(self, ctx, ref, struct):
        if self.p["stop_mode"] == "offx":           # the stop is a multiple of this cell's entry offset (points)
            return max(self.p["stop_val"] * self.p["off_val"], 2 * ctx.tick)
        return super()._dist(ctx, ref, struct)


def _wide_entry(t: str) -> tuple:
    at = _hms(S.clock_sec(t) - 1)                   # armed 1 s before the clock time
    flat = S.clock_flat(t)                          # entries only until the next listed time / the session end
    return (StraddleWide, {"at": at, "flat": flat}, True,
            f"W straddle_wide {t} ET: OCO stop entries at last price +/- off points (A / B / C / D: NQ 10 / 15 / 20 / 30, ES 2.5 / "
            f"4 / 5 / 8, GC 2 / 3 / 4 / 6), placed at {at}, unfilled legs cancelled 5 min later, entries until {flat[:5]}; own "
            "exits: stop 0.5 / 1 / 1.5 x the offset (stop_mode offx) x target 1:1 / 1:2 / 1:3; null = the same bracket at random "
            "minutes (shift_seed). Runs on every day: the release-day filter (A / B / C) is the analyst's. CARD: fill realism "
            "(1 / 5 / 25 ms, 2 ticks + 250 ms) and the late-cancel double-fill probe"
            + ("; 2024 was already read for close kin of this unit on NQ and GC (EDGE_SPEC STAGE 4: the analyst flags it)"
               if t == "08:30" else ""),
            {"rationale": "A scheduled release reprices the market in one burst; a bracket placed farther from the price is hit "
                          f"only by a real burst and does not need a fill at a tight stop price ({t} ET).",
             "complexity": 6,                       # bracket at the time . cancel after 5 min . flat by 15:58 + time, offset, stop
             "variants": [{"off": k} for k in WIDE_OFFS]})


# ---- D event_dir ----------------------------------------------------------------------------------------------------------
class EventDir(Template):
    """D (module docstring). At the release time `at` the anchor = the last print strictly before it. At at + x seconds:
    the last print at or before that instant vs the anchor -> ONE market order in the direction of the move; no move = no
    trade. One trade a day. shift_seed > 0 = the NULL: the same entry on the same days with a seeded random direction."""
    DEFAULTS = {"at": "08:30", "x": 1.0, "tf": "30", "max_tr": 1, "shift_seed": 0}
    SCHEMA = {"at": ("choice", EVENT_TIMES), "x": ("choice", EVENT_X), "tf": ("choice", ("30",)),
              "shift_seed": ("int", 0, 1000000)}
    SCREEN_TFS = ("30",)
    FEATURES = ()

    def at_s(self) -> int:
        return S.clock_sec(self.p["at"])

    def x_ns(self) -> int:
        return int(round(float(self.p["x"]) * S.NS))

    def dec_time(self) -> str:
        """The decision instant at + x as 'HH:MM:SS.ffffff' (always with its fraction: not a time of the Template's clock)."""
        whole, frac = divmod(self.x_ns(), S.NS)
        if frac % 1000:
            raise ValueError(f"event_dir: x {self.p['x']} s is finer than a microsecond")
        return "%s.%06d" % (_hms(self.at_s() + whole), frac // 1000)

    def fam_sessions(self):
        return {"t": (self.at_s(), S.clock_sec(S.clock_flat(self.p["at"])))}

    def fam_filter(self, ids):
        return ["t"]

    def fam_times(self):
        return [_hms(self.at_s()), self.dec_time()]

    def fam_day(self, ctx):
        self.anchor = None                          # the day's anchor print; set at the release time
        self.dec_px = None                          # the decision print (kept for the tests)

    def fam_time(self, ctx, sec):
        if self.sid == "t" and sec == self.at_s():
            self.anchor = ctx.last_price            # the last print STRICTLY before the release time

    def on_time(self, ctx, et_time):
        if et_time != self.dec_time():
            return super().on_time(ctx, et_time)
        self.decide(ctx)

    @staticmethod
    def last_at(ctx):
        """The last print stamped at or before the current event time (ctx.last_price is strictly before it)."""
        s = ctx._s
        j = s.i + int(np.searchsorted(s.ts[s.i:s.hi], ctx.now_ns, side="right"))
        return float(s.px[j - 1]) if j > s.lo else None

    def decide(self, ctx):
        a = self.anchor
        if self.sid != "t" or a is None or not self.can_enter(ctx):
            return
        p = self.dec_px = self.last_at(ctx)
        if p is None or abs(p - a) < ctx.tick / 2:  # no move since the last print before the release: no trade
            return
        up = p > a
        if self.p["shift_seed"]:
            up = random.Random("%s|%s|event_dir|%s" % (self.p["shift_seed"], self.day, self.p["at"])).random() < 0.5
        self._mkt(ctx, "long" if up else "short", ref=p)


def _dir_entry(t: str) -> tuple:
    return (EventDir, {"at": t}, False,
            f"D event_dir {t} ET: anchor = the last print before {t}:00; at {t}:00 + x (x = 0.25 / 0.5 / 1 / 2 / 5 / 15 / 60 s) the "
            "last print at or before that instant vs the anchor -> ONE market order in the direction of the move (live after "
            "the order delay), no move = no trade, one trade a day; exits = the 32-cell menu; null (shift_seed) = the same "
            "entry with a random direction. One direction, no opposite orders. Runs on every day: the release-day filter "
            "(A / B / C) is the analyst's. CARD: market fill at the first print after the order is live + 1 tick, stress 2 "
            "ticks + 250 ms, the 1 / 5 / 25 ms probe",
            {"rationale": "A scheduled release reprices the market in one burst; the first move after the release shows its "
                          f"direction, and one market order that way needs no resting bracket ({t} ET).",
             "complexity": 5,                       # direction of the move since the anchor . one market order, one trade . flat by 15:58 + time, x
             "variants": [{"x": x} for x in EVENT_X]})


FAMILIES = {}
FAMILIES.update({f"straddle_wide_{t.replace(':', '')}": _wide_entry(t) for t in EVENT_TIMES})
FAMILIES.update({f"event_dir_{t.replace(':', '')}": _dir_entry(t) for t in EVENT_TIMES})

# entry windows, ET seconds after 00:00 of the trade date [first, last]: the smoke's "entries outside the window" count.
# W: from the second the bracket is placed to its 5-minute cancel. D: from the release second to 2 minutes after it (the
# latest decision is 60 s after; the market order fills at the first print from then on).
ENTRY_WINDOWS = {**{f"straddle_wide_{t.replace(':', '')}": (S.clock_sec(t) - 1, S.clock_sec(t) + 299) for t in EVENT_TIMES},
                 **{f"event_dir_{t.replace(':', '')}": (S.clock_sec(t), S.clock_sec(t) + 119) for t in EVENT_TIMES}}

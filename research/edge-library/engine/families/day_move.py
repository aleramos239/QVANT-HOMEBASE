"""day_move -- LATE-DAY MOMENTUM: the day's move since the open carried into the close (Gao, Han, Li and Zhou 2018, "Market intraday
momentum": the first half-hour's return predicts the last half-hour's; here the whole 09:30-`at` move). The research workflow's idea 28,
built for the hunt's Amendment O (batch 4b), written from the rule below before any result. No Level-2 feature (FEATURES = ()): NQ, ES
and GC, 1 contract, hold_to = 'day' (flat 15:58 ET); the exits are the sheet's / the heat map's (no structure level).

THE RULE (New York time):
  * At the clock time `at` (15:00; 14:30 / 14:45 / 15:15): MOVE = the close of the last 1-minute bar before `at` minus the 09:30 OPEN
    (the open of the first 1-minute bar at or after 09:30; that bar more than 5 minutes late = no trade today).
  * RANGE = the simple average of high - low over the 20 daily bars before today (ctx.daily: prior trade dates only); fewer than 20 = no
    trade.
  * |MOVE| >= k x RANGE -> a market order WITH the move's sign at `at` (it fills at the next print); one trade a day (max_tr 1); stop and
    target the sheet's, measured from the move's close and re-priced to the fill; flat at the day's flatten time if neither is hit.
SESSION: the pm pass only (fam_filter), the one instance whose window holds `at`. NO LOOK-AHEAD: the move is read from closed 1-minute
bars and the range from prior days' bars; nothing after `at` is read (tests).
REGISTRATION as onr.py / xflow.py: join_blocks() puts the family into families/blocks.py's BASES and WRAPPED (blocks.py is not edited).
Tests: engine/tests/test_day_move.py."""
from __future__ import annotations

from l2sim import Template, _hms, _sec

OPEN_S = 34200                                      # 09:30 ET, seconds after 00:00 ET
OPEN_TOL_S = 300                                    # the 09:30 open's first minute bar may start at most 5 minutes late
ATS = ("14:30", "14:45", "15:00", "15:15")
RANGE_DAYS = 20


class DayMove(Template):
    """day_move (module docstring). No state: everything is read at `at` from self.M (the day's 1-minute bars) and self.dl."""
    DEFAULTS = {"k": 0.25, "at": "15:00", "max_tr": 1}
    SCHEMA = {"k": ("float", 0.05, 2.0), "at": ("choice", ATS), "max_tr": ("int", 1, 5)}
    SCREEN_TFS = ("1", "5", "15", "30")
    FEATURES = ()

    def fam_filter(self, ids):
        return [s for s in ids if s == "pm"]

    def fam_times(self):
        return [_hms(_sec(self.p["at"]))]

    def fam_time(self, ctx, sec):
        if sec != _sec(self.p["at"]) or not self.can_enter(ctx) or len(self.dl) < RANGE_DAYS:
            return
        first = next((m for m in self.M if m[0] >= OPEN_S), None)       # the first 1-minute bar from 09:30: its open
        c = self.mc(OPEN_S, sec)                                        # the last 1-minute close before `at`
        if first is None or first[0] - OPEN_S > OPEN_TOL_S or c is None:
            return
        rng = sum(r["h"] - r["l"] for r in self.dl[-RANGE_DAYS:]) / RANGE_DAYS
        mv = c - first[1]
        if rng <= 0 or abs(mv) < self.p["k"] * rng:
            return
        self._mkt(ctx, "long" if mv > 0 else "short", ref=c)


FAMILIES = {
    "day_move": (DayMove, {}, False,
                 "day_move: at `at` (15:00) the move since the 09:30 open, |move| >= k x the average daily range of the 20 days before -> "
                 "market with the move's sign, filled at the next bar; one trade a day; stop / target the sheet's, flat 15:58; the pm pass "
                 "only. Late-day momentum, Gao-Han-Li-Zhou 2018 (hunt Amendment O, batch 4b)",
                 {"rationale": "Into the close the day's winners add and the side caught against a big day move is squeezed out, so a move "
                               "since the open that is large for the market's daily range carries through the last hour. Who loses: the "
                               "traders fading the day's move at the close.",
                  "complexity": 3,
                  "variants": [{"k": 0.15}, {"k": 0.25}, {"k": 0.35}],
                  "roots": ("NQ", "ES", "GC")}),
}


def join_blocks() -> None:
    """Put the family into families/blocks.py's BASES and WRAPPED (as onr.py): the wrapped class a card runs, importable by name."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()

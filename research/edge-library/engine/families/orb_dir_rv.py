"""orb_dir_rv -- the 5-MINUTE OPENING RANGE BREAKOUT ON STOCKS IN PLAY, one market (Zarattini, Barbon and Aziz 2024, "A Profitable Day
Trading Strategy For The U.S. Equity Market", SSRN 4729284, sections 2 and 4), written from the paper's rule before any result. No
Level-2 feature (FEATURES = ()): NQ, ES and GC, 1 contract; the exits are the heat map's (no 10 % ATR stop: hm40 has none).

THE RULE (New York time, the nyam pass):
  * At 09:35 the opening range = the 1-minute bars of 09:30-09:35 (the 09:30 bar must be there): OPEN = the first bar's open, CLOSE = the
    last bar's close, HIGH / LOW = the extremes.
  * RELATIVE VOLUME = the volume of those five minutes / the MEAN of the same five minutes over the 14 trade dates before today (the
    paper's formula; a date without a tape, or fewer than 14 dates = no trade today). Trade only when it is >= `rv` (1.0 = the paper's 100 %).
  * DIRECTION = the opening range's own: CLOSE > OPEN -> ONE buy stop one tick above HIGH (long only); CLOSE < OPEN -> ONE sell stop one
    tick below LOW (short only); CLOSE == OPEN (a doji) -> nothing. The stop level is the paper's "stop order at the 5-minute high / low".
    Struct stop = the range's other extreme. One bracket a day (max_tr moot); the order is cancelled 5 minutes before the pass ends.
NOT CARRIED OVER: "the top 20 stocks by relative volume" (one market has no cross-section: the volume filter alone stays), the 10 % ATR
stop and the 1 % risk sizing (the heat map's stops, 1 contract), the 4x leverage cap, and an entry after 10:55 (the nyam pass ends 11:00; the
paper's entry window runs to the close, its position is held to 15:58 as here).
NO LOOK-AHEAD: the range is read from closed 1-minute bars up to 09:35, the reference from prior dates' tapes (sealed by their own date).
REGISTRATION as day_move.py: join_blocks() puts the family into families/blocks.py's BASES and WRAPPED (blocks.py is not edited).
Tests: engine/tests/test_orb_dir_rv.py."""
from __future__ import annotations

from l2sim import SESS, HoldoutSealed, Template, _hms

from . import blocks as B

OR_S = 300                                          # the opening range: the first five minutes
VOL_DAYS = 14


def ref_mean(root: str, dates: list, a: int, b: int):
    """The MEAN volume of the clock window [a, b) (seconds after 00:00 ET, whole minutes) over the last VOL_DAYS `dates`
    (blocks.cum_volume: the minute-volume file, else the date's own tape); None with fewer dates, a date without a tape (a sealed date the cache lacks counts as one), or a mean of 0."""
    i, j = a // 60 - B.MIN0, b // 60 - B.MIN0
    if len(dates) < VOL_DAYS or not 0 <= i < j <= B.NMIN:
        return None
    vals = []
    for iso in dates[-VOL_DAYS:]:
        try:
            c = B.cum_volume(root, iso)
        except HoldoutSealed:                       # a 2025+ session the cache lacks (a skipped, incomplete one) has no tape: no reference
            return None
        if c is None:
            return None
        vals.append(int(c[j] - c[i]))
    mean = sum(vals) / len(vals)
    return mean if mean > 0 else None


class OrbDirRv(Template):
    """orb_dir_rv (module docstring)."""
    DEFAULTS = {"rv": 1.0}
    SCHEMA = {"rv": ("float", 0.5, 20.0)}
    SCREEN_TFS = ("1", "5", "15", "30")
    FEATURES = ()

    def fam_filter(self, ids):
        return [s for s in ids if s == "nyam"]

    def fam_day(self, ctx):
        self._prior = [str(r["date"]) for r in self.dl]

    def fam_times(self):
        return [_hms(SESS["nyam"][0] + OR_S)]

    def fam_time(self, ctx, sec):
        a = SESS["nyam"][0]
        if self.sid != "nyam" or sec != a + OR_S or not self.can_enter(ctx):
            return
        xs = [m for m in self.M if a <= m[0] and m[0] + 60 <= sec]
        if not xs or xs[0][0] != a:
            return
        o, c = xs[0][1], xs[-1][4]
        if c == o:
            return
        ref = ref_mean(ctx.root, self._prior, a, sec)
        if ref is None or sum(m[5] for m in xs) < self.p["rv"] * ref:
            return
        hi, lo, t = max(m[2] for m in xs), min(m[3] for m in xs), ctx.tick
        self._arm(ctx, [("long", hi + t, lo, None)] if c > o else [("short", lo - t, hi, None)])


FAMILIES = {
    "orb_dir_rv": (OrbDirRv, {}, False,
                   "orb_dir_rv: at 09:35 the 09:30-09:35 range; its volume >= rv x the mean of the same five minutes over the 14 dates before "
                   "-> ONE stop entry one tick beyond the range, in the direction of the range's own candle (green: buy the high, red: sell the "
                   "low, doji: none); struct stop = the other extreme; the nyam pass only. Zarattini-Barbon-Aziz 2024 (SSRN 4729284)",
                   {"rationale": "A first five minutes that trades far more than usual shows institutions repricing a stock on news; the side "
                                 "that won that opening candle keeps the day's trend, so a break of the candle in its own direction carries. "
                                 "Who loses: the traders fading the open, and the side caught on the wrong end of an informed opening.",
                    "complexity": 3,
                    "variants": [{"rv": 1.0}, {"rv": 1.5}, {"rv": 2.0}],
                    "roots": ("NQ", "ES", "GC")}),
}


def join_blocks() -> None:
    """Put the family into families/blocks.py's BASES and WRAPPED (as day_move.py): the wrapped class a card runs, importable by name."""
    for name, entry in FAMILIES.items():
        if not B._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = B._wrap(name, entry[0])
        B.BASES[name] = entry
        B.WRAPPED[name] = cls
        setattr(B, cls.__name__, cls)


join_blocks()

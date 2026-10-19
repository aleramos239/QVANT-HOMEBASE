"""eve_fair -- THE EVENING FADE BACK TO THE 18:00 OPEN ("fair price"; JJ Simon, youtube BLvsYJ4sqn8, step 2; built at the owner's word of
2026-10-19: "build an eve fade-to-the-18:00-open entry rule first (like open_fade, 30-pt distance), then test it"). Written from the video's
rules (research/edge-library/videos/BLvsYJ4sqn8.md) before any result. No Level-2 feature. NQ, ES and GC, 1 contract, session eve only.

THE RULE (fixed here, before any run):
  * FAIR PRICE = the open of the first 1-minute bar at or after 18:00 ET (the reopen after the 17:00-18:00 break).
  * switch = on (the video, step 4): when the 20:00 1-minute candle moves AWAY from the fair line (20:00 open above fair and the candle
    green, or below and red), the 20:00 open becomes fair; toward it or a doji: 18:00 stays fair. off: 18:00 is fair all evening.
  * DISTANCE: at a tf close, the close at least `dist` points below fair -> longs only, at least `dist` above -> shorts only (the video: 30).
  * SIGNAL toward fair, read at that close (`sig`): disp = DISPLACEMENT -- the bar's body larger than the bar before's, and the close past
    that bar's wick (long: green and close above its high); bos = BREAK OF STRUCTURE -- the close crosses the last swing high (long) / low
    (short) of the evening's tf bars (a bar above / below its `piv` neighbours on each side, known `piv` bars later), the close before
    still on the other side; either (default) = disp or bos.
  * ENTRY: market at that close. Entries 18:00 -> 21:30 (the video: no new fade after 21:30). Retries allowed: max_tr 3 (2nd and 3rd tries).
  * EXIT: the exit cell's stop and target (the video: 25 / 38 points). A trade still open at 19:59 is flattened (the video, step 3: out
    before the 20:00 open). Later trades run to stop / target / the card's w_flat / the day's flatten.

MY PICKS, NOT THE VIDEO'S WORDS: the switch reads only the 20:00 1-minute candle's colour (the video also wants a break of structure and
skips a candle that "sits still"); swing = piv 3 bars each side; no "one green candle in a downtrend" check; no news; fair is never redrawn
by eye. The 18:00 / 20:00 continuation trade (step 1 / 4) is NOT this family.

NO LOOK-AHEAD: fair, the switch candle, both bars and every swing are read from closed bars; the order goes in after that close.
Tests: engine/tests/test_eve_fair.py."""
from __future__ import annotations

from l2sim import Template, _hms

FAIR0, SWITCH, LAST, OUT = -21600, -14400, -9000, -14460     # 18:00, 20:00, 21:30, 19:59 ET of the evening before (seconds)


class EveFair(Template):
    """eve_fair (module docstring). State per evening: fair = the fair price (None until 18:00 printed), sw = the 20:00 switch is read,
    want = the side to enter at this close, or None."""
    DEFAULTS = {"dist": 30.0, "sig": "either", "switch": "on", "piv": 3, "max_tr": 3}
    SCHEMA = {"dist": ("float", 0.0, 1000.0), "sig": ("choice", ("disp", "bos", "either")), "switch": ("choice", ("on", "off")),
              "piv": ("int", 1, 20)}
    SCREEN_TFS = ("1", "5")
    SCREEN_RUN = {}
    FEATURES = ()

    def fam_filter(self, ids):
        return ["eve"] if "eve" in ids else []

    def fam_day(self, ctx):
        self.fair, self.sw, self.want = None, False, None

    def fam_times(self):
        return [_hms(OUT)]

    def fam_time(self, ctx, sec):
        if sec == OUT and not ctx.flat:
            ctx.flatten("time")                      # the video: an 18:00 trade is out before 20:00

    def fam_update(self, ctx):
        self.want = None
        now = (self.M[-1][0] // (self.tf * 60) + 1) * self.tf * 60      # the clock close of this tf bar
        if self.fair is None:
            self.fair = self.mo(FAIR0)
        if not self.sw and self.p["switch"] == "on" and now >= SWITCH + 60:
            self.sw = True
            o, c = self.mo(SWITCH), self.mc(SWITCH, SWITCH + 60)
            if self.fair is not None and o is not None and c is not None and (o - self.fair) * (c - o) > 0:
                self.fair = o                        # the 20:00 move goes away: the 20:00 open is fair
        if self.fair is None or now > LAST or len(self.C) < 2:
            return
        c, d = self.C[-1], self.p["dist"]
        side = 1 if c <= self.fair - d else -1 if c >= self.fair + d else 0
        if side and (self._disp(side) or self._bos(side)):
            self.want = "long" if side > 0 else "short"

    def _disp(self, sd):
        if self.p["sig"] == "bos":
            return False
        o1, c1, o2, c2 = self.O[-2], self.C[-2], self.O[-1], self.C[-1]
        wick = self.H[-2] if sd > 0 else self.L[-2]
        return abs(c2 - o2) > abs(c1 - o1) and (c2 - o2) * sd > 0 and (c2 - wick) * sd > 0

    def _bos(self, sd):
        if self.p["sig"] == "disp":
            return False
        x = self.H if sd > 0 else [-v for v in self.L]   # a swing low is a swing high of the negated lows
        n, last = self.p["piv"], len(x) - 2              # pivots confirmed by the bars before this one
        for i in range(last - n, n - 1, -1):
            if x[i] > max(x[i - n:i]) and x[i] > max(x[i + 1:i + n + 1]):
                lvl = x[i] if sd > 0 else -x[i]
                return (self.C[-1] - lvl) * sd > 0 and (self.C[-2] - lvl) * sd <= 0
        return False

    def fam_signal(self, ctx):
        if self.want is not None:
            self._mkt(ctx, self.want)


ENTRY_WINDOWS = {"eve_fair": (FAIR0, LAST)}

FAMILIES = {
    "eve_fair": (EveFair, {}, False,
                 "eve_fair: fair = the 18:00 open (the 20:00 open when the 20:00 candle moves away, switch on); a close dist+ points from "
                 "fair and a displacement or break of structure back toward it -> market toward fair; entries 18:00-21:30, max 3, an open "
                 "trade flat at 19:59; eve only",
                 {"rationale": "The 18:00 reopen is the price both sides agreed on after the break, so a run far from it on thin evening "
                               "volume tends to come back once a strong candle shows the other side stepping in.",
                  "complexity": 5,
                  "variants": [{"dist": 20.0}, {"dist": 30.0}, {"dist": 40.0}]}),
}


def join_blocks() -> None:
    """Put the family into families/blocks.py's BASES and WRAPPED, as fvg_odir.py does. Idempotent."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()

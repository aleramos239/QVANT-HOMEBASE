"""sfp -- THE SWING FAILURE at a small swing as an entry trigger (the owner's request of 2026-10-09), written from its rule before any result. No
Level-2 feature is read (FEATURES = ()): NQ, ES and GC, 1 contract, hold_to = 'day' (flat 15:58 ET). Four JadeCap videos describe it (tFKOaF4HMcg,
TLEaD163obc, wZ4ea0VJnrw, Y8gUPDVnDgw, notes in research/edge-library/videos): price takes a recent swing high or low and the bar closes back.
`liq` sweeps levels too, but its swing is 50 five-minute bars each side; these traders mark the small swings of the 15-minute to 1-hour chart.

    sfp   bar-based 1/5/15   all seven sessions; setting swing (+ the Template's max_tr, dir)

THE RULE (fixed here, before any run):
  * SWING BARS. Bars of `swing` minutes (15 | 30 | 60, default 60) on ET clock multiples, built from the 1-minute bars the engine has handed
    this instance for the trade date (Template.M): from 00:00 ET of the trade date for a day session; from 18:00 ET of the evening before for
    an evening idea (the engine replays that evening and the day as one piece, so the evening belongs to the trade date). Earlier days are not
    read. A clock slot without a print makes no swing bar.
  * COMPLETE. At a tf close a swing bar counts only when it has ended: its end is at or before the clock close of the tf bar that has just
    closed. The swing bar still forming is never read.
  * SWING. A swing HIGH is a complete swing bar whose high is strictly above the high of the swing bar before it and of the swing bar after it
    (three bars); a swing LOW is the mirror with the lows. It is KNOWN only once the bar after it is complete: one swing bar late. The first
    swing bar of the day has no bar before it and is never a swing.
  * LEVEL. The high of a swing high (the low of a swing low) is a level. It is LIVE from the tf close at which the swing is known until a tf
    bar trades beyond it (a high above a swing high, a low below a swing low). Any number of levels can be live at once. The levels are
    followed from the first bar of the day, in and out of the idea's session: a level traded beyond before or after the session is gone too.
  * SIGNAL, read at a tf close inside the idea's session and never later than it: the bar's high is above a live swing high and its close is
    strictly back below that level = SHORT; the bar's low is below a live swing low and its close is strictly back above it = LONG. A bar that
    trades beyond a level and does not close back (a close on the level is not back) kills the level without a signal. So the first tf bar
    that trades beyond a level decides it, and each level gives at most one signal -- also when no order could be placed at that close (a
    trade is open, max_tr is reached, the last 5 minutes, the side is switched off by dir, the close is outside the session).
  * SEVERAL LEVELS. One bar that fails at several levels of the same side is ONE signal. A bar that gives a short and a long signal at once
    (it took a swing high and a swing low and closed between them) is no trade; a bar that fails at a high and closes THROUGH a low is the short.
  * ORDER. A market order placed at that close: it fills at the next bar's open (the first print after the 85 ms placement latency).
  * ENTRIES. Inside the idea's session only (a tf close in (start, end], never in the last 5 minutes of it: the Template's rule), up to `max_tr`
    a session (default 3), one position at a time.
  * EXITS. None of its own: the standard table's stop / target cells and the flat time 15:58 ET, as every family gets them.
  * SIDES. `dir` is the Template's: both (default), long or short; a one-sided card sets it through limits.dir. Not a mirror axis: the
    variants are the swing size.
  * WHAT FOLLOWS FROM IT. With the day starting at 00:00 the first swing can be known at 00:45 (swing 15), 01:30 (30) and 03:00 (60): an asia
    idea (00:00-03:00) with swing 60 never trades. The tf bars are never bigger than a swing bar (tf 1 / 5 / 15), so a swing bar always ends
    on a tf close and the bar that makes a swing known lies inside the swing's own neighbour: it cannot itself trade beyond the new level.

NO LOOK-AHEAD, where it could hide: (1) a swing needs the bar AFTER it, so it is used only from that bar's end on; (2) the clock of a decision
is the clock close of the tf bar, taken from the last 1-minute bar the Template has added (a tf bar whose last minutes had no print is closed
late by the Template, with the next minute's bar not yet added: that minute is not read either); (3) the level test reads the tf bar that has
just closed (H / L / C), nothing after it.

REGISTRATION. As families/noise.py: families/__init__.py picks this module up by itself (FAMILIES below), and join_blocks() puts the family
into families/blocks.py's BASES / WRAPPED when this module is imported (blocks always imports first: the package loads its modules in name
order) -- blocks.py, one of the files whose hash every store and lock remembers, stays byte for byte as it was.

COMPLEXITY 7 = the swing bars + the three-bar swing, known one bar late + live until traded beyond + beyond and a close back -> market against
it + once a level + both sides at once = no trade + swing. Tests: engine/tests/test_sfp.py."""
from __future__ import annotations

from l2sim import Template

SWINGS = ("15", "30", "60")                        # minutes of a swing bar


class Sfp(Template):
    """sfp (module docstring). State per day: sw = the swing bars in clock order as [slot, high, low] (the last one may still be forming),
    mi = the 1-minute bars already put into them, si = the next swing bar to judge as a swing, hi / lo = the live swing highs / lows,
    go = +1 / -1 / 0: the signal of the tf bar that has just closed."""
    DEFAULTS = {"swing": "60", "max_tr": 3}
    SCHEMA = {"swing": ("choice", SWINGS), "max_tr": ("int", 1, 5)}
    SCREEN_TFS = ("1", "5", "15")
    FEATURES = ()

    def fam_day(self, ctx):
        self.w = int(self.p["swing"]) * 60          # seconds of a swing bar
        self.sw, self.mi, self.si = [], 0, 1        # (the first swing bar of the day, index 0, is never judged)
        self.hi, self.lo = [], []
        self.go = 0

    def fam_update(self, ctx):
        self.go = 0
        M, w = self.M, self.w
        sw = self.sw
        for i in range(self.mi, len(M)):            # the new 1-minute bars go into their swing bar
            s, _, h, l, _, _ = M[i]
            k = s // w
            if sw and sw[-1][0] == k:
                if h > sw[-1][1]:
                    sw[-1][1] = h
                if l < sw[-1][2]:
                    sw[-1][2] = l
            else:
                sw.append([k, h, l])
        self.mi = len(M)
        step = self.tf * 60
        now = (M[-1][0] // step + 1) * step          # the clock close of the tf bar that has just closed, seconds after 00:00 ET
        while self.si + 1 < len(sw) and (sw[self.si + 1][0] + 1) * w <= now:      # the bar AFTER the candidate has ended
            a, b, c = sw[self.si - 1], sw[self.si], sw[self.si + 1]
            if b[1] > a[1] and b[1] > c[1]:
                self.hi.append(b[1])
            if b[2] < a[2] and b[2] < c[2]:
                self.lo.append(b[2])
            self.si += 1
        h, l, c = self.H[-1], self.L[-1], self.C[-1]
        short = any(h > x and c < x for x in self.hi)       # beyond a live swing high and a close back below it
        long = any(l < x and c > x for x in self.lo)
        self.hi = [x for x in self.hi if h <= x]             # a level traded beyond is gone, with or without a signal
        self.lo = [x for x in self.lo if l >= x]
        if short != long:
            self.go = -1 if short else 1

    def fam_signal(self, ctx):
        if self.go:
            self._mkt(ctx, "long" if self.go > 0 else "short")


FAMILIES = {
    "sfp": (Sfp, {}, False,
            "sfp: a swing high / low of the day's own `swing`-minute bars (a bar above / below both its neighbours, known once the bar after "
            "it has closed) is a level until price trades beyond it; a bar that trades beyond a level and closes back inside fails there -> "
            "market entry against it at the next bar's open: at a swing high = short, at a swing low = long. A bar that does not close back "
            "kills the level; each level signals once; entries inside the idea's session, up to max_tr a session, one position at a time; "
            "flat 15:58",
            {"rationale": "Stops and breakout orders rest just beyond a recent swing high or low, so a push through it fills breakout traders "
                          "at the worst price; when the bar closes back inside, those trapped traders have to get out and their exits carry "
                          "price the other way.",
             "complexity": 7,
             "variants": [{"swing": "15"}, {"swing": "30"}, {"swing": "60"}]}),
}


def join_blocks() -> None:
    """Put the family into families/blocks.py's BASES and WRAPPED (module docstring, REGISTRATION): the wrapped class a card runs, importable by
    name from there (workers import it through the package, which loads this module). Idempotent; a reload of blocks and then of this module
    does it again."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()

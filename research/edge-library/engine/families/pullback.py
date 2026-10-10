"""pullback -- THE PULLBACK INTO A SWING LEG as an entry trigger (the owner's request of 2026-10-10), written from its rule before any result. No
Level-2 feature is read (FEATURES = ()): NQ, ES and GC, 1 contract, hold_to = 'day' (flat 15:58 ET). Traders call it the "optimal trade
entry" or a Fibonacci pullback: structure breaks (a higher swing high, or a lower swing low), and they wait with a limit order part of the
way back into the leg that broke it. It trades WITH the leg. `sfp` fades a small swing; this one uses the same small swings to mark a leg.

    pullback   bar-based 1/5/15   all seven sessions; settings level, swing (+ the Template's max_tr, dir)

THE RULE (fixed here, before any run; the LIVE and ORDER lines as the owner corrected them on 2026-10-10, before any run as well):
  * SWING BARS: sfp's (families/sfp.py), restated here line for line. Bars of `swing` minutes (15 | 30 | 60, default 15) on ET clock
    multiples, built from the 1-minute bars the engine has handed this instance for the trade date (Template.M): from 00:00 ET of the trade
    date for a day session; from 18:00 ET of the evening before for an evening idea. Earlier days are not read. A clock slot without a print
    makes no swing bar. A swing bar counts only when it has ENDED: its end is at or before the clock close of the tf bar that has just closed.
  * SWING. A swing HIGH is a complete swing bar whose high is strictly above the high of the swing bar before it and of the swing bar after it;
    a swing LOW is the mirror with the lows. It is KNOWN only once the bar after it is complete: one swing bar late. The first swing bar of
    the day is never a swing.
  * LEG. An UP leg exists when a newly known swing high H is strictly above the swing high known before it (a higher high: structure broke
    up). Its START is the lowest low of the swing bars after that earlier swing high up to and including H's own bar. A DOWN leg is the
    mirror: a newly known swing low strictly below the swing low known before it; its start is the highest high of the swing bars after that
    earlier swing low up to and including the new one's bar. The first swing high (low) of the day has none before it and makes no leg; an
    equal or lower swing high makes none either, and is the one the next swing high is compared with. Legs are followed from the first bar
    of the day, in and out of the idea's session. The latest leg replaces any earlier one, of either side.
  * BOTH AT ONCE. A swing bar that is a higher swing high and a lower swing low at the same close points both ways: no order, and the earlier
    leg is replaced all the same.
  * ENTRY PRICE. Up leg: H - level x (H - start). Down leg: L + level x (start - L). Rounded to the tick toward the leg's start (down for an
    up leg, up for a down leg): the order never asks for less pullback than `level` says. `level` is the depth: 0.5 = half way back, 0.79 = deep.
  * THE EXTREME'S BAR. The tf bar (a bar of the idea's own size) inside H's swing bar that made the high H; when several tf bars trade that
    same price, the FIRST of them. For a down leg: the first tf bar that made the low. What happened inside that bar, before or after the
    extreme, the bars cannot say, so it is not counted below; every tf bar AFTER it is.
  * LIVE. A leg is live from the tf close at which it becomes known until the first of:
      1. its order fills (one entry a leg);
      2. a tf bar trades beyond H (a high above an up leg's H, a low below a down leg's low: the leg is still growing, and a new leg comes
         when the next swing is known). A bar that only touches H leaves it;
      3. a tf bar after the extreme's bar trades at or beyond the entry price while no order of this leg is working: the pullback happened
         without us. This counts the bars before the leg was known (a leg can be over at the close it becomes known), the bars outside the
         idea's session, the bars while another trade was open and the bars of a session's last 5 minutes. It is judged at the bar's close:
         the bar's low is at or under an up leg's entry price (high at or over a down leg's) and the leg has no working order at that close;
      4. a newer leg replaces it (also a newer leg that is over at once, and the two legs of BOTH AT ONCE).
  * THE ORDER. While a leg is live and has no working order, at EVERY tf close inside the idea's session the family asks for a LIMIT order
    at the entry price in the leg's direction (a buy for an up leg); the Template decides (flat, entries left, not the last 5 minutes, `dir`,
    the filters). The order is cancelled when the leg stops being live (2, 4). The Template's own cancel 5 minutes before the session's end
    does not end the leg by itself (3 does, once the price gets there). A limit fills on a one-tick trade-through, at its price (the
    engine's limit law), and the family runs with strict_limit (a fill print that is already through the stop is a loss), as fvg does.
  * STRUCTURE LEVEL passed with the order: the leg's start (where these traders put the stop). The stop table uses it only in its `struct` cells.
  * ENTRIES. Inside the idea's session only (a tf close in (start, end], never in the last 5 minutes of it: the Template's rule), up to `max_tr`
    a session (default 3), one position at a time.
  * EXITS. None of its own: the standard table's stop / target cells and the flat time 15:58 ET, as every family gets them.
  * SIDES. `dir` is the Template's: both (default), long or short; a one-sided card sets it through limits.dir. Not a mirror axis: the
    variants are the level (0.5 / 0.62 / 0.79).

WHAT FOLLOWS FROM IT (nothing below is an extra rule):
  * A leg needs two swings of one kind, and two swing highs are at least two swing bars apart. With the day starting at 00:00 the first leg can
    be known at 01:15 (swing 15), 02:30 (30) and 05:00 (60); an evening idea, starting at 18:00: 19:15, 20:30 and 23:00.
  * A leg becomes known at a clock multiple of `swing`, and its order can be placed at any tf close inside the session while it lives. A leg
    known before the session opens (09:15 for a 09:30 idea), exactly at its start, or while another trade is open gets its order at the
    first close inside at which the Template allows one -- if it is still live then. An asia idea (00:00-03:00) with swing 60 still never
    trades (no leg before 05:00); with swing 30 it can from 02:30 on.
  * A leg known exactly at a session's end (11:00, say) cannot trade in that session; the idea of the session that follows places it at
    its first close. An order cancelled in a session's last 5 minutes leaves its leg live, but that leg cannot trade in that session any
    more; in an instance that runs several sessions in turn it is placed again at the next session's first close.
  * The idea's bar size decides how much of H's own swing bar counts: with 1-minute bars every minute after the minute of the high, with
    5-minute bars the 5-minute bars after the one of the high, with 15-minute bars and swing 15 nothing of it. A leg can rise wholly inside
    H's own swing bar (its start can lie there). The deeper the level, the more legs live.
  * While its order works, a bar that trades AT the entry price and does not fill (the limit needs one tick through) leaves the leg alone.
    A bar inside which the Template cancelled the order (the last 5 minutes do not always begin on a bar's edge: 15-minute bars, or
    5-minute bars at 15:53) is a bar with no order working at its close: at the price in that bar = the leg is over.
  * The tf bars are never bigger than a swing bar (tf 1 / 5 / 15), so a swing bar always ends on a tf close, every swing bar is made of whole
    tf bars, and the bar that makes a leg known lies inside the swing's own neighbour: it cannot itself trade beyond H.
  * The entry price is never beyond the leg's start, and at most one entry order rests at a time. With `dir` set to one side the other
    side's legs still replace an earlier leg; their order is asked for and refused at every close.

NO LOOK-AHEAD, where it could hide: (1) a swing needs the bar AFTER it, so a leg is used only from that bar's end on; (2) the clock of a
decision is the clock close of the tf bar, taken from the last 1-minute bar the Template has added (a tf bar whose last minutes had no print
is closed late by the Template, with the next minute's bar not yet added: that minute is not read either); (3) the leg's start reads swing
bars made of 1-minute bars that have closed; the extreme's bar and the bars after it are tf bars that have closed (Template.H / L); the
tests of 2 and 3 read the tf bar that has just closed and the order's state at that close.

REGISTRATION. As families/noise.py: families/__init__.py picks this module up by itself (FAMILIES below), and join_blocks() puts the family
into families/blocks.py's BASES / WRAPPED when this module is imported (blocks always imports first: the package loads its modules in name
order) -- blocks.py, one of the files whose hash every store and lock remembers, stays byte for byte as it was.

COMPLEXITY 10 = the swing bars + the three-bar swing, known one bar late + a higher high / lower low makes the leg, its start the extreme
since the earlier swing + a limit with the leg at `level` of the way back, asked for while the leg lives + over beyond the leg's end + over
when the price got there without an order (the bars after the extreme's bar) + the newest leg replaces the older + once a leg + level +
swing. Tests: engine/tests/test_pullback.py."""
from __future__ import annotations

import math

from l2sim import Template

SWINGS = ("15", "30", "60")                        # minutes of a swing bar
EPS = 1e-6                                         # of a tick: a price that is on the tick grid stays there


def entry_price(sd: int, end: float, start: float, level: float, tick: float) -> float:
    """The limit price of a leg (module docstring, ENTRY PRICE): sd +1 = an up leg from `start` (its low) to `end` (H), -1 = a down leg."""
    k = (end - sd * level * abs(end - start)) / tick
    return round((math.floor(k + EPS) if sd > 0 else math.ceil(k - EPS)) * tick, 6)


class Pullback(Template):
    """pullback (module docstring). State per day: sw = the swing bars in clock order as [slot, high, low] (the last one may still be forming),
    mi = the 1-minute bars already put into them, si = the next swing bar to judge as a swing (sfp's three), ph / pl = the swing high / low
    known last as (its place in sw, its price), tb = the swing-bar slot of every tf bar that has closed (the Template's H / L hold their highs
    and lows, one for one), leg = the live leg as (side, H, entry price, start) or None, side +1 = an up leg (a buy), -1 = a down leg,
    od = the order last placed for the live leg (working, filled or cancelled) or None."""
    DEFAULTS = {"level": 0.62, "swing": "15", "max_tr": 3}
    SCHEMA = {"level": ("float", 0.25, 0.9), "swing": ("choice", SWINGS), "max_tr": ("int", 1, 5)}
    SCREEN_TFS = ("1", "5", "15")
    SCREEN_RUN = {"strict_limit": True}
    FEATURES = ()

    def fam_day(self, ctx):
        self.w = int(self.p["swing"]) * 60          # seconds of a swing bar
        self.sw, self.mi, self.si = [], 0, 1        # (the first swing bar of the day, index 0, is never judged)
        self.ph = self.pl = None
        self.tb = []
        self.leg = self.od = None

    def _known(self) -> list:
        """sfp's lines (Sfp.fam_update, restated; engine/tests/test_pullback.py holds the two together): the new 1-minute bars go into their
        swing bar, and every swing bar whose neighbour AFTER it has ended by the clock close of the tf bar that has just closed is judged
        once -> [(its place in sw, it is a swing high, it is a swing low)], oldest first."""
        M, w = self.M, self.w
        sw = self.sw
        for i in range(self.mi, len(M)):
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
        out = []
        while self.si + 1 < len(sw) and (sw[self.si + 1][0] + 1) * w <= now:
            a, b, c = sw[self.si - 1], sw[self.si], sw[self.si + 1]
            out.append((self.si, b[1] > a[1] and b[1] > c[1], b[2] < a[2] and b[2] < c[2]))
            self.si += 1
        return out

    def _drop(self, ctx):
        """The leg is over with its order (a bar beyond its end, or a newer leg): the order, if it still rests, is cancelled. A fill is
        counted first."""
        self.leg = self.od = None
        self._sync(ctx)
        self._cancel(ctx)

    def fam_update(self, ctx):
        self.tb.append(self.M[-1][0] // self.w)   # the swing bar this tf bar lies in
        known = self._known()
        H, L = self.H, self.L
        g, o = self.leg, self.od
        if g is not None:                            # the live leg against the tf bar that has just closed
            sd, end, px, _ = g
            if o is not None and o.status == "filled":
                self.leg = self.od = None            # 1. its order filled: one entry a leg (3 would say so too: a fill is a bar through the price)
            elif (H[-1] > end) if sd > 0 else (L[-1] < end):
                self._drop(ctx)                      # 2. a bar beyond H: the leg is still growing
            elif (o is None or o.status != "working") and ((L[-1] <= px) if sd > 0 else (H[-1] >= px)):
                self.leg = self.od = None            # 3. at the entry price with no order working: the pullback happened without us
        sw = self.sw
        for i, high, low in known:
            legs = []                                # (side, the leg's end, its start)
            if high:
                p, h = self.ph, sw[i][1]
                if p is not None and h > p[1]:       # a higher high: an up leg from the lowest low since the earlier swing high
                    legs.append((1, h, min(x[2] for x in sw[p[0] + 1:i + 1])))
                self.ph = (i, h)
            if low:
                p, l = self.pl, sw[i][2]
                if p is not None and l < p[1]:       # a lower low: a down leg from the highest high since the earlier swing low
                    legs.append((-1, l, max(x[1] for x in sw[p[0] + 1:i + 1])))
                self.pl = (i, l)
            if not legs:
                continue
            self._drop(ctx)                          # 4. the latest leg replaces any earlier one
            if len(legs) == 2:
                continue                             # both ways at once: no order
            sd, end, start = legs[0]
            px = entry_price(sd, end, start, self.p["level"], ctx.tick)
            k, ext = sw[i][0], H if sd > 0 else L
            x = next(j for j, t in enumerate(self.tb) if t == k and ext[j] == end)      # the extreme's bar: the first tf bar of H's swing bar at it
            if sd > 0:
                been, grown = min(L[x + 1:]) <= px, max(H[x + 1:]) > end
            else:
                been, grown = max(H[x + 1:]) >= px, min(L[x + 1:]) < end
            if not been and not grown:               # (grown: a leg known late, after a hole in the tape, that a later bar has passed)
                self.leg = (sd, end, px, start)

    def fam_signal(self, ctx):
        g = self.leg
        if g is not None:                            # live and no order working (the Template calls this only when none rests)
            self.od = self._lim(ctx, "long" if g[0] > 0 else "short", g[2], struct=g[3])


FAMILIES = {
    "pullback": (Pullback, {}, False,
                 "pullback: a higher swing high of the day's own `swing`-minute bars makes an up leg, from the lowest low since the swing high "
                 "before it -> a buy limit `level` of the way back into the leg (0.5 = half way); a lower swing low = the mirror, a sell limit; "
                 "a swing = a bar above / below both its neighbours, known once the bar after it has closed; the leg lives until its order "
                 "fills, a bar trades beyond its end, a bar after the one that made its end trades at the entry price with no order working, "
                 "or a newer leg comes; while it lives the order is asked for at every close inside the idea's session; one entry a leg; the "
                 "leg's start is the structure level; up to max_tr entries a session, one position at a time; flat 15:58",
                 {"rationale": "A new swing high above the last one shows buyers in control, and the traders who chased the move late have "
                               "their stops just under it, so the first pullback stops them out and hands their position, at a better price, "
                               "to the buyers who waited for the move to resume.",
                  "complexity": 10,
                  "variants": [{"level": 0.5}, {"level": 0.62}, {"level": 0.79}]}),
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

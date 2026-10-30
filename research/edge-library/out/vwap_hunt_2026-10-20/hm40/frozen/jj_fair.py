"""jj_fair -- JJ SIMON'S FAIR-PRICE REVERSION, NEW YORK, AS TAUGHT (the owner, 2026-10-19: "lets follow the $1000 plan and perfectly
execute it"). Written from the videos before any result: KN7j6NXXAio (the step-by-step strategy, 80 trades), KHEQ5g55dQ4 (the Chart
Fanatics interview), BLvsYJ4sqn8 / DEkzU8gqX-o (30 points of room, the 80 % rule). Notes: research/edge-library/videos/, merged in
jj-simon-fair-price-rulebook.md. disp_oside's sibling (families/disp_oside.py): the same side and displacement idea, but EVERY signal
of 09:35-11:00 instead of the first of the day. No Level-2 feature. NQ, 1 contract, hold_to = 'day' (flat 15:58 ET).

THE RULE (fixed here, before any run; the defaults are the taught sheet owner_jj_fair_nyam_25_38):
  * FAIR PRICE (`fair`): open = the 09:30 open (the open of the first 1-minute bar at or after 09:30): "fair price is 95 % of the time
    the market open". vwap = the session VWAP from 09:30 (his words: "a pretty good estimate on average"; he does not use it). adapt =
    the open until `max_loss` losing trades in a row, then the mean close of the last `cons` tf bars ("the most recent consolidation";
    his "adapt fair price if my trades are losing"), the count starting again from there; the day is never stopped in this mode.
  * SIDE, read at every tf close: that close below fair = longs only, above = shorts only, equal = nothing ("reversion back toward fair").
  * DISPLACEMENT (`entry` disp), two tf bars, bar 1 the older, read at bar 2's close: bar 2's body |close - open| larger than bar 1's
    body AND it closes beyond bar 1's wick -- UP: bar 2 green, close above bar 1's high; DOWN: bar 2 red, close below bar 1's low (the
    interview: "two qualifications: the body must be larger and it must close below the wick"). opp = on (default): bar 1 must be the
    opposite colour ("a displacement also has to displace a candle of the opposite color"). wick = off drops the close-beyond-the-wick
    test (his "zero discretion" wording in KN7j6NXXAio: "is the body bigger than the previous one? Then you do it").
  * BREAK OF STRUCTURE (`entry` bos; his A+ entry, the interview 6:35 / 54:39): a swing low = a tf bar whose low is below the lows of
    the `swing` bars on each side (swing 1 = his three-bar structure: "a wick lower than the candle before and the candle after"),
    known `swing` bars after it; above fair, a bar that CLOSES below the most recent known swing low is the short ("the instant it closes
    below ... I short"; KN7j6NXXAio: a close, not a wick). Long = the mirror with a swing high. One entry per level. `entry` both =
    either signal.
  * ROOM: the close is at least min_room points from fair (30: "I wouldn't take anything if it's not 30 points away"; the 80 % rule,
    30 of a 38-point target).
  * WINDOW: bar 2 closes after 09:35 and at or before `end` (11:00: "continuation in the first 5 minutes ... after that only reversion
    ... 90 minutes and I'm done"). A trade opened by then runs to its stop or target (flat 15:58).
  * ENTRY: a market order at the signal bar's close. One position at a time; the next signal after the trade has closed is the next
    entry (no cap: max_tr 20). STOP for the day after max_loss (3) losing trades in a row ("if I lose three in a row, then I'm done"),
    unless fair = adapt (the line moves instead).
  * STOP and TARGET (`exit`): cell = the exit cell's (the videos: 25-point stop, 38-point target, 1:1.5). room = his 80 % rule on a funded
    account (KHEQ5g55dQ4 79:06: "if I want to target a 100-point win I need at least 80 points in my favor"): target = 0.8 x the points
    back to fair, stop = target / 1.5 (needs stop_mode struct, tgt_r 1.5).
  * THE OPENING CONTINUATION (`cont` on; KN7j6NXXAio 5:36): at the close of the first 1-minute bar after 09:30, with its colour (green
    buy, red sell), stop 25 / target 38 when its body is 25 points or less, else 50 / 76 ("cut my contracts in half"), once a day
    (needs stop_mode struct, tgt_r 1.52). off (default) = reversions only, the taught sheet.
  * START (`start`): the first close that may enter: 09:35 (his words), 10:00, 10:30.
  * SCREEN-ONLY READINGS (never a taught sheet): entry any = every close toward fair with the room (the base rate of the fade); entry
    mom = the displacement traded AWAY from fair (the other side of the same bar); cont 2nd = the continuation on the second candle
    (his "weak first candle: enter on the 2nd"), cont 5m = the first 5-minute bar's colour at 09:35; cgap on = no continuation away from an
    unfilled gap (the open vs the prior day's close: a gap up allows the short only); fair pre = the last 1-minute close before 09:30
    (the pre-open consolidation he used live); entry momb = a close beyond the last known swing AWAY from fair, momall = mom or momb;
    cont 15m = the first 15-minute bar's colour at 09:45; cbias on = the continuation only against the last 6 hours (his "higher time
    frame bias is just inverting whatever happened for the previous 6 to 12 hours": the open above the 03:30 price allows the short only).

MY PICKS, NOT HIS WORDS: side and room read on the signal bar's close; entry at that close (market); bar 1 may be the 09:35 bar; a
trade's own result counts toward the in-a-row count when it closes (net < 0 after costs = a loss); the consolidation of `adapt` is a
mean of closes; a swing is known `swing` bars late.

NOT RUN (the taught sheet lists them): the 09:30 continuation trade; the pre-news price on 08:30 news days; the 14:00 session;
breakeven by eye; layering across accounts.

NO LOOK-AHEAD: the side, the room, both bars and every swing are read from closed bars; the order goes in after that close.
Tests: engine/tests/test_jj_fair.py."""
from __future__ import annotations

from .conti import _in_a_row
from .fvg_odir import OPEN, FvgOdir

REV0 = OPEN + 300                                    # 09:35 ET, seconds after 00:00
STARTS = {"09:35": REV0, "10:00": 36000, "10:30": 37800}
ENDS = {"11:00": 39600, "12:00": 43200, "15:00": 54000}
HOURS = {"all": ((0, 86400),), "good": ((34500, 36000), (41400, 45000), (50400, 52200)), "am": ((34500, 37800),), "pm": ((48600, 54000),)}


class JjFair(FvgOdir):
    """jj_fair (module docstring). State per day: want = the side to enter at this close, or None; fair = today's fair price;
    lo / hi = the most recent known swing low / high not yet traded; base = closed trades when fair was last set (adapt)."""
    DEFAULTS = {"min_room": 30.0, "opp": "on", "wick": "on", "max_loss": 3, "max_tr": 20,
                "entry": "disp", "fair": "open", "swing": 1, "cons": 15, "start": "09:35", "end": "11:00", "exit": "cell", "cont": "off",
                "cgap": "off", "cbias": "off", "min_body": 0.0, "vwap_dir": "off", "hours": "all", "vwap_slope": 0, "pullback": "off", "near": 0.0, "cont_min": 0.0}
    SCHEMA = {"min_room": ("float", 0.0, 500.0), "opp": ("choice", ("on", "off")), "wick": ("choice", ("on", "off")),
              "max_loss": ("int", 1, 99), "entry": ("choice", ("disp", "bos", "both", "any", "mom", "momb", "momall", "cont")),
              "fair": ("choice", ("open", "vwap", "adapt", "pre")),
              "swing": ("int", 1, 5), "cons": ("int", 3, 60), "start": ("choice", tuple(STARTS)), "end": ("choice", tuple(ENDS)),
              "exit": ("choice", ("cell", "room")), "cont": ("choice", ("off", "on", "2nd", "5m", "15m")), "cgap": ("choice", ("off", "on")), "cbias": ("choice", ("off", "on")),
              "min_body": ("float", 0.0, 10.0), "vwap_dir": ("choice", ("off", "on")), "hours": ("choice", ("all", "good", "am", "pm")),
              "vwap_slope": ("int", 0, 120), "pullback": ("choice", ("off", "on")), "near": ("float", 0.0, 100.0),
              "cont_min": ("float", 0.0, 500.0)}
    SCREEN_RUN = {}

    def fam_day(self, ctx):
        self.want, self.fair, self.lo, self.hi, self.base, self.struct, self.opened = None, None, None, None, 0, None, False
        self.vhist = []                                   # (clock second, session VWAP) at each 1-minute close, for vwap_slope

    def on_bar(self, ctx, bar):
        super().on_bar(ctx, bar)
        v = self.vwr()
        if v is not None:
            self.vhist.append((self.M[-1][0] + 60, v[0]))

    def _stop(self, c, sd, room):
        """The stop level handed to the order (read only under stop_mode struct): JJ's 25 points, or the 80 % rule's. Under struct the
        cell's stop_val is the Template's 1.5 default, not a size: reading it gave every non-opening entry a ~3-point stop (review 2026-10-20)."""
        if self.p["exit"] == "room":
            return c - sd * 0.8 * room / 1.5
        return c - sd * 25.0

    def _fair(self, ctx):
        if self.p["fair"] == "vwap":
            v = self.vwr()
            return None if v is None else v[0]
        if self.p["fair"] == "pre":
            return self.mc(OPEN - 3600, OPEN)                   # the last 1-minute close before 09:30
        o = self.mo(OPEN)
        if self.p["fair"] != "adapt" or o is None:
            return o
        if self.fair is None:
            self.fair = o
        trades = ctx._s.res.trades
        if len(trades) > self.base and _in_a_row(trades[self.base:]) >= self.p["max_loss"]:
            n = self.p["cons"]
            self.fair = sum(self.C[-n:]) / len(self.C[-n:])       # the line moves to the most recent consolidation
            self.base = len(trades)
        return self.fair

    def _swings(self):
        """Read the newest swing that became known at this close (k bars late) and keep it as the live level of its side."""
        k = self.p["swing"]
        if len(self.L) < 2 * k + 1:
            return
        j = len(self.L) - 1 - k
        lo, hi = self.L[j], self.H[j]
        if all(lo < self.L[i] for i in range(j - k, j)) and all(lo < self.L[i] for i in range(j + 1, j + k + 1)):
            self.lo = lo
        if all(hi > self.H[i] for i in range(j - k, j)) and all(hi > self.H[i] for i in range(j + 1, j + k + 1)):
            self.hi = hi

    def fam_update(self, ctx):
        self.want = None
        step = self.tf * 60
        now = (self.M[-1][0] // step + 1) * step     # the clock close of this tf bar
        if self.sid is None or now <= OPEN or len(self.C) < 2:
            return
        o2, c2 = self.O[-1], self.C[-1]
        cont = self.p["cont"]
        at = {"on": OPEN + 60, "2nd": OPEN + 120, "5m": OPEN + 300, "15m": OPEN + 900}.get(cont)
        if at is not None and not self.opened and now == at:
            self.opened = True                        # the opening candle(s): the colour, 25 / 38 or 50 / 76 by the body
            o0 = self.mo(OPEN)
            if o0 is None or c2 == o0:
                return
            sd = 1 if c2 > o0 else -1
            if abs(c2 - o0) <= self.p["cont_min"]:
                return                                # cont_min: only a big opening bar (JJ's 'over 25 points' line as the rule itself)
            if self.p["cgap"] == "on" and self.pdc is not None and (o0 - self.pdc) * sd > 0:
                return                                # away from an unfilled gap: no continuation
            if self.p["cbias"] == "on":
                c6 = self.mc(OPEN - 6 * 3600, OPEN - 6 * 3600 + 300)
                if c6 is None or (o0 - c6) * sd > 0:
                    return                            # the bias is the other way round from the last 6 hours
            self.want, self.struct = ("long" if sd > 0 else "short"), c2 - sd * (25.0 if abs(c2 - o0) <= 25.0 else 50.0)
            return
        if now <= REV0:
            return
        self._swings()
        if now < STARTS[self.p["start"]] or now > ENDS[self.p["end"]]:
            return
        if not any(a < now <= b for a, b in HOURS[self.p["hours"]]):
            return
        if self.p["entry"] == "cont":
            return                                    # the opening continuation alone
        fair = self._fair(ctx)
        if fair is None:
            return
        o1, h1, l1, c1 = self.O[-2], self.H[-2], self.L[-2], self.C[-2]
        room = abs(fair - c2)
        if room < self.p["min_room"]:
            return
        up, dn = c2 < fair, c2 > fair
        e = self.p["entry"]
        if self.p["min_body"] > 0 and (self.atr is None or abs(c2 - o2) < self.p["min_body"] * self.atr):
            return
        if e == "any":
            self.want = "long" if up else "short"
        if e in ("disp", "both", "mom", "momall") and abs(c2 - o2) > abs(c1 - o1):
            opp, wick = self.p["opp"] == "on", self.p["wick"] == "on"
            if e in ("mom", "momall"):
                up, dn = dn, up                        # the same displacement, traded away from fair
            if up and c2 > o2 and (not opp or c1 < o1) and (not wick or c2 > h1):
                self.want = "long"
            elif dn and c2 < o2 and (not opp or c1 > o1) and (not wick or c2 < l1):
                self.want = "short"
        if self.want is None and e in ("bos", "both"):
            if up and self.hi is not None and c2 > self.hi:
                self.want, self.hi = "long", None
            elif dn and self.lo is not None and c2 < self.lo:
                self.want, self.lo = "short", None
        if self.want is None and e in ("momb", "momall"):      # a break of structure AWAY from fair
            above, below = c2 > fair, c2 < fair
            if above and self.hi is not None and c2 > self.hi:
                self.want, self.hi = "long", None
            elif below and self.lo is not None and c2 < self.lo:
                self.want, self.lo = "short", None
        if self.want is not None and self.p["vwap_dir"] == "on":
            v = self.vwr()
            if v is None or (self.want == "long" and c2 <= v[0]) or (self.want == "short" and c2 >= v[0]):
                self.want = None                        # the entry must sit on its own side of the session VWAP
        if self.want is not None and self.p["vwap_slope"] > 0:
            v = self.vwr()
            back = [x for t, x in self.vhist if t <= now - 60 * self.p["vwap_slope"]]
            if v is None or not back or (self.want == "long" and v[0] <= back[-1]) or (self.want == "short" and v[0] >= back[-1]):
                self.want = None                        # the day's VWAP must be moving the entry's way
        if self.want is not None and self.p["pullback"] == "on":
            v = self.vwr()
            n = self.p["near"]
            if v is None or not (l1 - n <= v[0] <= h1 + n):
                self.want = None                        # the bar before must have touched (or come within `near` points of) the VWAP
        if self.want is not None:
            self.struct = self._stop(c2, 1 if self.want == "long" else -1, room)

    def fam_signal(self, ctx):
        if self.want is None:
            return
        if self.p["fair"] != "adapt" and _in_a_row(ctx._s.res.trades) >= self.p["max_loss"]:
            return
        self._mkt(ctx, self.want, struct=self.struct)


ENTRY_WINDOWS = {"jj_fair": (REV0, ENDS["11:00"] + 59)}       # the taught window; `end` past 11:00 is a screening knob only

FAMILIES = {
    "jj_fair": (JjFair, {}, False,
                "jj_fair: JJ Simon's fair price = the 09:30 open (or the VWAP, or the open moved to the last consolidation after 3 losses); "
                "09:35-11:00, below it long on an up displacement (body larger than the previous bar's, close above its high, the previous "
                "bar red) or a close above the last swing high, above it short on the mirror, only 30+ points from fair; market at the "
                "close, one position at a time, every signal, stop after 3 losses in a row; ONE instance 09:30-15:58; flat 15:58",
                {"rationale": "The open's first push is opening flow, stops and hedging rather than a re-pricing of the index, so once a "
                              "candle out-sizes the one before and closes through it back toward the open, price drifts back to the "
                              "open more often than not; three losses in a row says the open was not fair that day.",
                 "complexity": 5,
                 "variants": [{}]}),
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

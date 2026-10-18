"""candle_sweep -- THE PREVIOUS CANDLE SWEPT AND CLOSED BACK as an entry trigger (the owner's idea of 2026-10-17), written from his words
before any result: "on the 15 minute timeframe we look at the previous candle; if we sweep its high or low, then close back inside within
it, we enter: sweep the previous candle's low, reverse and close higher within the body = long, vice versa short; stop at the candle
extreme, 1 : 0.5". No Level-2 feature is read (FEATURES = ()): NQ, ES and GC, 1 contract, hold_to = 'day' (flat 15:58 ET).

    candle_sweep   bar-based 1/5/15/30   all seven sessions; settings mode, back, ema1h, candle, turn, dir930 (+ the Template's max_tr, dir)

THE RULE (fixed here, before any run):
  * BARS. The instance's own tf bars (the owner's bar is 15 minutes): the bar that has just closed (THIS bar) and the one before it (the
    PREVIOUS bar) of the same instance, from 00:00 ET of the trade date (an evening idea: from 18:00 of the evening before). The previous bar
    may lie before the session start: it is simply the bar before. A clock slot without a print makes no bar, so after a hole the previous bar
    is the last bar that traded.
  * CANDLES OF ANY SIZE (the owner, 2026-10-18: "test 3 minute"; the engine's bars are 1 / 5 / 15 / 30 only). `candle` = N > 0 minutes
    (0 = off, the default: the tf bars above): the family builds its own N-minute candles from the 1-minute bars (needs tf 1), on ET clock
    multiples of N from 00:00 (an evening idea: they run on from 18:00, the multiples are the same), a candle = the 1-minute bars whose
    start lies in it (a minute without a print adds nothing). A candle is judged once, at the first 1-minute close at or after its end
    (on time when its last minute traded; a minute late after a hole); THIS bar / the PREVIOUS bar below are then the candle that has just
    ended and the candle before it. The order, the structure level and the EMA's close are that candle's. The Template's own bits stay on
    the 1-minute bars: the 0.25 ATR floor of a structure stop is the 1-minute ATR(14), WARM is 3 minutes, the session window is read at
    the 1-minute close. With N = 5 / 15 / 30 on days without holes the signals are the tf 5 / 15 / 30 run's, from the third candle on.
  * SWEEP. THIS bar's low is strictly below the PREVIOUS bar's low (a long setup); its high strictly above the previous high (a short setup).
  * BACK. Read at THIS bar's close, strictly: `back` = where the close must come back to, for a long (the short is the mirror)
        range   above the previous bar's low (back inside its range)
        body    above the bottom of the previous bar's body, min(open, close) (the owner's words: "close higher within the body")
        far     above the top of the previous bar's body, max(open, close)
    A close past the far side of the body counts for `body` too: the owner's "within" is read as "back into it", not "and no further".
  * MODE (the owner, 2026-10-18: "if the candle closes over the previous candle's wick we enter, same stop idea and tp"). `mode` =
    sweep (the default: the rule above) | break: THIS bar closes strictly ABOVE the previous bar's high = long, strictly BELOW its low
    = short (the follow-through, not the fade; `back` is not read). The structure level is still THIS bar's own extreme (its low for a
    long, its high for a short), so the stop, the target and every other setting are the same as the sweep's.
  * TURN (the owner, 2026-10-18: "if the first candle is bearish, the candle that sweeps the wick and closes within the body must be
    bullish, and vice versa"). `turn` = on (off, the default: every run before it is unchanged): a long also needs the PREVIOUS bar red
    (close < open) and THIS bar green (close > open); a short needs the previous bar green and this bar red. A doji (close = open) is
    neither colour. `turn` = same (the owner, 2026-10-18: "it must be green green or red red"): a long needs the previous bar AND
    this bar green, a short both red.
  * THE 09:30-10:00 DIRECTION (the owner, 2026-10-18: "look at the direction from 9:30-10 and only trade in that direction"). `dir930`
    = with (off, the default): the open of the first 1-minute bar at or after 09:30 ET against the close of the last 1-minute bar
    before 10:00 sets the day's side -- up = longs only, down = shorts only, equal or no bar = no trade. It is known from the decision
    at or after 10:00 on, so an earlier decision (the 09:45 close) never trades with it; it never changes later in the day.
  * BOTH. A bar that swept both sides and qualifies both ways (it closed back inside both) is no trade.
  * ORDER. A market order placed at that close: it fills at the next bar's open (the first print after the 85 ms placement latency).
    Its structure level is THIS bar's extreme: its low for a long, its high for a short ("stop at the candle extreme"): stop_mode 'struct'
    takes it (the distance from the signal close to it, floored at 0.25 ATR like every structure stop, re-priced to the fill); the standard
    table's stops ignore it.
  * ENTRIES. Inside the idea's session only (a tf close in (start, end], never in the last 5 minutes of it: the Template's rule), up to
    `max_tr` a session (default 20: the owner gave no cap), one position at a time: a signal while a trade is open is not taken.
  * EXITS. None of its own: the stop / target cell and the flat time 15:58 ET.
  * SIDES. `dir` is the Template's: both (default), long or short; a one-sided card sets it through limits.dir.
  * THE 1-HOUR EMA (the owner, 2026-10-17: "add a 1 hour ema, only long above and short below"). `ema1h` = n > 0 (0 = off, the default:
    every run before it is unchanged): a long only when the signal close is strictly above the EMA(n) of the 1-hour closes, a short only
    when it is strictly below; no EMA (fewer than n closes) = no trade. A 1-hour close = the last print of a whole ET clock hour that has
    ENDED by the decision (an hour without a print makes none, so the 17:00-18:00 break is no bar). The closes run on across days as a
    chart's do: today's from 18:00 of the evening before up to the decision, before them the sessions before today (each 18:00 of its
    evening before to 17:00), newest back, until 3 x n closes are held (the EMA's start has faded below 1 %), the first session of the
    contract (a roll day) or 30 sessions. Seeded with the oldest close, then e += 2 / (n + 1) x (close - e).
    The sessions before today are read with the blueprint BUILD key (to 2025-06-30, as orb830): a read of the unseen days refuses.

NO LOOK-AHEAD, where it could hide: the test reads the two tf bars that have closed (O / H / L / C of each), nothing after them; the
decision's clock is the tf bar's close, taken from the last 1-minute bar the Template has added.

REGISTRATION. As families/sfp.py: families/__init__.py picks this module up by itself (FAMILIES below) and join_blocks() puts the family
into families/blocks.py's BASES / WRAPPED when this module is imported; blocks.py stays byte for byte as it was.

COMPLEXITY 4 = the previous bar + beyond its high / low + a close back to `back` -> market against it + both at once = no trade
(+1 with ema1h: the side of the 1-hour EMA; +1 with candle: candles of its own size; +1 with turn: the two colours; +1 with
dir930: the side of the 09:30-10:00 move).
Tests: engine/tests/test_candle_sweep.py."""
from __future__ import annotations

import datetime as dt

import numpy as np

import l2sim as S
from l2sim import Template

BACKS = ("range", "body", "far")
HOUR = 3600 * S.NS
LOOK = 30                                           # sessions back at most for the 1-hour closes
_CLOSES: dict = {}                                  # (root, iso) -> that session's 1-hour closes, per process


def hour_closes(ts, px, t0: int, t1: int):
    """The closes (last print) of the whole clock hours of the prints from t0 that have ENDED by t1, oldest first."""
    i0 = int(np.searchsorted(ts, t0 - t0 % HOUR, side="left"))
    i1 = int(np.searchsorted(ts, t1 - t1 % HOUR, side="left"))
    if i1 <= i0:
        return np.zeros(0)
    k = ts[i0:i1] // HOUR
    return np.asarray(px[i0:i1], np.float64)[np.flatnonzero(np.concatenate((k[1:] != k[:-1], [True])))]


def session_closes(root: str, iso: str):
    """The 1-hour closes of one whole session (18:00 ET of its evening before to 17:00), from its tape; None = no tape."""
    key = (root, iso)
    if key not in _CLOSES:
        t, d = S.load_tape(iso, root, allow_holdout=S.ALLOW_BP), S._date(iso)     # build days only (as orb830): a test-day read refuses
        _CLOSES[key] = None if t is None or not len(t.ts) else \
            hour_closes(t.ts, t.px, S.et_ns(d - dt.timedelta(days=1), "18:00"), S.et_ns(d, "17:00"))
    return _CLOSES[key]


def prior_closes(st, need: int):
    """The 1-hour closes of the sessions before today, one contract, oldest first (module docstring, THE 1-HOUR EMA)."""
    out, n = [], 0
    if st.day not in st.ROLLS:
        for r in reversed(st.dl[-LOOK:]):
            got = session_closes(st._cx.root, r["date"])
            if got is not None:
                out.append(got)
                n += len(got)
            if r["date"] in st.ROLLS or n >= need:
                break
    return np.concatenate(out[::-1]) if out else np.zeros(0)


def ema_last(closes, n: int):
    """EMA(n) after the last close, seeded with the first; None with fewer than n closes."""
    if len(closes) < n:
        return None
    a, e = 2.0 / (n + 1), float(closes[0])
    for c in closes[1:]:
        e += a * (float(c) - e)
    return e


def signal(po, ph, pl, pc, o, h, l, c, back, turn="off", mode="sweep"):
    """+1 long / -1 short / 0: THIS bar (o, h, l, c) against the PREVIOUS bar (po, ph, pl, pc) (module docstring, THE RULE, MODE, TURN)."""
    if mode == "break":                             # a close beyond the previous bar's wick: with it
        long, short = c > ph, c < pl
    else:
        lo_line = {"range": pl, "body": min(po, pc), "far": max(po, pc)}[back]
        hi_line = {"range": ph, "body": max(po, pc), "far": min(po, pc)}[back]
        long, short = l < pl and c > lo_line, h > ph and c < hi_line
    if turn == "on":                                # the previous bar the other colour, this bar the trade's
        long, short = long and pc < po and c > o, short and pc > po and c < o
    elif turn == "same":                            # both bars the trade's colour
        long, short = long and pc > po and c > o, short and pc < po and c < o
    return 0 if long == short else (1 if long else -1)


class CandleSweep(Template):
    """candle_sweep (module docstring). go = +1 / -1 / 0: the signal of the bar (or candle) that has just closed; sx = its (low, high,
    close); with `candle`: cd = the day's candles [slot, o, h, l, c], mi = the 1-minute bars already in them, done = the candles judged."""
    DEFAULTS = {"mode": "sweep", "back": "body", "ema1h": 0, "candle": 0, "turn": "off", "dir930": "off", "max_tr": 20}
    SCHEMA = {"mode": ("choice", ("sweep", "break")), "back": ("choice", BACKS), "ema1h": ("int", 0, 500), "candle": ("int", 0, 60), "turn": ("choice", ("off", "on", "same")), "dir930": ("choice", ("off", "with")),
              "max_tr": ("int", 1, 20)}
    SCREEN_TFS = ("1", "5", "15", "30")
    FEATURES = ()

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        if self.p["candle"] and self.p["tf"] != "1":
            raise ValueError(f"candle_sweep: candle = {self.p['candle']} builds its own candles from the 1-minute bars: it needs tf 1, "
                             f"not {self.p['tf']}")

    def fam_day(self, ctx):
        self.go, self.sx = 0, None
        self.cd, self.mi, self.done = [], 0, 0
        self.d930 = None

    def fam_update(self, ctx):
        self.go = 0
        if self.p["candle"]:
            return self._candles()
        if self.nb < 2:
            return
        O, H, L, C = self.O, self.H, self.L, self.C
        self.go = signal(O[-2], H[-2], L[-2], C[-2], O[-1], H[-1], L[-1], C[-1], self.p["back"], self.p["turn"], self.p["mode"])
        self.sx = (L[-1], H[-1], C[-1])

    def _candles(self):
        w, M, cd = self.p["candle"] * 60, self.M, self.cd
        for i in range(self.mi, len(M)):                # the new 1-minute bars go into their candle
            s, o, h, l, c, _ = M[i]
            k = s // w
            if cd and cd[-1][0] == k:
                x = cd[-1]
                x[2], x[3], x[4] = max(x[2], h), min(x[3], l), c
            else:
                cd.append([k, o, h, l, c])
        self.mi = len(M)
        if not cd:
            return
        now = (M[-1][0] // 60 + 1) * 60                 # the clock close of the 1-minute bar that has just closed
        j = len(cd) if (cd[-1][0] + 1) * w <= now else len(cd) - 1          # the candles that have ended
        if j > self.done:
            self.done = j
            if j >= 2:
                (_, po, ph, pl, pc), (_, o, h, l, c) = cd[j - 2], cd[j - 1]
                self.go = signal(po, ph, pl, pc, o, h, l, c, self.p["back"], self.p["turn"], self.p["mode"])
                self.sx = (l, h, c)

    def ema1h(self, ctx):
        """The 1-hour EMA at this decision (module docstring), or None."""
        n, s, d = self.p["ema1h"], ctx._s, ctx.date
        today = hour_closes(s.ts, s.px, S.et_ns(d - dt.timedelta(days=1), "18:00"), ctx.now_ns)
        return ema_last(np.concatenate((prior_closes(self, 3 * n - len(today)), today)), n)

    def dir930(self):
        """+1 / -1 / 0: the 09:30-10:00 ET move of the day (module docstring), 0 before it is known."""
        if self.d930 is None:
            M = self.M
            if not M or (M[-1][0] // 60 + 1) * 60 < 36000:
                return 0
            w = [m for m in M if 34200 <= m[0] < 36000]
            self.d930 = 0 if not w else (w[-1][4] > w[0][1]) - (w[-1][4] < w[0][1])
        return self.d930

    def fam_signal(self, ctx):
        if self.go and self.p["dir930"] == "with" and self.dir930() != self.go:
            return
        if self.go and self.p["ema1h"]:
            e = self.ema1h(ctx)
            if e is None or (self.sx[2] - e) * self.go <= 0:
                return
        if self.go > 0:
            self._mkt(ctx, "long", struct=self.sx[0])
        elif self.go < 0:
            self._mkt(ctx, "short", struct=self.sx[1])


FAMILIES = {
    "candle_sweep": (CandleSweep, {}, False,
                     "candle_sweep: a tf bar trades beyond the previous bar's low (high) and closes back above (below) a line of that bar -- "
                     "back = range: its low (high); body: the bottom (top) of its body; far: the top (bottom) of its body -> market entry "
                     "against the sweep at the next bar's open: long after a swept low, short after a swept high; both at once = no trade; "
                     "structure level = the sweeping bar's own extreme; entries inside the idea's session, up to max_tr a session, one "
                     "position at a time; flat 15:58",
                     {"rationale": "Stops and breakout orders sit just beyond the last candle's high and low; a bar that runs them and closes "
                                   "back inside fills those traders at the extreme and leaves no one to push further, so their exits carry "
                                   "price back the other way.",
                      "complexity": 4,
                      "variants": [{"back": "range"}, {"back": "body"}, {"back": "far"}]}),
}


def join_blocks() -> None:
    """Put the family into families/blocks.py's BASES and WRAPPED (module docstring, REGISTRATION). Idempotent."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()

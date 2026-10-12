"""Order-flow studies built on the tick fields a Bar carries (buy / sell / n / te / span). Pure; the Study contract of
studies_ta.py (push / preview, immutable state, None while warming up).

Wire keys (every part after the name is a number; a missing one takes its default):
  ddiv:5       delta divergence: a swing high / low of the price (n bars each side, known n bars later) against the
               session's cumulative delta at that bar. Higher price high on a LOWER cumulative-delta high = bearish
               (dir -1); lower price low on a HIGHER cumulative-delta low = bullish (dir +1). One value on the bar
               that CONFIRMS the swing, none on any other bar, and none from the developing bar (never repaints)
                                                                                  -> {dir, ago, px}
  tspeed:200   prints per second of the bar and a burst line = 3 x the median rate of the last n bars before it
                                                                                  -> {rate, burst, hot}
  press:5      buy / sell pressure (-100 .. +100, + = buyers) over an exponentially weighted window of about n
               bars (the newest weighs most): the aggressors' volume, the big prints, the sweeps and the orders each
               side sent, each as (buy - sell) / (buy + sell + a little); `p` is the blend (volume counts 3, the
               rest 1, parts with nothing left out), `tot` the session's whole volume balance so far
                                                                              -> {p, vol, big, swp, ord, tot}
"""
from __future__ import annotations

from .bars import BIG_MIN
from .studies_ta import _Study, make_ta_num

BURST_MULT = 3.0


class DeltaDiv(_Study):
    def __init__(self, n: int = 5):
        self.n = int(n)
        super().__init__()

    def initial(self):
        # session, cumulative delta, window of (high, low, cum) for the last 2n+1 bars, previous swing high / low (price, cum)
        return (None, 0, (), None, None)

    def step(self, st, bar):
        sess, cum, win, ph, pl = st
        if bar.session != sess:
            sess, cum, win, ph, pl = bar.session, 0, (), None, None
        cum += bar.buy - bar.sell
        n = self.n
        win = (win + ((bar.h, bar.l, cum),))[-(2 * n + 1):]
        out = None
        if len(win) == 2 * n + 1:
            h, l, c = win[n]
            if h > max(w[0] for w in win[:n]) and h > max(w[0] for w in win[n + 1:]):
                if ph is not None and h > ph[0] and c < ph[1]:
                    out = {"dir": -1, "ago": n, "px": h}
                ph = (h, c)
            if l < min(w[1] for w in win[:n]) and l < min(w[1] for w in win[n + 1:]):
                if pl is not None and l < pl[0] and c > pl[1]:
                    out = {"dir": 1, "ago": n, "px": l}
                pl = (l, c)
        return (sess, cum, win, ph, pl), out

    def preview(self, bar):
        return None     # a swing is only confirmed by CLOSED bars: the developing one never draws a marker


class TapeSpeed(_Study):
    def __init__(self, n: int = 200):
        self.n = int(n)
        super().__init__()

    def initial(self):
        return ()       # the rates of the closed bars, newest last

    @staticmethod
    def _rate(bar):
        if bar.n <= 0:
            return None
        ms = bar.span if bar.closed and bar.span else bar.te - bar.t
        return bar.n / max(1.0, ms / 1000.0)

    def step(self, st, bar):
        r = self._rate(bar)
        if r is None:
            return st, None
        burst = None
        if len(st) >= 10:
            s = sorted(st)
            burst = BURST_MULT * (s[len(s) // 2] + s[(len(s) - 1) // 2]) / 2.0
        out = {"rate": r, "burst": burst, "hot": r if burst is not None and r >= burst else None}
        return (st + (r,))[-self.n:], out


class Pressure(_Study):
    """Who is pushing harder, and by how much. Pure arithmetic on what a Bar already holds: buy / sell volume, the
    big prints (`big`: [ts, price, size, side]), the finished sweeps (`sw`: [ts, from, to, size, side]) and the
    aggressive orders each side sent (`ords_b` / `ords_s`: runs of one side's prints inside one millisecond, -1 on
    a bar cached before they were counted).

    Each part is (buy - sell) / (buy + sell + SHRINK) x 100 over an exponentially weighted window of the last n
    bars (n = the span: n bars carry about 87 % of the weight, n = 1 is the bar alone). The newest bar weighs
    most, so the line turns with the move instead of two bars after it; SHRINK is a little neutral weight that
    keeps a lone 10-lot print from reading +/-100. The blend weighs volume 3 and the rest 1 each, over the parts
    that have anything on either side. A print is "big" when it is at least BIG_MIN contracts AND at least
    BIG_REL times the session's average print, so ES (average print 3) is not all big prints and YM is not none.
    A session change restarts the window and the running total."""

    PARTS = ("vol", "big", "swp", "ord")
    WEIGHT = (3.0, 1.0, 1.0, 1.0)
    SHRINK = (0.0, 30.0, 30.0, 20.0)      # contracts, contracts, contracts, orders: first guesses, held on 6 roots
    BIG_REL = 8.0

    def __init__(self, n: int = 5):
        self.n = int(n)
        self.keep = 1.0 - 2.0 / (self.n + 1)        # n = 1 -> 0: the bar alone
        super().__init__()

    def initial(self):
        # session, decayed sums (buy, sell) x (volume, big, sweep, orders), session prints and volume (average print
        # size), session buy, sell
        return (None, (0.0,) * 8, 0, 0, 0, 0)

    def _parts(self, bar, avg):
        floor = max(float(BIG_MIN), self.BIG_REL * avg)
        bb = sum(r[2] for r in bar.big if r[3] > 0 and r[2] >= floor)
        bs = sum(r[2] for r in bar.big if r[3] <= 0 and r[2] >= floor)
        sb = sum(r[3] for r in bar.sw if r[4] > 0)
        ss = sum(r[3] for r in bar.sw if r[4] <= 0)
        return (bar.buy, bar.sell, bb, bs, sb, ss, max(bar.ords_b, 0), max(bar.ords_s, 0))

    def step(self, st, bar):
        sess, acc, pn, pv, cb, cs = st
        if bar.session != sess:
            sess, acc, pn, pv, cb, cs = bar.session, (0.0,) * 8, 0, 0, 0, 0
        pn, pv = pn + bar.n, pv + bar.v
        parts = self._parts(bar, pv / pn if pn > 0 else 0.0)
        acc = tuple(a * self.keep + x for a, x in zip(acc, parts))
        cb, cs = cb + bar.buy, cs + bar.sell
        vals, num, den = [], 0.0, 0.0
        for i, w in enumerate(self.WEIGHT):
            b, s = acc[2 * i], acc[2 * i + 1]
            if b + s > 0:
                v = 100.0 * (b - s) / (b + s + self.SHRINK[i])
                num, den = num + w * v, den + w
            else:
                v = None
            vals.append(v)
        out = dict(zip(self.PARTS, vals))
        out["p"] = num / den if den else None
        out["tot"] = 100.0 * (cb - cs) / (cb + cs) if cb + cs > 0 else None
        return (sess, acc, pn, pv, cb, cs), out


# name -> (class, parameters): each parameter is (default, minimum, maximum); a wire key may give them in order
PARAMS = {
    "ddiv": (DeltaDiv, ((5, 1, 50),)),
    "tspeed": (TapeSpeed, ((200, 20, 2000),)),
    "press": (Pressure, ((5, 1, 50),)),
}
NAMES = tuple(PARAMS)


def make_flow(name: str, args: list):
    """The flow study `name` with its wire-key `args` (strings), or ValueError: too many parameters, one not a number
    or outside its range."""
    cls, spec = PARAMS[name]
    if len(args) > len(spec):
        raise ValueError(f"bad study {name!r}: at most {len(spec)} parameter(s)")
    vals = []
    for i, (default, lo, hi) in enumerate(spec):
        vals.append(int(make_ta_num(name, args, i, default, lo, hi)))
    return cls(*vals)


def warm_flow(name: str, rest: list) -> int:
    """Bars after a join that a flow study's value still depends on (hub.warm_bars)."""
    try:
        n = int(float(rest[0]))
    except (IndexError, ValueError):
        n = PARAMS[name][1][0][0]
    if name == "press":
        return 3 * n + 2        # an exponential window: 0.67^15 of the weight left after 3n bars at n = 5
    return 4 * n + 2 if name == "ddiv" else n + 1

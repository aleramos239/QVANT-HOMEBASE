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
"""
from __future__ import annotations

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


# name -> (class, parameters): each parameter is (default, minimum, maximum); a wire key may give them in order
PARAMS = {
    "ddiv": (DeltaDiv, ((5, 1, 50),)),
    "tspeed": (TapeSpeed, ((200, 20, 2000),)),
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
    return 4 * n + 2 if name == "ddiv" else n + 1

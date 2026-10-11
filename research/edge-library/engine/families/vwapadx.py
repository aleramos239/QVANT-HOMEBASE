"""vwapadx -- the VWAP PULLBACK WITH AN ADX GATE entry (Matteo Conti, IQCapital video A0G14JYYVTk, "strategy 2"), written from the
video's rule before any result. No Level-2 feature is read (FEATURES = ()): NQ, ES and GC, 1 contract, long only, hold_to = 'day'.

    vwap_adx   bar-based 1 (the video's bars)   ONE pass: the nyam pass, stretched to 09:30-15:55 inside this family (see SESSION)

THE RULE (fixed here, before any run; every time New York, his Central + 1 hour):
  * OPENING RANGE = the high and the low of the 1-minute bars 09:30-10:00 (`or_min` minutes; his 08:30-09:00 Central).
  * VWAP = volume-weighted (high + low + close) / 3 of the 1-minute bars from 09:30 (his chart of 2026-09-22 draws the line from the
    08:30 Central open; the typical price is this toolkit's own, as in families/round1).
  * 1 ARM: a 1-minute bar that closes after the range is complete CLOSES strictly above the opening range high. Once a day; it stays.
  * 2 TOUCH: on that bar or a later one the bar's low is at or under the VWAP ("just can touch it").
  * 3 + 4 SIGNAL, read at a 1-minute close, on the touch bar or a later one: the bar CLOSES strictly above the VWAP, and Wilder's
    ADX(14) of the 1-minute bars since 00:00 ET, read at that bar, is strictly above `adx_min` (20) and NOT HIGHER than at the bar
    before ("not increasing ... from the previous bar"). When 1-3 hold and the ADX is still rising, or at or under the line, nothing is
    sent: the next bar that closes above the VWAP with the gate open trades ("we wait for the ADX").
  * ENTRY: long, a market order at that close: it fills at the next bar's open.
  * EXITS, both fixed at the signal: the TARGET is the highest high of the last `tp_bars` (5) 1-minute bars, the signal bar counted
    (a limit order); the STOP is the lowest low of the last `sl_bars` (20), the signal bar counted (a market stop). Out at 15:55 if
    neither (his 16:55; see the sheet). ONE trade a day (max_tr 1, one pass): the video gives no number.
  * `min_tp` (0 = off, the video's rule) is OURS, added 2026-10-11 after the taught run: a signal whose target is nearer than min_tp
    points is not traded (the day goes on). The taught run showed that the entries with a target of a few points are fill bets, and
    the video itself says the entry candle is the 5-bar high in under 5 % of its trades; the split was SEEN on the build days, so
    a run with it is a new rule that needs unseen days of its own.

SESSION. This family trades ONE pass, `nyam`, whose window it stretches to 09:30-15:55 (fam_sessions), so the day holds one decision
stream. Entries stop 5 minutes before the pass ends (the Template's rule). The other passes trade nothing (fam_filter). A trade is
flattened at 15:55 by the family (fam_time).

KNOWN DIFFERENCES FROM THE VIDEO (the sheet lists them under not_run): a target less than 2 ticks above the signal close is NO TRADE
here (the Template's rule; he says his target sits at the entry candle's own high under 5 % of the time and is taken); the stop is
never nearer than a quarter of the bars' ATR (the Template's floor on a structure stop); both brackets move with the fill (1 tick of
slippage); the ADX runs over the 1-minute bars since 00:00 ET of the day (his is a continuous series); costs are the engine's own.

The ADX is kept bar by bar (O(1) a bar) with the SAME arithmetic as families/blocks.adx_last: a test holds the two equal on every bar.
REGISTRATION as noise.py and onr.py: join_blocks() puts the family into families/blocks.py's BASES and WRAPPED once, so blocks.py stays
byte for byte as it was. Tests: engine/tests/test_vwapadx.py."""
from __future__ import annotations

from l2sim import Template, _hms

OPEN_S = 34200                                      # 09:30 ET, seconds after 00:00 ET
PASS_END_S = 57300                                  # 15:55 ET: the family's pass ends and a trade is flattened here
ADX_N = 14


class Adx:
    """Wilder's ADX(n), one bar at a time: add(h, l, c) -> the ADX at that bar, or None before 2 n bars. The arithmetic of
    families/blocks.adx_last (+DM / -DM / TR summed over n, then s - s / n + x; ADX = the mean of the first n DX, then Wilder's)."""

    def __init__(self, n: int = ADX_N):
        self.n, self.k = n, 0                       # k: bars seen
        self.prev = None                            # the bar before: (h, l, c)
        self.s_tr = self.s_p = self.s_m = 0.0
        self.dx: list = []                          # the first n DX values, until their mean is taken
        self.adx = None

    @staticmethod
    def _dx(tr: float, p: float, m: float) -> float:
        if tr <= 0:
            return 0.0
        pi, mi = 100.0 * p / tr, 100.0 * m / tr
        return 0.0 if pi + mi == 0 else 100.0 * abs(pi - mi) / (pi + mi)

    def add(self, h: float, l: float, c: float):
        n, self.k = self.n, self.k + 1
        if self.prev is None:
            self.prev = (h, l, c)
            return None
        ph, pl, pc = self.prev
        self.prev = (h, l, c)
        up, dn = h - ph, pl - l
        pdm = up if up > dn and up > 0 else 0.0
        mdm = dn if dn > up and dn > 0 else 0.0
        tr = max(h - l, abs(h - pc), abs(l - pc))
        i = self.k - 1                              # this is the i-th true range (1-based)
        if i <= n:
            self.s_tr += tr
            self.s_p += pdm
            self.s_m += mdm
            if i < n:
                return None
        else:
            self.s_tr += tr - self.s_tr / n
            self.s_p += pdm - self.s_p / n
            self.s_m += mdm - self.s_m / n
        x = self._dx(self.s_tr, self.s_p, self.s_m)
        if self.adx is None:
            self.dx.append(x)
            if len(self.dx) == n:
                self.adx = sum(self.dx) / n
        else:
            self.adx = (self.adx * (n - 1) + x) / n
        return self.adx if self.k >= 2 * n else None


class VwapAdx(Template):
    """vwap_adx (module docstring). State per day: the opening range high, armed, touched, the VWAP sums, the ADX now and a bar ago."""
    DEFAULTS = {"adx_min": 20.0, "or_min": 30, "tp_bars": 5, "sl_bars": 20, "min_tp": 0.0, "max_tr": 1}
    SCHEMA = {"adx_min": ("float", 0.0, 100.0), "or_min": ("int", 5, 120), "tp_bars": ("int", 1, 60), "sl_bars": ("int", 1, 240),
              "min_tp": ("float", 0.0, 500.0), "max_tr": ("int", 1, 5)}
    SCREEN_TFS = ("1",)
    FEATURES = ()

    def fam_filter(self, ids):
        return [s for s in ids if s == "nyam"]

    def fam_sessions(self) -> dict:
        return {"nyam": (OPEN_S, PASS_END_S)}

    def fam_day(self, ctx):
        self.vv = self.vp = 0.0                     # VWAP sums from 09:30: volume, volume x typical price
        self.mi = 0                                 # 1-minute bars already added to them
        self.bi = 0                                 # tf bars already given to the ADX
        self.ax = Adx()
        self.adx = self.adx_was = None              # the ADX at the last tf bar, and at the one before it
        self.vwap = None
        self.orh = None                             # the opening range high, once the range is complete
        self.armed = self.touched = False
        self.go = False

    def fam_times(self):
        return [_hms(PASS_END_S)]

    def fam_time(self, ctx, sec):
        if sec == PASS_END_S:
            self._cancel(ctx)
            ctx.flatten("time")

    def fam_update(self, ctx):
        self.go = False
        M = self.M
        for i in range(self.mi, len(M)):
            s, _, h, l, c, v = M[i]
            if s >= OPEN_S and v > 0:
                self.vv += v
                self.vp += v * (h + l + c) / 3.0
        self.mi = len(M)
        for i in range(self.bi, len(self.C)):       # every tf bar exactly once, in order
            self.adx_was, self.adx = self.adx, self.ax.add(self.H[i], self.L[i], self.C[i])
        self.bi = len(self.C)
        step = self.tf * 60
        end = (M[-1][0] // step + 1) * step         # the nominal close second of the tf bar that has just closed
        or_end = OPEN_S + int(self.p["or_min"]) * 60
        if end <= or_end or self.vv <= 0:
            return
        self.vwap = vw = self.vp / self.vv
        if self.orh is None:
            r = self.rng(OPEN_S, or_end)
            if r is None:
                return
            self.orh = r[0]
        c = self.C[-1]
        if not self.armed and c > self.orh:
            self.armed = True
        if self.armed and self.L[-1] <= vw:
            self.touched = True
        a, b = self.adx, self.adx_was
        self.go = bool(self.armed and self.touched and c > vw and a is not None and b is not None
                       and a > self.p["adx_min"] and a <= b)

    def fam_signal(self, ctx):
        if not self.go:
            return
        n, m = int(self.p["tp_bars"]), int(self.p["sl_bars"])
        tp = max(self.H[-n:])
        if tp - self.C[-1] < self.p["min_tp"]:      # OURS, not the video's (0 = off): the target is nearer than min_tp points -> no
            return                                  # trade at this bar; the day goes on and a later signal may trade
        o = self._mkt(ctx, "long", struct=min(self.L[-m:]), tp_px=tp)
        if o is not None:
            self.touched = False                    # a later trade (max_tr above 1) needs a touch of its own


FAMILIES = {
    "vwap_adx": (VwapAdx, {}, False,
                 "vwap_adx: long only. A 1-minute close above the 09:30-10:00 opening range high arms the day; then a touch of the "
                 "VWAP (from 09:30), then a 1-minute close back above it with ADX(14) above adx_min and not higher than a bar ago -> "
                 "market entry at the next bar's open; target = the highest high of the last tp_bars bars, stop = the lowest low of "
                 "the last sl_bars bars, both fixed at the signal; flat 15:55. Conti's VWAP pullback with ADX gate (A0G14JYYVTk)",
                 {"rationale": "Institutional orders are worked against the VWAP: once the day has shown buying (a close above its "
                               "opening range), a pullback that touches the VWAP and is bought back above it while the pullback's own "
                               "trend strength fades is where those orders push the price up again.",
                  "complexity": 9,
                  "variants": [{"adx_min": a} for a in (15.0, 20.0, 25.0)]}),
}


def join_blocks() -> None:
    """Put the family into families/blocks.py's BASES and WRAPPED (as noise.py does): the wrapped class a card runs, importable by name."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()

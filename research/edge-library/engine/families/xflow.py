"""xflow -- MOVING-AVERAGE CROSSES AND RELATIVE VOLUME as entry triggers (the owner, 2026-10-20: "maybe start to incorporate more things
like crossovers or ema/vwma, or volume, RVOL"; the portfolio hunt). Written from the rules below before any result. No Level-2 feature
(FEATURES = ()): NQ, ES and GC, 1 contract, hold_to = 'day' (flat 15:58 ET); the exits are the sheet's / the heat map's.

THE AVERAGES (closed tf bars of the instance's day, from 00:00 ET; 18:00 for an evening instance): ema = the exponential average of the
last n closes (seeded with the first close), sma = their plain mean, vwma = sum(close x volume) / sum(volume) of the last n bars; vwap =
the session VWAP (the engine's, restarted at every pass start), rth = the VWAP anchored at 09:30 for the New York passes (03:00 London,
00:00 Asia: Template.vwr). An average with fewer than n bars behind it has no value: no cross is read.

RELATIVE VOLUME (rvol_m / m): the volume of the tf bar that just closed against the median volume of the SAME clock window on the 14 trade
dates before today (avwap.vol_ref: the minute-volume cache, else the date's own tape opened by its own date). Fewer than 10 dates: no
value, no trade. 0 = off.

THE FAMILIES
  ma_x        at a tf close the FAST average crosses the SLOW one (the sign of fast - slow changes between two closed bars) -> market with
              the cross at that close. side = vwap: a long only with the close above the session VWAP (a short below). Structure stop =
              the extreme of the last `swing` bars (a long: their lowest low).
  rvol_break  at a tf close the bar closes beyond the high / low of the `n` bars before it AND its relative volume >= m -> market with
              the break; structure stop = the bar's other extreme.
REGISTRATION as vwap_touch.py: join_blocks() puts the families into families/blocks.py's BASES and WRAPPED (blocks.py is not edited).
shortcut: avwap.vol_ref / avwap.minutes are imported, not copied, so a change there is not in this module's code stamp -- re-run the
xflow stores after changing them. Tests: engine/tests/test_xflow.py."""
from __future__ import annotations

from l2sim import Template

from . import avwap as AV

TFS = ("1", "5", "15", "30")
KINDS = ("ema", "sma", "vwma")


def _avg(kind: str, n: int, C: list, V: list, ema_prev):
    """The average of the last n closed bars, or None with fewer than n bars."""
    if len(C) < n:
        return None
    if kind == "sma":
        return sum(C[-n:]) / n
    if kind == "vwma":
        v = sum(V[-n:])
        return sum(c * w for c, w in zip(C[-n:], V[-n:])) / v if v > 0 else None
    return ema_prev                                    # ema: kept by the caller, bar by bar


class _Rvol(Template):
    """The relative volume of the tf bar that just closed (module docstring)."""
    SCREEN_TFS = TFS
    FEATURES = ()

    def fam_day(self, ctx):
        self._prior = [str(r["date"]) for r in self.dl]

    def rvol(self, ctx):
        b = (self.M[-1][0] // (self.tf * 60) + 1) * self.tf * 60
        ref = AV.vol_ref(ctx.root, self._prior, b - self.tf * 60, b)
        return None if ref is None else self.V[-1] / ref


class MaX(_Rvol):
    """ma_x (module docstring)."""
    DEFAULTS = {"fast": "ema", "fast_n": 9, "slow": "ema", "slow_n": 21, "side": "off", "rvol_m": 0.0, "swing": 3, "max_tr": 3}
    SCHEMA = {"fast": ("choice", KINDS), "fast_n": ("int", 2, 200), "slow": ("choice", KINDS + ("vwap", "rth")), "slow_n": ("int", 2, 400),
              "side": ("choice", ("off", "vwap")), "rvol_m": ("float", 0.0, 20.0), "swing": ("int", 1, 20), "max_tr": ("int", 1, 20)}

    def fam_day(self, ctx):
        super().fam_day(ctx)
        self.ef = self.es = None                       # the two ema values (when an ema is asked)
        self.nf = self.ns = 0
        self.pd = 0                                    # the sign of fast - slow at the previous close
        self.go = 0

    def _ema(self, prev, n, c):
        return c if prev is None else prev + 2.0 / (n + 1) * (c - prev)

    def fam_update(self, ctx):
        self.go = 0
        p, c = self.p, self.C[-1]
        self.ef = self._ema(self.ef, p["fast_n"], c) if p["fast"] == "ema" else None
        self.es = self._ema(self.es, p["slow_n"], c) if p["slow"] == "ema" else None
        f = _avg(p["fast"], p["fast_n"], self.C, self.V, self.ef)
        if p["slow"] in ("vwap", "rth"):
            w = self.vw() if p["slow"] == "vwap" else self.vwr()
            s = None if w is None else w[0]
        else:
            s = _avg(p["slow"], p["slow_n"], self.C, self.V, self.es)
        if f is None or s is None or f == s:
            return
        d = 1 if f > s else -1
        if self.pd and d != self.pd and self.sid is not None:
            ok = True
            if p["rvol_m"] > 0:
                r = self.rvol(ctx)
                ok = r is not None and r >= p["rvol_m"]
            if ok and p["side"] == "vwap":
                w = self.vw()
                ok = w is not None and (c - w[0]) * d > 0
            self.go = d if ok else 0
        self.pd = d

    def fam_signal(self, ctx):
        if self.go:
            k = int(self.p["swing"])
            if self.go > 0:
                self._mkt(ctx, "long", struct=min(self.L[-k:]))
            else:
                self._mkt(ctx, "short", struct=max(self.H[-k:]))


class RvolBreak(_Rvol):
    """rvol_break (module docstring)."""
    DEFAULTS = {"n": 20, "m": 2.0, "max_tr": 3}
    SCHEMA = {"n": ("int", 2, 200), "m": ("float", 0.5, 20.0), "max_tr": ("int", 1, 20)}

    def fam_signal(self, ctx):
        n = int(self.p["n"])
        if len(self.C) < n + 1:
            return
        c = self.C[-1]
        hi, lo = max(self.H[-n - 1:-1]), min(self.L[-n - 1:-1])
        if not (c > hi or c < lo):
            return
        r = self.rvol(ctx)
        if r is None or r < self.p["m"]:
            return
        if c > hi:
            self._mkt(ctx, "long", struct=self.L[-1])
        else:
            self._mkt(ctx, "short", struct=self.H[-1])


_WHY_X = ("When a fast average crosses a slow one the recent flow has turned against the older one; with volume behind the cross the turn "
          "is real participation, not drift. Who loses: the side still positioned for the old direction.")
FAMILIES = {
    "ma_x": (MaX, {}, False,
             "ma_x: at a tf close the fast average (ema / sma / vwma of fast_n) crosses the slow one (ema / sma / vwma of slow_n, or the "
             "session / 09:30 VWAP) -> market with the cross; rvol_m > 0 = the crossing bar's volume >= rvol_m x the 14-day median of its "
             "clock window; side vwap = only on the session VWAP's side; structure stop = the extreme of the last `swing` bars (portfolio "
             "hunt 2026-10-20)",
             {"rationale": _WHY_X, "complexity": 4,
              "variants": [{"fast": "ema", "fast_n": 9, "slow": "ema", "slow_n": 21}, {"fast": "ema", "fast_n": 9, "slow": "vwma", "slow_n": 21},
                           {"fast": "ema", "fast_n": 9, "slow": "rth", "slow_n": 21}]}),
    "rvol_break": (RvolBreak, {}, False,
                   "rvol_break: at a tf close the bar closes beyond the high / low of the n bars before it on relative volume >= m (its "
                   "volume vs the 14-day median of the same clock window) -> market with the break; structure stop = the bar's other "
                   "extreme (portfolio hunt 2026-10-20)",
                   {"rationale": "A breakout on far more volume than this time of day usually trades is new participation: it carries; "
                                 "a breakout on ordinary volume is noise. Who loses: the range traders fading the break.",
                    "complexity": 3,
                    "variants": [{"n": 20, "m": 1.5}, {"n": 20, "m": 2.0}, {"n": 20, "m": 3.0}]}),
}


def join_blocks() -> None:
    """Put the families into families/blocks.py's BASES and WRAPPED (as vwap_touch): the wrapped class a card runs. Idempotent."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()

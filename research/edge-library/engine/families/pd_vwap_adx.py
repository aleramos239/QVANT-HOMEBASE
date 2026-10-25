"""pd_vwap_adx -- MOMENTUM EXHAUSTION AT THE PRIOR HIGH / LOW, STRETCHED FROM VWAP, ADX TURNING DOWN (Bhatti 2026, "Momentum Exhaustion and
Fair Value Reversion: An ADX-conditioned VWAP Strategy in FX Markets", SSRN 6454659), written from the owner's reading of the paper before
any result. The paper is FX and has no backtest. No Level-2 feature (FEATURES = ()): NQ, ES and GC, 1 contract, one trade a day.

THE RULE (New York time; bars = the idea's own tf; the nyam pass stretched to 09:30-15:55 as vwap_adx does):
  * LOCATION: SHORT -- the bar's high is at or above the PRIOR RTH SESSION's high (09:30-16:00 of the prior trade date). LONG -- the bar's
    low is at or below the prior RTH session's low. (Not the engine's pdh / pdl: those are the whole Globex day.) A contract-roll day, or a
    prior date without a tape, has no level and does not trade.
  * STRETCH: SHORT -- the bar's close >= VWAP + k x ATR(14). LONG -- close <= VWAP - k x ATR(14). VWAP anchored at 09:30 (typical price
    (h + l + c) / 3 of the 1-minute bars, volume weighted, as vwap_adx); ATR(14) of the idea's own bars (the Template's).
  * EXHAUSTION: Wilder's ADX(14) of the tf bars since 00:00 ET, at this bar, is LOWER than at the bar before (the same arithmetic as
    families/vwapadx.Adx, which a test holds equal to families/blocks.adx_last).
  * All three on the SAME bar close -> market entry (fills at the next bar's open). Struct stop = the day's high (short) / low (long) since
    09:30, signal bar included. Max one trade a day; flat 15:55.
EXITS: the card's (hm40). The paper's own target -- a return to VWAP -- is not built: a signal's VWAP is known at the signal and could be
passed as tp_px, but the default stays the heat map's targets.
NO LOOK-AHEAD: the level is a prior date's session; every other input is a closed bar of today.
REGISTRATION as vwapadx.py: join_blocks(). Tests: engine/tests/test_pd_vwap_adx.py."""
from __future__ import annotations

import datetime as dt

import l2sim as S
import levels as L
from l2sim import HoldoutSealed, Template, _hms

from .vwapadx import Adx

OPEN_S = 34200                                      # 09:30 ET, seconds after 00:00 ET
PASS_END_S = 57300                                  # 15:55 ET: the pass ends and a trade is flattened here


def rth_level(root: str, iso: str):
    """(high, low) of the 09:30-16:00 ET prints of the trade date `iso` from its 5-minute bars (levels.session_bars), or None (no tape, or a
    sealed date the cache lacks: no level, no trade)."""
    try:
        got = L.session_bars(root, iso)
    except HoldoutSealed:
        return None
    if got is None:
        return None
    d = dt.date.fromisoformat(iso)
    end, hi, lo = got
    m = (end > S.et_ns(d, "09:30")) & (end <= S.et_ns(d, "16:00"))
    return (float(hi[m].max()), float(lo[m].min())) if m.any() else None


class PdVwapAdx(Template):
    """pd_vwap_adx (module docstring). State per day: the prior RTH level, the VWAP sums, the ADX now and a bar ago, the signal (self.sig)."""
    DEFAULTS = {"k": 1.5, "max_tr": 1}
    SCHEMA = {"k": ("float", 0.1, 5.0), "max_tr": ("int", 1, 5)}
    SCREEN_TFS = ("1", "5", "15", "30")
    FEATURES = ()

    def fam_filter(self, ids):
        return [s for s in ids if s == "nyam"]

    def fam_sessions(self) -> dict:
        return {"nyam": (OPEN_S, PASS_END_S)}

    def fam_day(self, ctx):
        self.vv = self.vp = 0.0                     # VWAP sums from 09:30: volume, volume x typical price
        self.mi = self.bi = 0                       # 1-minute bars read into the VWAP; tf bars given to the ADX
        self.ax = Adx()
        self.adx = self.adx_was = None
        self.sig = None                             # the signal at the last tf close: "long" / "short" / None
        self.lvl = None
        if self.day not in self.ROLLS and self.dl:
            self.lvl = rth_level(ctx.root, str(self.dl[-1]["date"]))

    def fam_times(self):
        return [_hms(PASS_END_S)]

    def fam_time(self, ctx, sec):
        if sec == PASS_END_S:
            self._cancel(ctx)
            ctx.flatten("time")

    def fam_update(self, ctx):
        self.sig = None
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
        a, b = self.adx, self.adx_was
        if self.lvl is None or self.vv <= 0 or not self.atr or a is None or b is None or not a < b:
            return
        vw, gap, step = self.vp / self.vv, self.p["k"] * self.atr, self.tf * 60
        if (M[-1][0] // step + 1) * step <= OPEN_S:  # the bar closed before 09:30: no VWAP yet
            return
        if self.H[-1] >= self.lvl[0] and self.C[-1] >= vw + gap:
            self.sig = "short"
        elif self.L[-1] <= self.lvl[1] and self.C[-1] <= vw - gap:
            self.sig = "long"

    def fam_signal(self, ctx):
        if self.sig is None:
            return
        r = self.rng(OPEN_S, PASS_END_S)            # the day's extremes since 09:30, signal bar included
        self._mkt(ctx, self.sig, struct=r[0] if self.sig == "short" else r[1])


FAMILIES = {
    "pd_vwap_adx": (PdVwapAdx, {}, False,
                    "pd_vwap_adx: a bar reaches the prior RTH session's high (low) AND closes >= VWAP(09:30) + k x ATR(14) (<= VWAP - k x ATR) "
                    "AND ADX(14) is lower than a bar ago -> fade at market; struct stop = the day's high (low) since 09:30; one trade a day; "
                    "flat 15:55. Bhatti 2026 (SSRN 6454659), the paper has no backtest",
                    {"rationale": "VWAP is the price institutions are benchmarked against; a move that has run far from it into the prior "
                                  "session's extreme, while its trend strength is already fading, is out of fuel and drifts back toward fair "
                                  "value. Who loses: the late momentum chasers buying the high after the push is spent.",
                     "complexity": 5,
                     "variants": [{"k": 1.0}, {"k": 1.5}, {"k": 2.0}],
                     "roots": ("NQ", "ES", "GC")}),
}


def join_blocks() -> None:
    """Put the family into families/blocks.py's BASES and WRAPPED (as vwapadx.py): the wrapped class a card runs, importable by name."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()

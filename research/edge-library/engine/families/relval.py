"""relval -- RELATIVE VALUE between NQ and ES as an entry trigger (portfolio hunt, 2026-10-21). The vault's one robust high-frequency
mechanism on ES (Quant-Portfolio note high-freq-1perday-edge-NQ-only, round 3: ES/NQ ratio reversion, ~1.8 a day, every year positive).
Written from the rule below before any result. No Level-2 feature (FEATURES = ()): NQ and ES, 1 contract; the exits are the sheet's.

THE GAP (at each tf close of the instance's own market; own = NQ or ES, partner = the other one): the 1-minute closes of the minutes
that START in the last `look` minutes before the decision AND in which both markets printed. Own = the Template's completed minutes;
partner = its own tape of the same trade date, only minutes that ENDED by the decision (the end of the own market's newest completed
minute). r = the log returns between consecutive common minutes; beta = cov(r_own, r_partner) / var(r_partner) over the window;
e = the running sum of r_own - beta x r_partner (the own market's move its partner does not explain), 0 at the window's first minute;
z = (e_last - mean(e)) / std(e). Fewer than MIN_SHARE x look common minutes, a flat partner (var 0) or a flat e (std 0): no value.

rv_fade   z >= k -> short the own market (it ran ahead of its partner); z <= -k -> long (it lagged). Market at the close; no structure
          level (the stops are the sheet's ATR / fixed points).

The partner tape opens with the seal of ITS OWN date (as avwap.minutes): the run's own seal already decided the trade date is open, and
nothing after the decision is read. Tests: engine/tests/test_relval.py."""
from __future__ import annotations

import numpy as np

import l2sim as S
from l2sim import Template

PARTNER = {"NQ": "ES", "ES": "NQ"}
MIN_SHARE = 0.8
_CL: dict = {}
_KEEP = 40


def closes(root: str, iso: str):
    """(start_ns, close) of every 1-minute bar of trade date `iso`'s tape, or None without a tape. Remembered per process."""
    key = (root, iso)
    if key in _CL:
        return _CL[key]
    d = S._date(iso)
    t = S.load_tape(iso, root, allow_holdout=S.ALLOW_BP if d <= S.BP_BUILD[1] else S.ALLOW_BT)
    out = None
    if t is not None and len(t.ts):
        k = np.asarray(t.ts) // S.MIN_NS
        last = np.flatnonzero(np.concatenate((k[1:] != k[:-1], [True])))         # the last print of each minute
        out = (k[last] * S.MIN_NS, np.asarray(t.px, np.float64)[last])
    _CL[key] = out
    while len(_CL) > _KEEP:
        _CL.pop(next(iter(_CL)))
    return out


def gap_z(own_start, own_c, par_start, par_c, look: int):
    """z of the own market's unexplained move over the common minutes given (module docstring), or None (pure)."""
    _, io, ip = np.intersect1d(own_start, par_start, assume_unique=True, return_indices=True)
    if len(io) < max(3, MIN_SHARE * look):
        return None
    ro, rp = np.diff(np.log(np.asarray(own_c)[io])), np.diff(np.log(np.asarray(par_c)[ip]))
    vp = float(rp.var())
    if vp <= 0:
        return None
    beta = float(((rp - rp.mean()) * (ro - ro.mean())).mean()) / vp
    e = np.concatenate(([0.0], np.cumsum(ro - beta * rp)))
    sd = float(e.std())
    return None if sd <= 0 else float((e[-1] - e.mean()) / sd)


class RvFade(Template):
    """rv_fade (module docstring)."""
    SCREEN_TFS = ("1", "5", "15", "30")
    FEATURES = ()
    DEFAULTS = {"k": 2.0, "look": 60, "max_tr": 4}
    SCHEMA = {"k": ("float", 0.5, 10.0), "look": ("int", 10, 600), "max_tr": ("int", 1, 20)}

    def fam_day(self, ctx):
        self._other = PARTNER.get(ctx.root)

    def gap(self):
        if self._other is None or not self.M:
            return None
        p = closes(self._other, self.day)
        if p is None:
            return None
        look = int(self.p["look"])
        end_s = self.M[-1][0] + 60                                   # the decision: the end of the newest completed own minute
        own = [m for m in self.M[-(look + 5):] if m[0] >= end_s - 60 * look]
        if not own:
            return None
        own_start = self.t0 + np.array([m[0] for m in own], np.int64) * S.NS
        cut = self.t0 + end_s * S.NS
        a, b = np.searchsorted(p[0], [own_start[0], cut - S.MIN_NS + 1])         # partner minutes that started in the window, ended by cut
        return gap_z(own_start, [m[4] for m in own], p[0][a:b], p[1][a:b], look)

    def fam_signal(self, ctx):
        z = self.gap()
        if z is None:
            return
        k = self.p["k"]
        if z >= k:
            self._mkt(ctx, "short")
        elif z <= -k:
            self._mkt(ctx, "long")


FAMILIES = {
    "rv_fade": (RvFade, {}, False,
                "rv_fade: at a tf close, the own market's 1-minute move over the last `look` minutes that its partner (NQ <-> ES) does not "
                "explain (beta-adjusted, z of the running gap) is >= k -> fade it: short the leader, long the laggard; no structure "
                "(portfolio hunt 2026-10-21)",
                {"rationale": "NQ and ES price the same US large-cap flow; when one runs ahead of the other in minutes, index arbitrage and "
                              "basket traders pull it back. Who loses: the momentum chaser who bought the leader at its stretch.",
                 "complexity": 3, "roots": ("NQ", "ES"),
                 "variants": [{"k": 1.5}, {"k": 2.0}, {"k": 2.5}]}),
}


def join_blocks() -> None:
    """Put the family into families/blocks.py's BASES and WRAPPED (as xflow): the wrapped class a card runs. Idempotent."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()

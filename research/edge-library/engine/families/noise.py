"""noise -- the NOISE BAND entry (the owner's request of 2026-10-08), written from its rule before any result. No Level-2 feature is read
(FEATURES = ()): NQ, ES and GC, 1 contract, hold_to = 'day' (flat 15:58 ET). Two independent sources describe it: the noise-area momentum of
Zarattini / Aziz / Barbon (2024) and Maroy (2025), and Matteo Conti's "vault break" (IQCapital, A0G14JYYVTk, research/edge-library/videos).

    noise_band   bar-based 1/5/15/30   nyam / mid / pm (+ asia / london / pre with the globex anchor); settings k, anchor (+ the Template's max_tr, dir)

THE RULE (fixed here, before any run):
  * ANCHOR. `rth`: the reference is the OPEN of the first 1-minute bar from 09:30 ET, the VWAP runs from 09:30. `globex`: the 01:00 ET bar
    (midnight Central, Conti's session open), the VWAP from 01:00. The anchor does NOT depend on the idea's session: a pm idea still reads the
    band and the VWAP of the anchor. If the first minute bar at / after the anchor starts more than 5 minutes late (a thin print hour), the day has
    no anchor and no trade.
  * A = the toolkit's daily ATR(14) (Template.datr: Wilder, the daily bars BEFORE the trade date -- the runner hands over prior days only; none
    until 15 exist). The same source `gap` and `mid_fade` use. Conti averages the daily ATR over 15 sessions; here it is 14, the toolkit's one.
  * BAND. noise_up = reference + k x A, noise_down = reference - k x A, both set once (when the anchor's open is known) and fixed for the day.
  * SIGNAL, read at a tf close and never later than it: LONG = the bar's CLOSE is strictly above noise_up AND strictly above the VWAP since the
    anchor (volume-weighted (h + l + c) / 3 of the 1-minute bars, the engine's VWAP rule, the bar just closed included); SHORT = the mirror
    (strictly below noise_down and below the VWAP). The order is a market order placed at that close: it fills at the next bar's open (the first
    print after the 85 ms placement latency). The anchor's open and the prior days are known at every bar after the anchor: nothing later is read.
  * SESSIONS. nyam, mid and pm for `rth`; asia, london, pre, nyam, mid, pm for `globex`: a session that is over before the anchor is dropped
    (fam_filter), since the band does not exist yet; the evening never runs.
  * ENTRIES. Inside the idea's session only (a tf close in (start, end], never in the last 5 minutes of it: the Template's rule), up to `max_tr` a
    session (default 3: Conti's), one position at a time; once a trade has exited the next qualifying close may enter again, on either side.
  * EXITS. None of its own: the standard table's stop / target cells and the flat time 15:58 ET, as every family gets them.
  * SIDES. `dir` is the Template's: both (default), long or short. A one-sided card sets it through limits.dir; the long and the short side are
    MIRROR units for the library (families.MIRROR: 'dir', as orb_confirm and tod_drift): each is judged on its own.

REGISTRATION. families/__init__.py picks this module up by itself (FAMILIES below). The idea toolkit (cards, `bp.py blocks`) reads the families through
families/blocks.py: its WRAPPED / BASES tables list the family modules by name. families/blocks.py is one of the files whose hash a store and a
lock remember (blueprint/runner.py code()), so adding a name to its module list would mark EVERY earlier store and lock "written by other code".
join_blocks() below puts this family into those two tables instead, once, when this module is imported (blocks always imports first: the
package loads its modules in name order) -- blocks.py stays byte for byte as it was.

COMPLEXITY 6 = the reference + band (open +/- k x A) + the close beyond the band and the VWAP -> market + re-entry up to max_tr + k + anchor + max_tr.
Tests: engine/tests/test_noise.py."""
from __future__ import annotations

from l2sim import Template

TFS = ("1", "5", "15", "30")
ANCHOR_S = {"rth": 34200, "globex": 3600}           # 09:30 ET . 01:00 ET (midnight Central), seconds after 00:00 ET
OPEN_TOL_S = 300                                    # the anchor's first minute bar may start at most 5 minutes after the anchor


class NoiseBand(Template):
    """noise_band (module docstring). State per day: ref (the anchor's open), up / dn (the band), vv / vp (the VWAP sums), go (+1 / -1 / 0: the
    signal of the tf bar that has just closed)."""
    DEFAULTS = {"k": 0.3, "anchor": "rth", "max_tr": 3}
    SCHEMA = {"k": ("float", 0.05, 3.0), "anchor": ("choice", tuple(ANCHOR_S)), "max_tr": ("int", 1, 5)}
    SCREEN_TFS = TFS
    FEATURES = ()

    def fam_filter(self, ids):
        """Only the sessions that end after the anchor: the band does not exist before it (rth: the NY sessions; globex: asia and on; never the evening)."""
        a = ANCHOR_S[self.p["anchor"]]
        return [s for s in ids if self.S[s][1] > a]

    def fam_day(self, ctx):
        self.vv = self.vp = 0.0                     # VWAP sums from the anchor: volume, volume x typical price
        self.mi = 0                                 # 1-minute bars already added
        self.ref = self.up = self.dn = None         # the anchor's open, noise_up, noise_down
        self.no_anchor = False                      # the anchor's bar came too late: no trade today
        self.go = 0

    def vwap(self):
        """The VWAP since the anchor over the minute bars seen so far, or None."""
        return self.vp / self.vv if self.vv > 0 else None

    def fam_update(self, ctx):
        self.go = 0
        a = ANCHOR_S[self.p["anchor"]]
        M = self.M
        for i in range(self.mi, len(M)):
            s, o, h, l, c, v = M[i]
            if s < a:
                continue
            if self.ref is None and not self.no_anchor:
                if s - a > OPEN_TOL_S:
                    self.no_anchor = True
                else:
                    self.ref = o
            if self.ref is not None and v > 0:
                self.vv += v
                self.vp += v * (h + l + c) / 3.0
        self.mi = len(M)
        if self.ref is None:
            return
        if self.up is None:
            da = self.datr()                        # prior days only; None until 15 daily bars exist
            if not da or da <= 0:
                return
            self.up, self.dn = self.ref + self.p["k"] * da, self.ref - self.p["k"] * da
        w, c = self.vwap(), self.C[-1]
        if w is None:
            return
        if c > self.up and c > w:
            self.go = 1
        elif c < self.dn and c < w:
            self.go = -1

    def fam_signal(self, ctx):
        if self.go:
            self._mkt(ctx, "long" if self.go > 0 else "short")


FAMILIES = {
    "noise_band": (NoiseBand, {}, False,
                   "noise_band: a bar closes beyond open +/- k x A (A = the daily ATR(14) of the days before) and the anchored VWAP -> market "
                   "entry at the next bar's open. rth = 09:30 ET open and VWAP; globex = 01:00 ET open (midnight Central) and VWAP. The band is "
                   "fixed for the day; entries inside the idea's session, up to max_tr a session, one position at a time; flat 15:58. Conti's "
                   "vault break averages 15 sessions; here A is the toolkit's daily ATR(14), the source gap uses",
                   {"rationale": "A move away from the open that is bigger than the day's usual noise, with price on the same side of the day's "
                                 "average price, shows one-way participation that trend followers and hedgers keep chasing, while the moves "
                                 "inside the band are the noise that market makers fade.",
                    "complexity": 6,
                    "variants": [{"k": k, "dir": d} for k in (0.2, 0.3, 0.4) for d in ("long", "short")]}),
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

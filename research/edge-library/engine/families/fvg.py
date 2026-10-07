"""fvg -- THE FAIR VALUE GAP as an entry trigger (the owner's idea of 2026-10-06), written from its definition before any
result. No Level-2 feature is read (FEATURES = ()): NQ, ES and GC, 1 contract, hold_to = 'day' (flat 15:58 ET).

    fvg   bar-based 1/5/15   all seven sessions

HOW THE RULE IS READ (fixed here, before any run; nothing below was chosen after a result):
  * THE GAP. Three tf bars in a row, bar 1 the oldest. An UP gap: bar 3's low is above bar 1's high -- the prices between
    them traded in bar 2 only. Its NEAR edge is bar 3's low (the side price comes back to first), its FAR edge bar 1's
    high. A DOWN gap is the mirror: bar 3's high below bar 1's low; near edge = bar 3's high, far edge = bar 1's low.
    Read at bar 3's close, on completed bars only.
  * IN THE SESSION. All three bars closed inside the instance's session (the third close of a session is the first that
    can show a gap): a gap that opened before the session is not this session's.
  * BIG ENOUGH. far edge to near edge >= min_gap x ATR14 of the tf at bar 3's close, and never less than one tick.
  * THE ENTRY trades WITH the gap (an up gap is bought), `mode`:
        touch   a limit at the near edge: the first time price comes back to the gap
        mid     a limit at the middle of the gap (rounded to the tick)
        go      a market order at bar 3's close: no wait for a return
    A limit fills on a one-tick trade-through, at its price (the engine's limit law), and the family runs with
    strict_limit: a fill print that is already through the stop is a loss.
  * THE NEWEST GAP COUNTS. While the instance is flat, a new gap (either side) cancels the entry still resting from an
    older one and takes its place. An entry rests until it fills, a newer gap replaces it, or the session's entries end.
    A gap that forms while a trade is open is not traded.
  * The stop and the target are the exit table's. With stop_mode 'struct' the stop is the gap's far edge.

COMPLEXITY 6 = the gap + inside the session + the newest replaces the older + the entry at the edge + min_gap + mode.
Tests: tests/test_fvg.py."""
from __future__ import annotations

from l2sim import Template

MODES = ("touch", "mid", "go")


class Fvg(Template):
    """fvg (module docstring). The gap of the three newest tf bars of the session, at least min_gap x ATR high -> an entry
    WITH the gap: a limit at its near edge (touch) or its middle (mid), or a market order (go)."""
    DEFAULTS = {"min_gap": 0.25, "mode": "touch"}
    SCHEMA = {"min_gap": ("float", 0.0, 10.0), "mode": ("choice", MODES)}
    SCREEN_TFS = ("1", "5", "15")
    SCREEN_RUN = {"strict_limit": True}
    FEATURES = ()

    def fam_session(self, ctx, s):
        self.gap, self.seen = None, 0

    def fam_update(self, ctx):
        """The gap this close shows, if any: (side, near edge, far edge). A new one cancels an older gap's resting entry."""
        self.gap = None
        if self.sid is None or self.sn == self.seen or self.sn < 3:      # (sn grows only at a close inside the session)
            return
        self.seen = self.sn
        h1, l1, h3, l3 = self.H[-3], self.L[-3], self.H[-1], self.L[-1]
        g = ("long", l3, h1) if l3 > h1 else ("short", h3, l1) if h3 < l1 else None
        if g is None or abs(g[1] - g[2]) < max(self.p["min_gap"] * self.atr, ctx.tick):
            return
        self.gap = g
        self._sync(ctx)
        if ctx.flat and self.orders:
            self._cancel(ctx)

    def fam_signal(self, ctx):
        if self.gap is None:
            return
        side, near, far = self.gap
        mode = self.p["mode"]
        if mode == "go":
            self._mkt(ctx, side, struct=far)
        else:
            self._lim(ctx, side, near if mode == "touch" else (near + far) / 2.0, struct=far)


FAMILIES = {
    "fvg": (Fvg, {}, False,
            "fvg: three bars of the session leave a fair value gap (bar 3's low above bar 1's high = an up gap, the mirror = a "
            "down gap) at least min_gap x ATR high -> an entry WITH the gap: touch = a limit at its near edge, mid = a limit at "
            "its middle, go = a market order at once; the newest gap replaces an older gap's resting entry",
            {"rationale": "A fair value gap is the footprint of one-sided urgency: orders that wanted in during the move were "
                          "left unfilled, so the first return into the gap meets that waiting interest and the traders who "
                          "faded the move are the ones who pay.",
             "complexity": 6,
             "variants": [{"min_gap": 0.1}, {"min_gap": 0.25}, {"min_gap": 0.5}]}),
}

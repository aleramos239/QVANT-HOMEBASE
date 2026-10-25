"""vwap_band_pb -- THE PULLBACK TO A VWAP SIGMA BAND, WITH THE TREND (the owner's VWAP band idea, 2026-10-25: "not sure the perfect
variant which band or if it needs another ema on top or maybe not a limit and enter after we close back inside or after we touch then
get displacement"). Written from the rule before any run. No Level-2 feature (FEATURES = ()): NQ, ES, GC.

THE RULE (fixed here, before any run):
  * THE LINE. The VWAP and its sigma (volume-weighted stdev of the typical price) of the 1-minute bars from the rth anchor (09:30 for
    the NY sessions, 03:00 london, 00:00 asia) when line = rth (the default: midday still reads the 09:30 VWAP), or from the session's
    own start when line = sess. Read at each tf close (the Template's vwr() / vw()). Band = VWAP +/- lvl x sigma.
  * THE STRETCH (the arm). A tf close above the upper band arms a LONG (the trend is up and stretched); below the lower band a SHORT.
    A tf close on the other side of the VWAP drops the arm (the trend is broken). Arms are kept across the sessions of one day.
  * THE ENTRY, `entry`:
      close  an armed long: the first tf close back at or below the upper band and still above the VWAP -> market long at that close.
      limit  an armed long, flat, last print above the band: a LIMIT at the upper band, re-priced at every tf close while armed (the
             engine's limit law: a one-tick trade-through fills it at its price). A close below the band with no fill drops the arm.
      disp   an armed long: a tf bar whose low reaches the upper band is the TOUCH; within `wait` tf bars after it (the touch bar
             included) the first green tf bar whose body >= disp x ATR(14) and that closes above the band -> market long at its close.
    The short is the mirror. An entry uses the arm up: a new stretch must arm it again.
  * THE STRUCTURE LEVEL (the hm40 "own" stop): close / limit = the VWAP at the decision; disp = the lowest low (highest high) since the
    touch bar.
  * Up to max_tr entries a session, one position at a time (the Template). EXITS: none of its own (the hm40 cells), flat 15:58 ET.
  * NOT in the rule: an EMA (the open layer's gate price_ema does that), a volume check, the 2nd touch.

NO LOOK-AHEAD: everything is read at a tf close from bars that have ended; a limit rests from a close for the bars after it.
Tests: engine/tests/test_vwap_band_pb.py."""
from __future__ import annotations

from l2sim import Template

TFS = ("1", "5", "15", "30")


class VwapBandPb(Template):
    DEFAULTS = {"lvl": 1.0, "entry": "close", "line": "rth", "disp": 1.0, "wait": 3, "max_tr": 2}
    SCHEMA = {"lvl": ("float", 0.25, 4.0), "entry": ("choice", ("close", "limit", "disp")), "line": ("choice", ("rth", "sess")),
              "disp": ("float", 0.1, 5.0), "wait": ("int", 1, 12), "max_tr": ("int", 1, 20)}
    SCREEN_TFS = TFS
    SCREEN_RUN = {"strict_limit": True}
    FEATURES = ()

    def fam_day(self, ctx):
        self.arm, self.touch, self.tlow, self.sig = 0, None, None, None

    def line(self):
        v = self.vwr() if self.p["line"] == "rth" else self.vw()
        return v if v is not None and v[1] > 0 else None

    def fam_update(self, ctx):
        self.sig = None
        v = self.line()
        if v is None or self.nb < 3:
            return
        m, b = v[0], float(self.p["lvl"]) * v[1]
        c, h, l, o = self.C[-1], self.H[-1], self.L[-1], self.O[-1]
        e, a = self.p["entry"], self.arm
        if a and (c - m) * a <= 0:                                   # closed through the VWAP: the trend is broken
            self.arm, self.touch = 0, None
            self._drop(ctx)
            return
        if a:
            band = m + a * b
            if e == "close" and (c - band) * a <= 0:
                self.sig = (a, m)
            elif e == "limit" and (c - band) * a < 0:
                self.arm = 0                                         # ran through the band without the order filling
                self._drop(ctx)
                return
            elif e == "disp":
                if self.touch is None and (l <= band if a > 0 else h >= band):
                    self.touch, self.tlow = 0, (l if a > 0 else h)
                if self.touch is not None:
                    self.tlow = min(self.tlow, l) if a > 0 else max(self.tlow, h)
                    if (c - o) * a > 0 and abs(c - o) >= float(self.p["disp"]) * self.atr and (c - band) * a > 0:
                        self.sig = (a, self.tlow)
                    else:
                        self.touch += 1
                        if self.touch >= int(self.p["wait"]):
                            self.touch = None                        # no displacement in time: wait for the next touch
        if not self.arm or self.sig:
            if c > m + b:
                self.arm, self.touch = (1, None) if self.arm != 1 else (1, self.touch)
            elif c < m - b:
                self.arm, self.touch = (-1, None) if self.arm != -1 else (-1, self.touch)

    def _drop(self, ctx):
        for r in self.orders:
            if r[0].status == "working":
                ctx.cancel(r[0])

    def can_enter(self, ctx):
        """The Template's rule, but this family's own resting limit does not stand in the way of its re-pricing."""
        self._sync(ctx)
        rest, self.orders = self.orders, []
        ok = super().can_enter(ctx)
        self.orders = rest
        return ok

    def fam_signal(self, ctx):
        if self.p["entry"] == "limit":
            self._drop(ctx)
            self.orders = [r for r in self.orders if r[0].status != "working"]
            v = self.line()
            if self.arm and v is not None:
                a = self.arm
                if self._lim(ctx, "long" if a > 0 else "short", v[0] + a * float(self.p["lvl"]) * v[1], struct=v[0]) is not None:
                    pass
            return
        if self.sig:
            a, st = self.sig
            if self._mkt(ctx, "long" if a > 0 else "short", struct=st) is not None:
                self.arm, self.touch = 0, None


FAMILIES = {
    "vwap_band_pb": (VwapBandPb, {}, False,
                     "vwap_band_pb: a tf close beyond the VWAP +/- lvl sigma band arms the trend's side; the pullback to that band -> enter "
                     "with the trend: on the close back inside (close), a limit AT the band re-priced each close (limit), or after a touch a "
                     "displacement bar (body >= disp x ATR) closing beyond the band (disp); a close through the VWAP drops the arm; own stop "
                     "= the VWAP (close, limit) or the low since the touch (disp); line rth = the 09:30 VWAP (owner 2026-10-25)",
                     {"rationale": "On a trend day the sigma band is where the trend's funds add on a pullback; those who fade the stretch "
                                   "at the band and late counter-trend entries lose when the trend resumes.",
                      "complexity": 4,
                      "variants": [{"lvl": 0.5}, {"lvl": 1.0}, {"lvl": 1.5}]}),
}


def join_blocks() -> None:
    """Put the family into families/blocks.py's BASES and WRAPPED (as vwap_touch). Idempotent."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()

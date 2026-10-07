"""liq -- LIQUIDITY LEVELS as an entry trigger (the owner's request of 2026-10-06), written from its definition before any result. No Level-2
feature is read (FEATURES = ()): NQ, ES and GC, 1 contract, hold_to = 'day' (flat 15:58 ET). The levels are engine/levels.py (prior day,
overnight, Asia 00:00-03:00, early London 02:00-05:00, London 03:00-08:25, the evening before 20:00-24:00, the last 5 days, the swing high / low: 50 5-minute bars each side, last 5 sessions; the equal highs / lows on NQ).

    liq   bar-based 1/5/15   every session; `levels` = one level name or "all", `mode` = sweep | break

HOW THE RULE IS READ (fixed here, before any run):
  * A LEVEL is a (high, low) pair of a window that has ended (levels.py). Each of its two prices is a liquidity pool: resting stops sit
    behind the high (above) and behind the low (below).
  * `sweep` (a reversal; the engine's sweep_rev rule on more levels): a tf bar trades beyond the price (the extreme is remembered) and a
    tf bar closes back on the inside of it -> market against the move: beyond a HIGH -> short, beyond a LOW -> long. The sweep extreme
    is passed as the structure (stop_mode 'struct'; the standard menu uses atr / pts / pct). One signal per price per session.
  * `break` (a continuation): a tf bar closes beyond the price while the bar before it closed on the inside -> market WITH the break.
    One signal per price per session; a close beyond a price whose previous close was beyond it too never signals.
  * Several prices at once: the first in the order of levels.NAMES; one trade at a time (the Template's rule).
  * `mode` holds OPPOSITE ideas (families.MIRROR): an idea holds one value under `fixed` and varies `levels`.
COMPLEXITY 5 = the level windows + the sweep / break trigger + once per price per session + the extreme as the structure + two settings.
Tests: tests/test_liq.py."""
from __future__ import annotations

import levels as LV
from l2sim import Template


class Liq(Template):
    """liq (module docstring)."""
    DEFAULTS = {"levels": "pd", "mode": "sweep"}
    SCHEMA = {"levels": ("choice", LV.NAMES + ("all",)), "mode": ("choice", ("sweep", "break"))}
    SCREEN_TFS = ("1", "5", "15")
    FEATURES = ()

    def fam_session(self, ctx, s):
        self.done, self.ext, self.sig = set(), {}, None

    def fam_day(self, ctx):
        self.done, self.ext, self.sig = set(), {}, None

    def fam_update(self, ctx):
        self.sig = None
        if self.sid is None or not self.nb:
            return
        h, l, c = self.H[-1], self.L[-1], self.C[-1]
        pc = self.C[-2] if self.nb > 1 else None
        for name, (hi, lo) in LV.levels(self, self.p["levels"]).items():
            for kind, px in (("hi", hi), ("lo", lo)):
                key = (name, kind)
                if key in self.done:
                    continue
                if self.p["mode"] == "sweep":
                    beyond = h > px if kind == "hi" else l < px
                    if beyond:
                        e = self.ext.get(key)
                        self.ext[key] = (h if kind == "hi" else l) if e is None else (max(e, h) if kind == "hi" else min(e, l))
                    inside = c <= px if kind == "hi" else c >= px
                    if key in self.ext and inside:
                        self.done.add(key)
                        self.sig = self.sig or ("short" if kind == "hi" else "long", self.ext[key])
                else:
                    first = c > px and (pc is None or pc <= px) if kind == "hi" else c < px and (pc is None or pc >= px)
                    if first:
                        self.done.add(key)
                        self.sig = self.sig or ("long" if kind == "hi" else "short", px)

    def fam_signal(self, ctx):
        if self.sig:
            self._mkt(ctx, self.sig[0], struct=self.sig[1])


FAMILIES = {
    "liq": (Liq, {}, False,
            "liq: the highs and lows of the prior day, overnight, Asia, London, the evening before, the last 5 days and the last untraded swing "
            "(50 5-minute bars each side) and, on NQ, equal highs / lows are liquidity levels -> sweep = a bar trades beyond one and closes back inside: fade it; break = the "
            "first close beyond it: follow it; one signal per price per session",
            {"rationale": "Stops rest behind the obvious highs and lows, so price is pulled to them; the traders who sit behind a level are the "
                          "fuel for a sweep and a reversal, or for a break that runs.",
             "complexity": 5,
             "variants": [{"mode": m, "levels": lv} for m in ("sweep", "break") for lv in ("pd", "on", "ldn", "asia2000")]}),
}

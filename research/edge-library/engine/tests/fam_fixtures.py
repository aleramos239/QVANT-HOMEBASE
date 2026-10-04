"""Strategy classes for tests/test_families.py and tests/test_screen.py (NOT a test module, NOT in the registry). They live in
a module of their own so worker processes can import them by name."""
import l2ref
import l2sim


class ToyImb(l2sim.Template):
    """Follows the top-10 imbalance at a tf close (the contract's minimal shape: features only through ctx.feat)."""
    DEFAULTS = {"k": 0.15}
    SCHEMA = {"k": ("float", 0.0, 1.0)}
    SCREEN_TFS = ("5",)
    FEATURES = ("imb10",)

    def fam_signal(self, ctx):
        v = ctx.feat("imb10")
        if v is not None and v == v and abs(v) >= self.p["k"]:
            self._mkt(ctx, "long" if v > 0 else "short")


class ToyBracket(l2sim.Template):
    """Rests a stop entry on BOTH sides of the last price (an OCO pair): both_sides must be declared True."""
    SCREEN_TFS = ("5",)
    FEATURES = ("imb10",)

    def fam_signal(self, ctx):
        v, lp = ctx.feat("imb10"), ctx.last_price
        if v is not None and v == v and lp is not None:
            self._arm(ctx, [("long", lp + self.atr, None, None), ("short", lp - self.atr, None, None)], ttl=3)


class Leaky(l2ref.Donchian):
    """BROKEN ON PURPOSE: state that survives a session (`seen` is never reset) while session_independent stays True.
    One worker sees the days in order and trades every second one; eight workers give every chunk a fresh instance."""
    SCREEN_TFS = ("5",)
    FEATURES = ("imb10",)

    def fam_day(self, ctx):
        self.seen = getattr(self, "seen", 0) + 1

    def fam_signal(self, ctx):
        if self.seen % 2 == 0:
            super().fam_signal(ctx)


class Crashes(ToyImb):
    """Raises in every session of one month (a dropped session is not a screen result)."""

    def fam_day(self, ctx):
        if self.day.startswith("2023-08"):
            raise RuntimeError("boom")


# ---- edge-library fixtures (tests/test_edge_*.py): library families without Level-2 features -------------------------------
class EdgeDonch(l2ref.Donchian):
    """A ported family as a family author registers it: no features, every screen tf it supports."""
    SCREEN_TFS = ("15",)
    FEATURES = ()


class EdgeStraddleT(l2ref.StraddleT):
    """Family A as a family author registers it (time-fired: the runner adds its time-shuffle null)."""


EDGE_LIB = {"rationale": "trend continuation: a close beyond the recent channel means late sellers must cover into the move",
            "complexity": 3, "variants": [{"n": 10}, {"n": 20}]}
EDGE_LIB_T = {"rationale": "at the US cash open new orders arrive and price leaves its pre-open balance; a straddle rides the break",
              "complexity": 4, "variants": [{"at": "09:30", "off_mode": "atr", "off_val": 0.5}]}

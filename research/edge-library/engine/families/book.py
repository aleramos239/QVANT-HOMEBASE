"""Book families of the Stage A screen: B1 bimb_follow, B2 bimb_fade, B3 thin_side.

Definitions, pre-registered defaults and every detail the SPEC left open: FAMILIES.md, section "Book families" (written
before the first run; frozen). Tests: tests/test_fam_book.py.

All three: one market entry at a tf-bar close on the newest usable ONE-minute row (ctx.feat / ctx.feat_window only), the
Template's ATR stop and R target, no resting order (both_sides False), no state at all between decisions. The Template decides
WHEN `fam_signal` runs (tf-bar close inside a session, flat, < max_tr entries, not in the last 5 minutes of the session).
"""
from __future__ import annotations

import numpy as np

import l2sim as S

Z_WIN = 60          # B1 / B2: the trailing window, minutes before the newest usable row's minute
Z_MIN = 30          # ... and the fewest valid values in it
EPS = 1e-6          # B3: tolerance on a ratio threshold (float32 column; an exact 0.60 / 0.90 is inside, as l2sim.depth_regime)


def fresh(ctx, t_utc) -> bool:
    """The newest usable row is the minute that just ended (stamp + 60 s = the decision time), never a stale one."""
    return t_utc is not None and int(t_utc) + 60 == ctx.now_ns // S.NS


def imb_z(ctx, col: str):
    """B1 / B2: z-score of the newest usable `col` value against the rows stamped in the Z_WIN minutes before it (book_ok and
    finite only, >= Z_MIN of them, population std > 0). None = no signal (stale / masked / NaN row, short or flat history)."""
    w, ok, t = (ctx.feat_window(c, Z_WIN + 1) for c in (col, "book_ok", "t_utc"))
    if len(w) < Z_MIN + 1 or not fresh(ctx, t[-1]) or not ok[-1] or not np.isfinite(w[-1]):
        return None
    keep = ok[:-1].astype(bool) & np.isfinite(w[:-1]) & (t[:-1] >= t[-1] - 60 * Z_WIN)
    h = w[:-1][keep].astype(np.float64)
    if len(h) < Z_MIN:
        return None
    sd = float(h.std())
    if not sd > 0.0:
        return None
    return (float(w[-1]) - float(h.mean())) / sd


def thin_side(ctx, thin: float, hold: float):
    """B3: 'bid' / 'ask' = the side whose top-10 depth is <= `thin` x its trailing-15-minute median while the other side's is
    >= `hold` x its own; None = no signal. The columns hold ratio - 1."""
    if not fresh(ctx, ctx.feat("t_utc")) or not ctx.feat("book_ok"):
        return None
    b, a = ctx.feat("bid10_rel15"), ctx.feat("ask10_rel15")
    if b is None or a is None or b != b or a != a:
        return None
    rb, ra = 1.0 + b, 1.0 + a
    if rb <= thin + EPS and ra >= hold - EPS:
        return "bid"
    if ra <= thin + EPS and rb >= hold - EPS:
        return "ask"
    return None


class BimbFollow(S.Template):
    """B1 bimb_follow: |z(top-N imbalance vs its trailing 60 minutes)| >= k at a tf-bar close -> market entry WITH the sign of z
    (z > 0: the bid side is heavier than its own trailing hour -> long)."""
    DEFAULTS = {"k": 2.0, "n_lv": "10"}
    SCHEMA = {"k": ("float", 0.5, 6.0), "n_lv": ("choice", ("10", "3"))}
    SCREEN_TFS = ("1", "5")
    FEATURES = ("imb10", "imb3", "book_ok", "t_utc")
    SIGN = 1                                    # +1 follow, -1 fade

    def fam_signal(self, ctx):
        z = imb_z(ctx, "imb10" if self.p["n_lv"] == "10" else "imb3")
        if z is not None and abs(z) >= self.p["k"]:
            self._mkt(ctx, "long" if z * self.SIGN > 0 else "short")


class BimbFade(BimbFollow):
    """B2 bimb_fade: B1's trigger, entry AGAINST the sign of z."""
    SIGN = -1


class ThinSide(S.Template):
    """B3 thin_side: one side's top-10 depth <= 0.60 x its trailing-15-minute median while the other side's >= 0.90 x its own
    -> market entry toward the thin side (bid thin -> short, ask thin -> long)."""
    DEFAULTS = {"thin": 0.60, "hold": 0.90}
    SCHEMA = {"thin": ("float", 0.10, 0.80), "hold": ("float", 0.85, 1.50)}
    SCREEN_TFS = ("1", "5")
    FEATURES = ("bid10_rel15", "ask10_rel15", "book_ok", "t_utc")

    def fam_signal(self, ctx):
        s = thin_side(ctx, self.p["thin"], self.p["hold"])
        if s is not None:
            self._mkt(ctx, "short" if s == "bid" else "long")


FAMILIES = {                      # name -> (StrategyClass, default_inputs, both_sides, notes)
    "bimb_follow": (BimbFollow, {}, False, "B1: |z(imb10, trailing 60 min)| >= 2 at a tf close -> market WITH the sign of z"),
    "bimb_follow_n3": (BimbFollow, {"n_lv": "3"}, False, "B1, N = 3: |z(imb3, trailing 60 min)| >= 2 at a tf close -> market WITH the sign of z"),
    "bimb_fade": (BimbFade, {}, False, "B2: |z(imb10, trailing 60 min)| >= 2 at a tf close -> market AGAINST the sign of z"),
    "bimb_fade_n3": (BimbFade, {"n_lv": "3"}, False, "B2, N = 3: |z(imb3, trailing 60 min)| >= 2 at a tf close -> market AGAINST the sign of z"),
    "thin_side": (ThinSide, {}, False, "B3: one side's top-10 depth <= 0.60 x its 15-min median, the other >= 0.90 -> market toward the thin side"),
}

"""B4 wall_bounce / B5 wall_break (SPEC "Stage A screen"). The exact, pre-registered definitions are in FAMILIES.md
"Walls" (written before either family was run) + its addendum of 2026-10-02 (B4 conformed to the SPEC line before any
screen run: the limit also rests when the last print is 1 tick in front of the wall): this module implements that text
and nothing else.

A wall on a side = that side's LARGEST level of the top-10 near book with wall_sz >= m x med_sz. Its price comes from the
snapshot's own best bid / ask (tape coordinates) and the wall's tick distance: bid_px - bid_wall_dist x tick,
ask_px + ask_wall_dist x tick. Price = ctx.last_price. Rows are read through ctx.feat(name, back >= 0) only.
"""
from __future__ import annotations

import math

import l2sim as S

COLS = {"bid": ("bid_px", "bid_wall_dist", "bid_wall_sz", "bid_med_sz"),
        "ask": ("ask_px", "ask_wall_dist", "ask_wall_sz", "ask_med_sz")}
FEATURES = COLS["bid"] + COLS["ask"] + ("t_utc", "book_ok")
FRONT = 1                                           # B4: the limit rests this many ticks in front of the wall
BEYOND = 4                                          # B4 / B5: the struct stop is this many ticks beyond the wall price
SIDE = {1: "long", -1: "short"}


def fresh(ctx, rows: int = 1) -> bool:
    """The newest usable row is the minute that just ended and the `rows` newest rows are consecutive minutes."""
    t = ctx.feat("t_utc")
    if t is None or t + 60 != ctx.now_ns // S.NS:
        return False
    return all(ctx.feat("t_utc", k) == t - 60 * k for k in range(1, rows))


def wall(ctx, side: str, m: float, back: int = 0):
    """One side of the row `back` minutes old -> (wall price in whole ticks, is it a wall: wall_sz >= m x med_sz), or
    None when the row is not valid for that side (no row, book_ok False, a NaN column, med_sz <= 0)."""
    if not ctx.feat("book_ok", back):
        return None
    px, dist, sz, med = (ctx.feat(c, back) for c in COLS[side])
    if not all(v is not None and math.isfinite(v) for v in (px, dist, sz, med)) or med <= 0:
        return None
    return round(px / ctx.tick) + (-1 if side == "bid" else 1) * round(dist), sz >= m * med


class WallBounce(S.Template):
    """B4 wall_bounce: a wall with the last print 1..near ticks in front of it -> LIMIT fade 1 tick in front of the
    wall, stop 4 ticks beyond the wall (floor 0.25 ATR), target tgt_r x stop. One order per decision, alive one tf bar.
    Screened with strict_limit (the stop is live on the fill print). The limit is never beyond the last print: 2+ ticks
    in front it is passive, 1 tick in front it rests AT the last print; either way it fills only on a print at / through
    the wall price (the simulator's 1-tick trade-through law), at the limit price."""
    DEFAULTS = {"stop_mode": "struct", "m": 5.0, "near": 2}
    SCHEMA = {"m": ("float", 1.5, 20.0), "near": ("int", 1, 10)}
    SCREEN_TFS = ("1", "5")
    FEATURES = FEATURES
    SCREEN_RUN = {"strict_limit": True}

    def fam_signal(self, ctx):
        lp = ctx.last_price
        if lp is None or not fresh(ctx):
            return
        t, hits = ctx.tick, []
        for side, sd in (("bid", 1), ("ask", -1)):              # bid wall -> long, ask wall -> short
            w = wall(ctx, side, self.p["m"])
            if w is not None and w[1] and 0 < sd * (round(lp / t) - w[0]) <= self.p["near"]:
                hits.append((sd, w[0] * t))
        if len(hits) != 1:                                      # no wall in reach, or one on each side: no order
            return
        sd, w = hits[0]
        self._lim(ctx, SIDE[sd], w + sd * FRONT * t, struct=w - sd * BEYOND * t, ttl=1)

    def _lim(self, ctx, side, px, struct=None, tp_px=None, ttl=None, tag=None):
        """Template._lim with ONE difference: a limit AT the last print rests too (the Template refuses it as 'not
        passive', which silently dropped the SPEC's 1-tick case). A limit BEYOND the last print is still refused. Same
        brackets, same bookkeeping, same fill law (ctx.limit_entry: a 1-tick trade-through, at the limit price)."""
        lp = ctx.last_price
        if lp is None or not self.allowed(side):
            return None
        sd = 1 if side == "long" else -1
        if (lp - px) * sd < 0:
            return None
        d = self._dist(ctx, px, struct)
        o = ctx.limit_entry(side, px, sl=px - sd * d, tp=self._tp(sd, px, d, tp_px), **S._tagkw(tag))
        self.orders.append([o, self.nb + ttl if ttl else None, False])
        return o


class WallBreak(S.Template):
    """B5 wall_break: a wall standing at one price on the `stand` snapshots before the newest one is gone in the newest
    one and the last print is beyond its price -> STOP entry 1 tick beyond the last print in the break direction,
    struct stop 4 ticks back beyond the wall price (floor 0.25 ATR), target tgt_r x stop. One order, alive one tf bar."""
    DEFAULTS = {"stop_mode": "struct", "m": 5.0, "stand": 2}
    SCHEMA = {"m": ("float", 1.5, 20.0), "stand": ("int", 2, 10)}
    SCREEN_TFS = ("1", "5")
    FEATURES = FEATURES

    def broken(self, ctx, side):
        """Wall price (whole ticks) of the wall of `side` that stood on rows back = 1..stand and is gone at back = 0."""
        m, w = self.p["m"], None
        for k in range(1, self.p["stand"] + 1):                 # standing: a wall, at the same price, on every row
            r = wall(ctx, side, m, k)
            if r is None or not r[1] or (w is not None and r[0] != w):
                return None
            w = r[0]
        now = wall(ctx, side, m)
        if now is None or (now[0] == w and now[1]):             # newest row unknown, or the wall is still there
            return None
        return w

    def fam_signal(self, ctx):
        lp = ctx.last_price
        if lp is None or not fresh(ctx, self.p["stand"] + 1):
            return
        t, hits = ctx.tick, []
        for side, sd in (("bid", -1), ("ask", 1)):              # bid wall broken -> short, ask wall broken -> long
            w = self.broken(ctx, side)
            if w is not None and sd * (round(lp / t) - w) > 0:  # the last print is beyond the wall price
                hits.append((sd, w * t))
        if len(hits) != 1:
            return
        sd, w = hits[0]
        self._arm(ctx, [(SIDE[sd], lp + sd * t, w - sd * BEYOND * t, None)], ttl=1)


FAMILIES = {
    "wall_bounce": (WallBounce, {}, False,
                    "B4: bid/ask wall (largest top-10 level >= 5 x median level) with the last print 1-2 ticks in front -> "
                    "limit 1 tick in front of it (at the last print in the 1-tick case), stop 4 ticks beyond (floor 0.25 "
                    "ATR), 2R; strict_limit. Not hand-executable at tf 1: not an Apex 300K PA candidate as built"),
    "wall_break": (WallBreak, {}, False,
                   "B5: a wall standing >= 2 consecutive snapshots is gone and the last print is beyond its price -> stop "
                   "entry 1 tick beyond the last print, struct stop wall -/+ 4 ticks (floor 0.25 ATR), 2R. C2 null "
                   "degenerate for this family (FAMILIES.md walls addendum): read ctrl_trades before any C2 lift. Not "
                   "hand-executable at tf 1: not an Apex 300K PA candidate as built"),
}

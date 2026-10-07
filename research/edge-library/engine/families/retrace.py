"""open_retrace -- FADE THE OPENING MOVE WHEN IT GIVES BACK HALF (the owner's idea of 2026-10-07), written from his words before
any result. NQ (ES and GC run the same rule), 1 contract, hold_to = 'day' (flat 15:58 ET), the New York morning session.

    open_retrace   bar-based 1 / 5   nyam (09:30-11:00 ET)

HOW THE RULE IS READ (fixed here, before any run; nothing below was chosen after a result):
  * THE SIDE OF THE DAY. The first 5-minute candle of the session (09:30-09:35, from the 1-minute bars) is up when its close is
    above its open, down when below; a doji (close = open) has no side and no trade. Known at 09:35, never earlier.
  * THE MOVE. From the 09:30 open (the first 1-minute bar's open) to the furthest price since then in the candle's direction:
    the highest high on an up day, the lowest low on a down day, over the completed 1-minute bars. It keeps growing while price
    makes new extremes: the move is measured again at every bar close.
  * THE ENTRY IS AGAINST THE MOVE. When price gives back `level` of the move (default 0.5: half of it), a stop order trades it:
    up day -> SELL at extreme - level x move; down day -> BUY at extreme + level x move. A resting stop entry, as the owner asked,
    so it fills when price trades down (up day) / up (down day) through the level. At every bar close the level is measured again
    from the new extreme: a resting order whose level moved is cancelled and placed again.
  * ONLY AFTER A RALLY. The order is placed only while price is still on the far side of its level (above it on an up day); when
    price is already through it (the candle itself gave back half), nothing rests until a new extreme puts price above the new
    level again.
  * THE STOP IS THE STRUCTURE'S. Stop = the extreme of the move (an up day's high); the stop part of a table cell is ignored
    (`_dist`), the Template's floor (a quarter of the ATR) applies. The TARGET is the table's: tgt_r x the stop distance (0 = none).
    At level 0.5 and tgt_r 1 that is the owner's rule: the target falls on the 09:30 open, the start of the move, 1 : 1.
  * ONE TRADE A DAY (max_tr 1), only inside the session; the position is flat by 15:58 ET like every library trade.

SETTING: level -- how much of the move price must give back before the entry (0.4 / 0.5 / 0.6 are the library's three). The
distance from the entry back to the open is (1 - level) / level of the stop distance: that is the reward : risk of a target at the
open (1.5 : 1, 1 : 1, 0.67 : 1); the table's targets (0.5 .. 3 x the stop, or none) are the reward : risk heat map.

COMPLEXITY 6 = the first candle's side + the running extreme + the level + the stop at the extreme + the target at the open +
one trade a day.  Tests: tests/test_retrace.py."""
from __future__ import annotations

from l2sim import Template

OPEN_S = 34200                                      # 09:30 ET in seconds after 00:00 ET
FIRST_S = 300                                       # the first candle: 5 minutes


class OpenRetrace(Template):
    """open_retrace (module docstring): the first 5-minute candle gives the side, the move from the 09:30 open runs to its extreme,
    and a stop order trades the give-back of `level` of it against the move, stop at the extreme, target at the open."""
    DEFAULTS = {"level": 0.5, "stop_mode": "struct", "tgt_r": 1.0, "max_tr": 1}      # (tgt_r 1 at level 0.5 = the target on the open)
    SCHEMA = {"level": ("float", 0.1, 0.9)}
    SCREEN_TFS = ("1", "5")
    FEATURES = ()

    def fam_filter(self, ids):
        return [s for s in ids if s == "nyam"]

    def fam_session(self, ctx, s):
        self.plan = self.armed = None

    def _dist(self, ctx, ref, struct):
        """The structure sets the stop distance; a table cell's stop is ignored (the stop is the extreme, floored like every stop)."""
        if struct is None:
            return super()._dist(ctx, ref, struct)
        return max(abs(ref - struct), 0.25 * self.atr, 2 * ctx.tick)

    def fam_update(self, ctx):
        """The plan this close shows: (side, level price, extreme, open) or None. A resting order whose level moved is cancelled."""
        self.plan = None
        if self.sid != "nyam":
            return
        xs = [m for m in self.M if m[0] >= OPEN_S]
        first = [m for m in xs if m[0] < OPEN_S + FIRST_S]
        if len(first) < 5 or first[0][0] != OPEN_S:               # the candle is not whole yet (or the open has no print)
            return
        o0, c5 = first[0][1], first[-1][4]
        up = 1 if c5 > o0 else -1 if c5 < o0 else 0
        if up == 0:
            return
        ext = max(m[2] for m in xs) if up > 0 else min(m[3] for m in xs)
        move = abs(ext - o0)
        if move <= 0:
            return
        t = ctx.tick
        px = round((ext - up * float(self.p["level"]) * move) / t) * t
        self.plan = ("short" if up > 0 else "long", px, ext, o0)
        self._sync(ctx)
        if ctx.flat and self.orders and self.armed != self.plan:  # the extreme grew: the old level is stale
            self._cancel(ctx)
            self.armed = None

    def fam_signal(self, ctx):
        if self.plan is None:
            return
        side, px, ext, o0 = self.plan
        if self._arm(ctx, [(side, px, ext, None)]):
            self.armed = self.plan


FAMILIES = {
    "open_retrace": (OpenRetrace, {}, False,
                     "open_retrace: the first 5-minute candle of 09:30 gives the side, the move runs from the 09:30 open to its "
                     "extreme, and a resting stop order trades the give-back of `level` (half) of it AGAINST the move; stop at the "
                     "extreme, target tgt_r x the stop (1 at half = the open), one trade a day",
                     {"rationale": "The first minutes of the cash open are a rush of orders that had to trade now; once that rush "
                                   "gives back half its move the traders who chased it are offside and the unfilled orders at the "
                                   "start of the move pull price back toward the open.",
                      "complexity": 6,
                      "variants": [{"level": 0.4}, {"level": 0.5}, {"level": 0.6}]}),
}

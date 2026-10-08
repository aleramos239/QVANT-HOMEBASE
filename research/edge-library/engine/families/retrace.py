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


class Judas(Template):
    """judas (v2 of open_retrace, the owner's redefinition of 2026-10-07; drops the first 5-minute candle).

    THE JUDAS MOVE. From the 09:30 open (the first 1-minute bar's open) the FIRST side to travel at least `thrust` x the prior daily
    ATR14 sets the direction (a bar that reaches both sides at once, or no daily ATR yet: no trade that day). From then on the extreme
    of that direction is tracked over the completed 1-minute bars: M = |extreme - open|, the move.
    THE REVERSAL. A resting STOP order trades half of it back: up move -> SELL at extreme - 0.5 M; down move -> BUY at extreme + 0.5 M.
    It rests only for `cap_min` minutes after the bar that set the extreme (a new extreme re-places it and restarts the clock): a slow
    drift back is a trend, not a Judas. Nothing rests while price is already through the level.
    THE EXITS ARE IN UNITS OF THE MOVE (the owner's grid): stop = `stop_m` x M beyond the entry (0.5 = the extreme itself), target =
    `tgt_m` x M back from the entry (0.5 = the open; 0 = none). One trade a day, entries from 09:30 until `until` minus 5 minutes (default 11:00: 10:55), flat by 15:58 ET."""
    DEFAULTS = {"thrust": 0.25, "stop_m": 0.5, "tgt_m": 0.5, "cap_min": 15, "until": "11:00", "stop_mode": "struct", "tgt_r": 0.0, "max_tr": 1}      # tgt_r 0: only tgt_m sets a target
    SCHEMA = {"thrust": ("float", 0.02, 1.0), "stop_m": ("float", 0.05, 5.0), "tgt_m": ("float", 0.0, 5.0), "cap_min": ("int", 1, 120),
              "until": ("choice", ("11:00", "12:00", "13:30", "15:55"))}      # the morning session's end: entries stop 5 minutes before it (default 11:00 = 10:55)
    SCREEN_TFS = ("1",)
    FEATURES = ()

    def fam_filter(self, ids):
        return [s for s in ids if s == "nyam"]

    def fam_sessions(self) -> dict:
        h, m = str(self.p["until"]).split(":")
        return {"nyam": (OPEN_S, int(h) * 3600 + int(m) * 60)}      # the window of the entries: from the open to `until`

    def fam_session(self, ctx, s):
        self.plan = self.armed = None
        self.dir = 0
        self.dead = False
        self.ext = self.t_ext = None

    def _dist(self, ctx, ref, struct):
        if struct is None:
            return super()._dist(ctx, ref, struct)
        return max(abs(ref - struct), 0.25 * self.atr, 2 * ctx.tick)

    def fam_update(self, ctx):
        self.plan = None
        if self.sid != "nyam" or self.dead:
            return
        xs = [m for m in self.M if m[0] >= OPEN_S]
        if not xs or xs[0][0] != OPEN_S:                           # no print in the 09:30 minute: the open is unknown
            return
        a = self.datr()
        if a is None:
            return
        o0 = xs[0][1]
        if self.dir == 0:
            d = float(self.p["thrust"]) * a
            up, dn = max(m[2] for m in xs) - o0 >= d, o0 - min(m[3] for m in xs) >= d
            if up and dn:
                self.dead = True                                    # both sides in the bars so far: which came first is unknown
                return
            if not (up or dn):
                return
            self.dir = 1 if up else -1
            self.ext = None
        # the running extreme and the end of the bar that set it (a bar that ties the extreme does not restart the clock)
        for m in xs:
            hi, st = (m[2], m[0] + 60) if self.dir > 0 else (m[3], m[0] + 60)
            if self.ext is None or (hi > self.ext if self.dir > 0 else hi < self.ext):
                self.ext, self.t_ext = hi, st
        now_s = (ctx.now_ns - self.t0) // 1_000_000_000
        move = abs(self.ext - o0)
        t = ctx.tick
        px = round((self.ext - self.dir * 0.5 * move) / t) * t
        stale = now_s >= self.t_ext + int(self.p["cap_min"]) * 60
        if not stale and move > 0:
            sd = self.dir
            stop = px + sd * float(self.p["stop_m"]) * move
            tgt = None if float(self.p["tgt_m"]) <= 0 else px - sd * float(self.p["tgt_m"]) * move
            self.plan = ("short" if sd > 0 else "long", px, stop, tgt)
        self._sync(ctx)
        if ctx.flat and self.orders and self.armed != self.plan:    # a new extreme moved the level, or the clock ran out
            self._cancel(ctx)
            self.armed = None

    def fam_signal(self, ctx):
        if self.plan is None:
            return
        side, px, stop, tgt = self.plan
        if self._arm(ctx, [(side, px, stop, tgt)]):
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
    "judas": (Judas, {}, False,
              "judas: the first side to move `thrust` x the daily ATR from the 09:30 open is the Judas move; half of it given back within "
              "cap_min minutes of its extreme is traded AGAINST it by a resting stop order; stop and target in units of the move",
              {"rationale": "A big, fast push away from the cash open that gives half back is the sign of orders that had to trade now and "
                            "are offside: the traders who chased the push pay when price returns toward where the day started.",
               "complexity": 6,
               "variants": [{"thrust": 0.2}, {"thrust": 0.25}, {"thrust": 0.3}]}),
}

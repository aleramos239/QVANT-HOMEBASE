"""ranges -- THE THREE WAYS TO MARK A RANGE for premium / discount and OTE (the owner's choice, 2026-10-07, from the charts pages and the
build-days study 2026-10-07-no-range-definition-beats-random-ranges). Pure functions of the 5-minute bars (high, low) a decision has seen,
oldest first, the last bar the last CLOSED one. Each returns (low, high, d) of the range at that last bar, d = +1 when the leg points UP
(its low came first) and -1 when it points DOWN, or None. Points are NQ points.

  move   THE MOVE IN PROGRESS. A zigzag of MOVE_PTS = 200 points: price must reverse that far from an extreme to turn the leg. The range runs
         from the last turning point to the extreme reached since (the leg that is still being drawn). None until one move of 200 points has
         happened in the bars given.
  swing  THE SWING PAIR. The latest swing high and the latest swing low (a bar above / below the SWING_N = 50 bars before it AND after it:
         levels.pivots) that no later bar traded beyond, among the swings of the last SWING_BACK = 1380 bars (5 sessions). None without both.
  leg    THE LEG RULE. Swings of LEG_N = 180 bars each side (15 hours); consecutive swings of one kind keep the more extreme; the legs between
         neighbouring swings that ENDED in the last LEG_WITHIN = 2760 bars (10 sessions), at least LEG_MIN = 200 points, and not BROKEN
         (a leg is broken when, since it ended, price traded through its origin). A leg whose end price was passed since is EXTENDED to
         the new extreme. The pick is the biggest size x speed (size squared over the bars the leg took). None when no leg qualifies.

A swing is known only n bars after it, so nothing here reads a bar that has not closed. The first-guess study ran on global arrays with
`>=` ties; here a tie is no swing (levels.pivots, the owner's strict definition).
"""
from __future__ import annotations

import numpy as np

import levels as LV

MOVE_PTS = 200.0
SWING_N, SWING_BACK = 50, 5 * 276
LEG_N, LEG_WITHIN, LEG_BACK, LEG_MIN = 180, 10 * 276, 6000, 200.0


def move(h, l, thr: float = MOVE_PTS):
    """(low, high, d) of the move in progress, or None (module docstring)."""
    h, l = np.asarray(h, np.float64).tolist(), np.asarray(l, np.float64).tolist()
    if not h:
        return None
    mode, hi, lo, pv, ex = 0, h[0], l[0], 0.0, 0.0
    for i in range(1, len(h)):
        if mode == 0:
            hi, lo = max(hi, h[i]), min(lo, l[i])
            if h[i] - lo >= thr:
                mode, pv, ex = 1, lo, h[i]
            elif hi - l[i] >= thr:
                mode, pv, ex = -1, hi, l[i]
        elif mode == 1:
            if h[i] > ex:
                ex = h[i]
            elif ex - l[i] >= thr:
                mode, pv, ex = -1, ex, l[i]
        else:
            if l[i] < ex:
                ex = l[i]
            elif h[i] - ex >= thr:
                mode, pv, ex = 1, ex, h[i]
    return None if mode == 0 else (min(pv, ex), max(pv, ex), mode)


def swing_pair(h, l, n: int = SWING_N, back: int = SWING_BACK):
    """(low, high, d) of the latest untouched swing low and swing high, or None."""
    h, l = np.asarray(h, np.float64), np.asarray(l, np.float64)
    g = len(h) - 1
    ih, il = LV.pivots(h, l, n)
    hh = [int(i) for i in ih if i >= g - back and h[i + 1:].max(initial=-np.inf) <= h[i]]
    ll = [int(i) for i in il if i >= g - back and l[i + 1:].min(initial=np.inf) >= l[i]]
    if not hh or not ll:
        return None
    a, b = hh[-1], ll[-1]
    return float(l[b]), float(h[a]), 1 if b < a else -1


def leg(h, l, n: int = LEG_N, within: int = LEG_WITHIN, back: int = LEG_BACK, min_size: float = LEG_MIN):
    """(low, high, d) of the leg rule's pick, or None."""
    h, l = np.asarray(h, np.float64), np.asarray(l, np.float64)
    g = len(h) - 1
    ih, il = LV.pivots(h, l, n)
    sw = sorted([(int(i), 1) for i in ih if i >= g - back] + [(int(i), -1) for i in il if i >= g - back])
    col: list = []
    for i, t in sw:
        if col and col[-1][1] == t:
            j = col[-1][0]
            if (t == 1 and h[i] > h[j]) or (t == -1 and l[i] < l[j]):
                col[-1] = (i, t)
        else:
            col.append((i, t))
    best = None
    for (i0, t0), (i1, t1) in zip(col, col[1:]):
        if i1 < g - within:
            continue
        o = l[i0] if t0 == -1 else h[i0]
        e = h[i1] if t1 == 1 else l[i1]
        if abs(e - o) < min_size:
            continue
        up = t1 == 1
        after_h, after_l = h[i1 + 1:].max(initial=-np.inf), l[i1 + 1:].min(initial=np.inf)
        if (up and after_l < o) or (not up and after_h > o):
            continue                                                              # broken
        if up and after_h > e:
            e = after_h
        if not up and after_l < e:
            e = after_l
        size = abs(e - o)
        score = size * size / max(1, i1 - i0)
        if best is None or score > best[0]:
            best = (score, float(min(o, e)), float(max(o, e)), 1 if up else -1)
    return None if best is None else best[1:]


KINDS = {"move": move, "swing": swing_pair, "leg": leg}
WORDS = {"move": "the move in progress (from the last turning point where price had reversed 200 points, to the high or low reached since)",
         "swing": "the latest swing high and swing low that nothing has traded beyond (50 bars each side)",
         "leg": "the biggest, fastest leg between 180-bar swings (at least 200 points, not broken)"}

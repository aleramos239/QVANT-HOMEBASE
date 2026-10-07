"""levels -- LIQUIDITY LEVELS of a day: the highs and lows traders rest orders behind, for the `liq` trigger (families/liq.py) and the
`level` and `swept` filter blocks (families/blocks.py). NQ, ES and GC; read from an instance of l2sim.Template at a decision.

A level = (high, low) of a window that has ENDED. Every level is known before the decision that uses it (a window still running has no
level), so nothing here looks ahead. A level that cannot be had (a roll day, no prints, too little history) is left out.

    pd        the prior trade date's high / low (the Template's pdh / pdl; none on a contract-roll day)
    on        the overnight range: 00:00 to the session's start (london: 00:00-03:00; the NY sessions: 00:00-09:30; pre: 00:00-08:25)
    asia      today's Asia range 00:00-03:00 ET            (known from 03:00)
    lon0205   today's early London range 02:00-05:00 ET    (known from 05:00)
    ldn       today's London range 03:00-08:25 ET          (known from 08:25)
    asia2000  the EVENING BEFORE: 20:00-24:00 ET of the previous calendar day, from the tape's prints before 00:00 (never traded: a level
              only; at least EV_MIN prints, else none)
    d5        the high / low of the 5 trade dates before today (the daily bars; none when a contract roll lies inside them)
    sw        the SWING high / low (owner's definition, 2026-10-06): a 5-minute bar whose high is above the 50 bars before it AND the 50 bars
              after it (strict; a low mirrors it). Known only once the 50th bar after it has closed. The level is the most recent swing
              high and the most recent swing low that no bar has traded beyond since, over the last 5 sessions of ONE contract (bars from
              18:00 ET the evening before to 16:00). Read ONCE per session, at the session's first decision, and then fixed: a swing that
              confirms later in the session is not used that day. A side with no such swing is +inf (high) / -inf (low): nothing can reach it;
              with neither side the level is left out.
    eq        EQUAL highs / lows (owner, 2026-10-06; NQ only): two CONSECUTIVE swings (the `sw` swings: 50 five-minute bars each side) whose
              prices are within EQ_TOL = 10 points, and the SECOND does NOT sweep the FIRST: a second high above the first high (a second
              low below the first low) makes it a new, single swing, not an equal; neither does any bar between them trade beyond the first
              (an equal price is not beyond). The level is the first swing's price (the pool of stops behind it). Known once the second swing
              is confirmed (50 bars after it). The level = the most recent equal high and the most recent equal low that no bar has traded
              beyond since (same history, same single read at the session's first decision, same +inf / -inf rule as `sw`).

`levels(st, which)` -> {name: (high, low)}; `which` = one name or "all". `nearest(st)` = the distance of the last close to the closest
level price (any name, high or low), or None. `track(st)` keeps, per session instance, whether a level HIGH and whether a level LOW
has been traded beyond since 00:00 (a sweep needs no close back inside here): st._swept = {"hi": bool, "lo": bool}.
"""
from __future__ import annotations

import datetime as dt
import math
import os
from pathlib import Path

import numpy as np

import l2sim as S

NAMES = ("pd", "on", "asia", "lon0205", "ldn", "asia2000", "d5", "sw", "eq")
WINDOWS = {"asia": (0, 10800), "lon0205": (7200, 18000), "ldn": (10800, 30300)}          # seconds after 00:00 ET, [a, b)
EV_START, EV_END, EV_MIN = "20:00", "00:00", 30                                         # the evening window, and the fewest prints it needs
D5 = 5
SW_TF, SW_N, SW_SESS = 5, 50, 5                                                         # swing bars (minutes), bars each side, sessions looked back
EQ_TOL = {"NQ": 10.0}                                                                   # equal highs / lows: the gap in points, per market (NQ only for now)
SW_OPEN, SW_CLOSE = "18:00", "16:00"                                                     # a session's swing bars: the evening before 18:00 .. 16:00 ET


def _now_s(st) -> int:
    return (st._cx.now_ns - st.t0) // S.NS


def _evening(st):
    """(high, low) of the prints of 20:00-24:00 ET of the calendar day before the trade date, or None. Remembered per trade date."""
    c = st.__dict__.get("_ev")
    if c is not None and c[0] == st.day:
        return c[1]
    s, d = st._cx._s, st._cx.date
    a, b = S.et_ns(d - dt.timedelta(days=1), EV_START), S.et_ns(d, EV_END)
    i, j = np.searchsorted(s.ts, [a, b])
    px = s.px[i:j] if j - i >= EV_MIN else None
    out = None if px is None else (float(px.max()), float(px.min()))
    st.__dict__["_ev"] = (st.day, out)
    return out


# ---- swings ---------------------------------------------------------------------------------------------------------------------
_FM: dict = {}                                    # root -> {iso: (end_ns, h, l)} of the cache file, read once per process
_BARS: dict = {}                                  # (root, iso, tf) -> (end_ns, h, l) of a session (file or tape), per process


def _fm_path(root: str, tf: int = SW_TF) -> Path:
    return S.CACHE / f"bars{tf}m_{root}.npz"


def _fm_file(root: str, tf: int = SW_TF) -> dict:
    key = (root, tf)
    if key not in _FM:
        out, p = {}, _fm_path(root, tf)
        if p.exists():
            z = np.load(p)
            off = z["off"]
            for k, d in enumerate(z["dates"].tolist()):
                a, b = int(off[k]), int(off[k + 1])
                out[d] = (z["end"][a:b], z["h"][a:b], z["l"][a:b])
        _FM[key] = out
    return _FM[key]


def hl_bars(ts, px, hi: int, t0: int, t1: int, tf: int = SW_TF):
    """(end_ns, high, low) of the tf-minute bars of the prints [0, hi) that start in [t0, t1) and have CLOSED by t1 (aligned to multiples
    of tf in epoch time; an empty bucket makes no bar)."""
    step = tf * S.MIN_NS
    i0 = int(np.searchsorted(ts[:hi], t0 - t0 % step, side="left"))
    i1 = int(np.searchsorted(ts[:hi], t1 - t1 % step, side="left"))                 # whole buckets that end by t1
    if i1 <= i0:
        return np.zeros(0, np.int64), np.zeros(0), np.zeros(0)
    k = ts[i0:i1] // step
    st = np.flatnonzero(np.concatenate(([True], k[1:] != k[:-1])))
    seg = np.asarray(px[i0:i1], np.float64)
    return (k[st] + 1) * step, np.maximum.reduceat(seg, st), np.minimum.reduceat(seg, st)


def session_arrays(tape, tf: int = SW_TF):
    """(end_ns, high, low) of a session's tf-minute bars from SW_OPEN of the evening before to SW_CLOSE, from its prints."""
    d = tape.date
    return hl_bars(tape.ts, tape.px, len(tape.ts), S.et_ns(d - dt.timedelta(days=1), SW_OPEN), S.et_ns(d, SW_CLOSE), tf)


def session_bars(root: str, iso: str, tf: int = SW_TF):
    """The session's (end_ns, high, low): the cache file when it holds the date, else its tape (a sealed date that is not in the
    file raises HoldoutSealed: the run stops). None when the date has no tape. Remembered per process."""
    key = (root, iso, tf)
    if key not in _BARS:
        got = _fm_file(root, tf).get(iso)
        if got is None:
            t = S.load_tape(iso, root)
            got = None if t is None or not len(t.ts) else session_arrays(t, tf)
        _BARS[key] = got
    return _BARS[key]


def _one(args):
    iso, root, allow, tf = args
    S.wait_compute_window()
    t = S.load_tape(iso, root, **allow)
    return iso, (None if t is None or not len(t.ts) else session_arrays(t, tf))


def build_bars_cache(root: str, period="build", workers: int = 1, tf: int = SW_TF, **allow) -> dict:
    """Fill cache/bars<tf>m_<root>.npz (tf = SW_TF = 5) with the 5-minute bars (end, high, low) of every session of `period` the file does not hold
    yet -- the same shape and the same switch rules as the minute-volume cache (families.blocks.build_minvol). -> {path, dates, added}."""
    from multiprocessing import get_context
    p = _fm_path(root, tf)
    _FM.pop((root, tf), None)
    have = dict(_fm_file(root, tf))
    a, b = S.period(period)
    todo = [(d.isoformat(), root, allow, tf) for d in S.sessions(a, b, root, **allow)
            if d.isoformat() not in have and (root == "NQ" or S.hb_tape_path(d, root) is not None)]
    if todo:
        workers = max(1, min(int(workers), S.MAX_WORKERS))
        S.wait_compute_window()
        if workers == 1 or not S.pool_usable():
            res = [_one(x) for x in todo]
        else:
            with get_context("spawn").Pool(workers) as pool:
                res = pool.map(_one, todo, chunksize=16)
        have.update({d: v for d, v in res if v is not None})
        dates = sorted(have)
        lens = [len(have[d][0]) for d in dates]
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f".{p.stem}.{os.getpid()}.tmp.npz")
        cat = lambda i, dt_: (np.concatenate([have[d][i] for d in dates]) if dates else np.zeros(0, dt_))
        np.savez_compressed(tmp, dates=np.array(dates), off=np.concatenate(([0], np.cumsum(lens))).astype(np.int64),
                            end=cat(0, np.int64), h=cat(1, np.float64), l=cat(2, np.float64))
        os.replace(tmp, p)
        _FM.pop((root, tf), None)
        for d, *_ in todo:
            _BARS.pop((root, d, tf), None)
    return {"path": str(p), "dates": len(_fm_file(root, tf)), "added": len(todo)}


def pivots(h, l, n: int = SW_N):
    """Indices of the swing highs and swing lows of the bars (pure): strictly above / below the n bars before AND the n bars after."""
    h, l = np.asarray(h, np.float64), np.asarray(l, np.float64)
    if len(h) < 2 * n + 1:
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    from numpy.lib.stride_tricks import sliding_window_view as sw
    wh, wl = sw(h, 2 * n + 1), sw(l, 2 * n + 1)
    hi = (wh[:, n] > wh[:, :n].max(1)) & (wh[:, n] > wh[:, n + 1:].max(1))
    lo = (wl[:, n] < wl[:, :n].min(1)) & (wl[:, n] < wl[:, n + 1:].min(1))
    return np.flatnonzero(hi) + n, np.flatnonzero(lo) + n


def untouched_swings(h, l, n: int = SW_N):
    """(price of the most recent swing high no later bar traded above, price of the most recent swing low none traded below) -- either
    may be None. A swing at bar i is confirmed by bar i + n, so every bar read here has closed by the last bar given (pure)."""
    h, l = np.asarray(h, np.float64), np.asarray(l, np.float64)
    ih, il = pivots(h, l, n)
    out = [None, None]
    if len(ih):
        after = np.concatenate((np.maximum.accumulate(h[::-1])[::-1][1:], [-np.inf]))      # after[i] = max(h[i+1:])
        ok = ih[after[ih] <= h[ih]]
        out[0] = float(h[ok[-1]]) if len(ok) else None
    if len(il):
        after = np.concatenate((np.minimum.accumulate(l[::-1])[::-1][1:], [np.inf]))
        ok = il[after[il] >= l[il]]
        out[1] = float(l[ok[-1]]) if len(ok) else None
    return out[0], out[1]


def equal_pairs(h, l, n: int = SW_N, tol: float = 10.0):
    """The equal highs and equal lows of the bars (pure): {"hi": [(a, b, level)], "lo": [...]} for every pair of CONSECUTIVE swings (indices a < b) whose
    prices differ by at most `tol` points with the second NOT beyond the first (high: h[b] <= h[a]; low: l[b] >= l[a]) and no bar in a+1 .. b beyond the
    first swing's price. level = the first swing's price."""
    h, l = np.asarray(h, np.float64), np.asarray(l, np.float64)
    ih, il = pivots(h, l, n)
    out = {"hi": [], "lo": []}
    for kind, idx, y in (("hi", ih, h), ("lo", il, -l)):                  # a low is a high of the mirrored series
        for a, b in zip(idx[:-1], idx[1:]):
            if 0 <= y[a] - y[b] <= tol and y[a + 1:b + 1].max() <= y[a]:
                out[kind].append((int(a), int(b), float(y[a]) if kind == "hi" else float(-y[a])))
    return out


def live_equal(h, l, n: int = SW_N, tol: float = 10.0):
    """(price of the most recent equal high no bar traded above since its second swing, the same for the lows) -- None for a side with none (pure)."""
    h, l = np.asarray(h, np.float64), np.asarray(l, np.float64)
    p, out = equal_pairs(h, l, n, tol), [None, None]
    for k, (kind, y) in enumerate((("hi", h), ("lo", -l))):
        for a, b, lvl in reversed(p[kind]):
            if (y[b + 1:].max() if b + 1 < len(y) else -np.inf) <= (lvl if kind == "hi" else -lvl):
                out[k] = lvl
                break
    return out[0], out[1]


def _sw_bars(st):
    """The session's one-contract bar history up to this decision: the last SW_SESS prior sessions (cache file / tape; the roll day is
    the first session of its contract) and today's prints before now -> (high, low) arrays, oldest first."""
    s, root = st._cx._s, st._cx.root
    now = st._cx.now_ns
    prior = []
    if st.day not in st.ROLLS:
        for r in reversed(st.dl[-SW_SESS:]):
            got = session_bars(root, r["date"])
            if got is None:
                break
            prior.append(got)
            if r["date"] in st.ROLLS:
                break
    d = st._cx.date
    hi = int(np.searchsorted(s.ts, now, side="left"))
    today = hl_bars(s.ts, s.px, hi, S.et_ns(d - dt.timedelta(days=1), SW_OPEN), now, SW_TF)
    hs = [g[1] for g in reversed(prior)] + [today[1]]
    ls = [g[2] for g in reversed(prior)] + [today[2]]
    return np.concatenate(hs), np.concatenate(ls)


def _hist(st):
    """The swing history (_sw_bars), read ONCE per session at the first call: the swing and equal levels share it and stay fixed."""
    c = st.__dict__.get("_swh")
    if c is None or c[0] != st.day:
        c = st.__dict__["_swh"] = (st.day, _sw_bars(st))
    return c[1]


def _equal(st):
    """(high, low) of the equal-highs / equal-lows level, read once per session, or None (market without a tolerance, or neither side)."""
    tol = EQ_TOL.get(st._cx.root)
    if tol is None:
        return None
    c = st.__dict__.get("_eql")
    if c is not None and c[0] == st.day:
        return c[1]
    a, b = live_equal(*_hist(st), SW_N, tol)
    out = None if a is None and b is None else (math.inf if a is None else a, -math.inf if b is None else b)
    st.__dict__["_eql"] = (st.day, out)
    return out


def _swing(st):
    """(high, low) of the swing level, read once per session at the first call (fixed afterwards), or None."""
    c = st.__dict__.get("_swl")
    if c is not None and c[0] == st.day:
        return c[1]
    h, l = _hist(st)
    a, b = untouched_swings(h, l, SW_N)
    out = None if a is None and b is None else (math.inf if a is None else a, -math.inf if b is None else b)
    st.__dict__["_swl"] = (st.day, out)
    return out


def _d5(st):
    dl = st.dl[-D5:]
    if len(dl) < D5 or any(r["date"] in st.ROLLS for r in dl) or st.day in st.ROLLS:
        return None
    return max(r["h"] for r in dl), min(r["l"] for r in dl)


def levels(st, which: str = "all") -> dict:
    """The levels of `which` known at this decision: {name: (high, low)}."""
    out = {}
    for name in NAMES if which == "all" else (which,):
        if name == "pd":
            v = (st.pdh, st.pdl)
        elif name == "on":
            v = (st.onh, st.onl)
        elif name in WINDOWS:
            a, b = WINDOWS[name]
            v = st.rng(a, b) if _now_s(st) >= b else None
        elif name == "asia2000":
            v = _evening(st)
        elif name == "sw":
            v = _swing(st)
        elif name == "eq":
            v = _equal(st)
        else:
            v = _d5(st)
        if v is not None and v[0] is not None and v[1] is not None:
            out[name] = (float(v[0]), float(v[1]))
    return out


def nearest(st):
    """The distance of the last close to the closest level price, or None (no level, no bar)."""
    lv = levels(st)
    if not lv or not st.nb:
        return None
    c = st.C[-1]
    return min(abs(c - px) for hi, lo in lv.values() for px in (hi, lo))


def track(st) -> None:
    """At a bar close: has the bar traded beyond a level high / low? (st._swept, reset by the caller at each session start.)"""
    if not st.nb:
        return
    h, l = st.H[-1], st.L[-1]
    for hi, lo in levels(st).values():
        if h > hi:
            st._swept["hi"] = True
        if l < lo:
            st._swept["lo"] = True

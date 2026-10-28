"""win_dir -- A CLOCK ENTRY WITH ONE TRADE A DAY, THE SIDE FROM A DIRECTION RULE (owner, 2026-10-25: "D and E": a trade every day).

tod_drift's clock entry (session start + off_min, 1 per session, held to the card's w_flat or the stop) with the side taken from `src`,
written BEFORE any result. d = the number the rule reads; d > 0 -> long, d < 0 -> short, d == 0 or unreadable -> no trade. mode fade flips it.
  ret    d = close of the 1-minute bar before a_end minus the open of a_start (a window of the trade date, read at the entry; 00:00 on)
  open   d = last price - the open of a_start
  vwap   d = last price - the VWAP anchored at 00:00 / 03:00 / 09:30 (the session's own cash anchor, `vwr`)
  gap    d = last price - the prior daily close
  loc    d = the prior daily close - the middle of its range
  retgap d = ret; a flat window (a doji) reads the open of a_start vs the prior daily close instead (owner, 2026-10-27: first-candle follow)
  retd   d = the prior daily close - the daily close n_d days before it
  smad   d = the prior daily close - the mean of the last n_d daily closes
Every window rule needs a_end at or before the entry (else no trade).
Daily bars are `ctx.daily` (the days BEFORE the trade date), so no look-ahead; a window that ends after the entry is not read (no trade).
dir long / short keeps one side only (both = the default). tod_drift is untouched (test_port2 keeps its methods AST-identical).
Registration as eve_gap_follow.py: join_blocks()."""
from __future__ import annotations

import datetime as dt

import numpy as np

import flowtab
import l2sim as S
from l2sim import SESS, Template, _hms

from .orb_dir_rv import ref_mean
from .port2 import TodDrift

SRCS = ("ret", "retgap", "open", "vwap", "gap", "loc", "retd", "smad", "pret", "rexp", "gapagree", "vol5", "delta", "vslope")
WINDOWED = ("ret", "retgap", "gapagree", "vol5", "delta", "vslope")          # same-day windows (pret reads the prior day: its a_end is that day's)
_BS: dict = {}


def _bars5(root: str) -> dict:
    """root -> {session iso: (bar start ns, open, close)} of barstore's 5-minute bars (the 3:1 in-sample months only), once per process."""
    if root not in _BS:
        import barstore
        df = barstore.load(root, "5m", fresh=False)
        _BS[root] = {str(k)[:10]: (g.t.to_numpy(), g.o.to_numpy(), g.c.to_numpy()) for k, g in df.groupby("session")}
    return _BS[root]


def window_ret(root: str, iso: str, day: dt.date, a: str, b: str):
    """Close of the last 5-minute bar that starts before `b` minus the open of the first one at or after `a` (clock 'HH:MM' on calendar `day`)
    in session `iso`; None: no such session, no bar, or a hole of 5 minutes or more at the start."""
    got = _bars5(root).get(iso)
    if got is None:
        return None
    t, o, c = got
    lo, hi = S.et_ns(day, a), S.et_ns(day, b)
    i, j = int(np.searchsorted(t, lo)), int(np.searchsorted(t, hi))
    return float(c[j - 1] - o[i]) if j > i and t[i] - lo < 300 * S.NS else None


class WinDir(TodDrift):
    SCREEN_TFS = ("1", "3", "5", "15", "30")          # 3 added 2026-10-28 (owner: first-candle follow on a 3-minute candle)
    DEFAULTS = {**TodDrift.DEFAULTS, "dir": "both", "exit_bars": 400, "mode": "follow", "src": "ret", "a_start": "09:30",
                "a_end": "10:00", "n_d": 5}
    SCHEMA = {**TodDrift.SCHEMA, "dir": ("choice", ("both", "long", "short")), "exit_bars": ("int", 1, 1000),
              "mode": ("choice", ("follow", "fade")), "src": ("choice", SRCS), "a_start": ("str",), "a_end": ("str",),
              "n_d": ("int", 1, 300)}

    def _wm(self):
        """The a_start-to-a_end return of today's 1-minute bars (the close of the minute before a_end minus the open of a_start)."""
        p = self.p
        o, c = self.mo(S._sec(p["a_start"])), self.mc(S._sec(p["a_end"]) - 60, S._sec(p["a_end"]))
        return None if o is None or c is None else c - o

    def _vw(self, a, b):
        xs = [m for m in self.M if a <= m[0] and m[0] + 60 <= b]
        v = sum(m[5] for m in xs)
        return sum(m[4] * m[5] for m in xs) / v if v else None

    def _d(self, lp, root):
        _sec = S._sec
        p, dl, n, src = self.p, self.dl, int(self.p["n_d"]), self.p["src"]
        if src in WINDOWED and S.clock_sec(p["a_end"]) > self.fam_times_sec():
            return None                                                    # a window that ends after the entry is not read
        if src == "ret":
            if p["a_start"] >= "18:00":                                    # the evening before the trade date
                return window_ret(root, self.day, dt.date.fromisoformat(self.day) - dt.timedelta(days=1), p["a_start"], p["a_end"])
            return self._wm()
        if src == "retgap":
            w, o = self._wm(), self.mo(_sec(p["a_start"]))
            return w if w or w is None or o is None or not dl else o - dl[-1]["c"]
        if src == "open":
            o = self.mo(_sec(p["a_start"]))
            return None if o is None else lp - o
        if src == "vwap":
            w = self.vwr()
            return None if w is None else lp - w[0]
        if src == "vslope":
            a, b = _sec(p["a_start"]), _sec(p["a_end"])
            v0, v1 = self._vw(a, b), self._vw(a, self.fam_times_sec())
            return None if v0 is None or v1 is None else v1 - v0
        if src == "delta":
            w = flowtab.window(root, self.day, _sec(p["a_start"]), _sec(p["a_end"]))
            return None if w is None else w[1]
        if not dl:
            return None
        if src == "pret":
            iso = str(dl[-1]["date"])
            return window_ret(root, iso, dt.date.fromisoformat(iso), p["a_start"], p["a_end"])
        if src == "vol5":
            a, b = _sec(p["a_start"]), _sec(p["a_end"])
            xs = [m for m in self.M if a <= m[0] and m[0] + 60 <= b]
            ref = ref_mean(root, [str(r["date"]) for r in dl], a, b) if xs and xs[0][0] == a else None
            if ref is None:
                return None
            mv = xs[-1][4] - xs[0][1]
            return mv if sum(m[5] for m in xs) >= ref else -mv
        if src == "gapagree":
            o, w = self.mo(_sec(p["a_start"])), self._wm()
            s1 = None if o is None else o - dl[-1]["c"]
            return w if s1 and w and (s1 > 0) == (w > 0) else None
        if src == "gap":
            return lp - dl[-1]["c"]
        if src == "loc":
            return dl[-1]["c"] - (dl[-1]["h"] + dl[-1]["l"]) / 2
        if src == "retd":
            return dl[-1]["c"] - dl[-1 - n]["c"] if len(dl) > n else None
        if src == "rexp":
            if len(dl) < n + 1:
                return None
            rs = [r["h"] - r["l"] for r in dl[-n:]]
            mv = dl[-1]["c"] - dl[-2]["c"]
            return mv if rs[-1] > sum(rs) / n else -mv                      # a wide prior day: follow its move, a narrow one: fade it
        cl = [d["c"] for d in dl[-n:]]                                     # smad
        return dl[-1]["c"] - sum(cl) / n if len(cl) == n else None

    def fam_time(self, ctx, sec):
        s, lp = self.sid, ctx.last_price
        if s is None or lp is None or sec != self.fam_times_sec() or not self.can_enter(ctx):
            return
        d = self._d(lp, ctx.root)
        if not d:
            return
        side = "long" if (d > 0) == (self.p["mode"] == "follow") else "short"
        if self.p["dir"] in ("both", side):
            self._mkt(ctx, side, ref=lp)

    def fam_times_sec(self):
        s = self.sid
        return None if s is None else SESS[s][0] + int(self.p["off_min"]) * 60


class WinDirOwn(WinDir):
    """win_dir whose own stop is the a_start-a_end window's other extreme (a long: its low, a short: its high): the hm40 table gains the
    own-stop cells. A subclass, so the win_dir cards keep their exit table (blocks.has_structure reads each class apart)."""

    def _mkt(self, ctx, side, *a, **kw):
        r = self.rng(S._sec(self.p["a_start"]), S._sec(self.p["a_end"]))
        return super()._mkt(ctx, side, *a, struct=None if r is None else (r[1] if side == "long" else r[0]), **kw)


class WinDirRetr(WinDirOwn):
    """win_dir_own that waits for a retracement: instead of the market order at the window's close, a LIMIT `retr` of the window's range back
    from its far end (a long: high - retr x range, a short: low + retr x range; 0.5 = the middle), the stop = the window's other extreme, alive
    `wait_min` minutes. A price already past the level, or no fill in time = no trade. retr 0 = win_dir_own's market order."""
    DEFAULTS = {**WinDirOwn.DEFAULTS, "retr": 0.5, "wait_min": 60}
    SCHEMA = {**WinDirOwn.SCHEMA, "retr": ("float", 0.0, 1.0), "wait_min": ("int", 5, 240)}

    def _mkt(self, ctx, side, *a, **kw):
        if not float(self.p["retr"]):
            return super()._mkt(ctx, side, *a, **kw)
        r = self.rng(S._sec(self.p["a_start"]), S._sec(self.p["a_end"]))
        if r is None:
            return None
        hi, lo = r
        px = hi - float(self.p["retr"]) * (hi - lo) if side == "long" else lo + float(self.p["retr"]) * (hi - lo)
        px = round(px / ctx.tick) * ctx.tick
        return self._lim(ctx, side, px, struct=lo if side == "long" else hi, ttl=-(-int(self.p["wait_min"]) // self.tf))


class PdBracket(Template):
    """pd_bracket: at session start + off_min, OCO stop entries one tick beyond the prior day's high and low (the daily bar's: evening to 17:00);
    the stop = the other level; a side whose level price has already passed is not armed; one trade a session; the exit cell's stop and target."""
    DEFAULTS = {"off_min": 0, "max_tr": 1}
    SCHEMA = {"off_min": ("int", 0, 240)}
    SCREEN_TFS = ("1", "5", "15", "30")
    FEATURES = ()

    def fam_times(self):
        om = int(self.p["off_min"]) * 60
        return [_hms(SESS[s][0] + om) for s in self.sessions()]

    def fam_time(self, ctx, sec):
        s, lp = self.sid, ctx.last_price
        if s is None or lp is None or not self.dl or sec != SESS[s][0] + int(self.p["off_min"]) * 60 or not self.can_enter(ctx):
            return
        hi, lo, t = self.dl[-1]["h"], self.dl[-1]["l"], ctx.tick
        legs = ([("long", hi + t, lo, None)] if lp < hi else []) + ([("short", lo - t, hi, None)] if lp > lo else [])
        if legs:
            self._arm(ctx, legs)


FAMILIES = {
    "win_dir": (WinDir, {}, False,
                "win_dir: market at session start + off_min, the side from a direction rule (a window's return, last price vs an open / "
                "the VWAP / the prior close, the prior day's close location, an n-day return or mean); fade flips it; 1 per session",
                {"rationale": "A rule that trades every day: the side comes from what the market already did (a window, the gap, the "
                              "daily trend) and the exits do the rest. Who loses: the traders on the other side of that first move "
                              "(follow) or the ones chasing it (fade).",
                 "complexity": 3,
                 "variants": [{"off_min": 0}, {"off_min": 15}, {"off_min": 30}],
                 "roots": ("NQ",)}),
    "win_dir_own": (WinDirOwn, {}, False,
                    "win_dir_own: win_dir with the window's other extreme as the structure (own stop = its distance x 0.5 / 1 / 1.5 / 2)",
                    {"rationale": "As win_dir; the stop sits where the window's move is proven wrong (past the other end of the first candle).",
                     "complexity": 3,
                     "variants": [{"off_min": 0}, {"off_min": 15}, {"off_min": 30}],
                     "roots": ("NQ",)}),
    "win_dir_retr": (WinDirRetr, {}, False,
                     "win_dir_retr: win_dir_own that enters on a retracement: a limit `retr` of the window's range back from its far end, the stop "
                     "the window's other extreme (own stop = its distance x 0.5 / 1 / 1.5 / 2), alive wait_min minutes; 1 per session",
                     {"rationale": "The first candle's direction is the day's lean; a pullback into the candle buys it cheaper and puts the stop "
                                   "closer to where the read is proven wrong. Who loses: sellers into the opening drop and chasers who missed the dip.",
                      "complexity": 3,
                      "variants": [{"retr": 0.382}, {"retr": 0.5}, {"retr": 0.618}],
                      "roots": ("NQ",)}),
    "pd_bracket": (PdBracket, {}, True,
                   "pd_bracket: at session start + off_min, stop entries one tick beyond the prior day's high and low (OCO), the stop the other "
                   "level, a level price has already passed is not armed; 1 per session",
                   {"rationale": "The prior day's high and low are the levels every desk watches; the first one broken sets the day's side.",
                    "complexity": 2,
                    "variants": [{"off_min": 0}, {"off_min": 15}, {"off_min": 30}],
                    "roots": ("NQ",)}),
}


def join_blocks() -> None:
    """Put the family into families/blocks.py's BASES and WRAPPED (as eve_gap_follow.py)."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()

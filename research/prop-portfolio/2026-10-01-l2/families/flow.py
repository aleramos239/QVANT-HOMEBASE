"""Flow families of the Stage A screen (SPEC "Stage A screen" F1-F4): delta_follow, absorption, cvd_div, sweep_follow.

The exact, pre-registered definitions are in FAMILIES.md ("Flow families F1 ... F4", written before anything was run);
this module implements them and nothing else. In short, at an ON-TIME tf-bar close T (the bar's last minute printed, the
newest usable feature row is the minute that just ended and its `book_ok` is True):

  F1 delta_follow  |D| of the bar >= the q-th percentile (90) of |D| over the 60 tf clock buckets before it, and the bar
                   closes in the delta's direction -> market entry WITH the delta.
  F2 absorption    the same |D| trigger and |close - open| <= move_atr (0.25) x ATR -> market entry AGAINST the delta.
  F3 cvd_div       the bar's close is beyond the session's prior high (low) while the session cum-delta (rebuilt from
                   f_delta since the session start) is below (above) its running session extreme -> fade.
  F4 sweep_follow  sweep volume of the bar (buy + sell) > 0 and >= the q-th percentile (95) of the 60 buckets before it
                   -> market entry on the side with the larger sweep volume.

D = sum of f_delta over the one-minute rows of the tf clock bucket (a minute without a print adds 0; a bucket without a
finite row is missing; fewer than 30 valid trailing buckets = no signal). Stops / targets / sessions / max_tr / the
last-5-minutes rule are the Template's (atr 1.5, tgt_r 2.0); on a CME half day the rule is applied to the 13:15 ET end
as well (FAMILIES.md addendum). Market entries only: one direction (`both_sides` False).
Features are read through ctx.feat / ctx.feat_window only; no state of its own (every decision is recomputed).
"""
from __future__ import annotations

import numpy as np

import l2sim as S

NS = S.NS
LOOK = 60                                  # "the trailing 60 tf bars": the 60 clock buckets before the signal bar
MIN_VALID = 30                             # fewer valid trailing buckets -> no signal


def bucket_sums(t_utc, cols, now_s: int, tf: int, look: int = LOOK):
    """Per-minute columns summed over tf CLOCK buckets counted back from the decision second `now_s` (a multiple of
    tf minutes): bucket 0 = [now - tf min, now) = the signal bar, bucket j = the j-th bar before it, up to `look`.
    A row counts only when every column of `cols` is finite on it. -> (sums float64 [len(cols), look + 1],
    valid bool [look + 1]); a bucket without a counted row is not valid (its sum is 0.0 and must not be used)."""
    t = np.asarray(t_utc, np.int64)
    vs = [np.asarray(v, np.float64) for v in cols]
    b = (int(now_s) - 1 - t) // (int(tf) * 60)
    ok = (b >= 0) & (b <= look)
    for v in vs:
        ok &= np.isfinite(v)
    bk = b[ok]
    sums = np.vstack([np.bincount(bk, weights=v[ok], minlength=look + 1) for v in vs])
    return sums, np.bincount(bk, minlength=look + 1) > 0


def top_quantile(cur: float, hist, q: float, min_valid: int = MIN_VALID) -> bool:
    """cur > 0 and cur >= the q-th percentile (numpy, linear interpolation) of `hist`; False with fewer than
    `min_valid` values."""
    h = np.asarray(hist, np.float64)
    return bool(len(h) >= min_valid and cur > 0 and cur >= np.percentile(h, q))


class _Flow(S.Template):
    """Shared plumbing of the flow families: the on-time / fresh / book_ok guard and the tf-bucket aggregation."""
    SCREEN_TFS = ("1", "5")

    def fam_day(self, ctx):
        # The last-5-minutes rule on a CME half day: the engine ends the day at 13:15 ET (the Template only knows the
        # sessions' own ends), so no signal from 13:10 ET on. On a full day this is 16:05 ET, after every session.
        h, m = S.effective_session_window(ctx.date, self.session_window)[1].split(":")[:2]
        self._day_cut = self.t0 + (int(h) * 3600 + int(m) * 60 - 300) * NS

    def _on_time(self, ctx):
        """The decision second T when this close is a signal instant, else None. Needs: T on the tf clock grid, the
        closed tf bar's last one-minute bar ended exactly at T (not a late close), the newest usable row stamped
        T - 60 s (fresh) and that row's book_ok True; and T more than 5 minutes before the end of the simulated day."""
        now = ctx.now_ns
        if now % self.step or not self.M or self.t0 + (self.M[-1][0] + 60) * NS != now or now >= self._day_cut:
            return None
        T = now // NS
        t = ctx.feat("t_utc")
        if t is None or t + 60 != T:
            return None
        ok = ctx.feat("book_ok")
        if ok is None or ok != ok or not ok:
            return None
        return int(T)

    def _bars(self, ctx, T: int, names):
        n = (LOOK + 1) * self.tf
        return bucket_sums(ctx.feat_window("t_utc", n), [ctx.feat_window(c, n) for c in names], T, self.tf)

    def _delta(self, ctx, T: int):
        """The signal bar's delta D when |D| > 0 and |D| >= the q-th percentile of the trailing buckets, else None."""
        sums, valid = self._bars(ctx, T, ("f_delta",))
        d = sums[0]
        if not valid[0] or not top_quantile(abs(d[0]), np.abs(d[1:][valid[1:]]), self.p["q"]):
            return None
        return float(d[0])


class DeltaFollow(_Flow):
    """F1 delta_follow: top-decile |delta| tf bar that closes in the delta's direction -> follow (FAMILIES.md)."""
    DEFAULTS = {"q": 90.0}
    SCHEMA = {"q": ("float", 50.0, 99.9)}
    FEATURES = ("f_delta", "t_utc", "book_ok")

    def fam_signal(self, ctx):
        T = self._on_time(ctx)
        if T is None:
            return
        d = self._delta(ctx, T)
        if d is None:
            return
        move = self.C[-1] - self.O[-1]
        if d > 0 and move > 0:
            self._mkt(ctx, "long")
        elif d < 0 and move < 0:
            self._mkt(ctx, "short")


class Absorption(_Flow):
    """F2 absorption: top-decile |delta| tf bar that moved <= move_atr x ATR -> fade the aggressor (FAMILIES.md)."""
    DEFAULTS = {"q": 90.0, "move_atr": 0.25}
    SCHEMA = {"q": ("float", 50.0, 99.9), "move_atr": ("float", 0.05, 2.0)}
    FEATURES = ("f_delta", "t_utc", "book_ok")

    def fam_signal(self, ctx):
        T = self._on_time(ctx)
        if T is None:
            return
        d = self._delta(ctx, T)
        if d is None or abs(self.C[-1] - self.O[-1]) > self.p["move_atr"] * self.atr:
            return
        self._mkt(ctx, "short" if d > 0 else "long")


class CvdDiv(_Flow):
    """F3 cvd_div: tf close beyond the session's prior high / low while the session cum-delta is short of its own
    session extreme -> fade (FAMILIES.md)."""
    DEFAULTS = {"warm_min": 15}
    SCHEMA = {"warm_min": ("int", 0, 120)}
    FEATURES = ("f_delta", "t_utc", "book_ok")

    def fam_signal(self, ctx):
        T = self._on_time(ctx)
        sn = self.sn
        if T is None or sn < 2:
            return
        s0 = self.t0 // NS + S.SESS[self.sid][0]
        m = (T - s0) // 60
        if m < 1 or m < self.p["warm_min"]:
            return
        t = ctx.feat_window("t_utc", m)
        d = ctx.feat_window("f_delta", m)
        if len(t) != m or not np.array_equal(t, s0 + 60 * np.arange(m, dtype=np.int64)) or not np.isfinite(d[-1]):
            return
        cum = np.cumsum(np.where(np.isfinite(d), d, 0.0), dtype=np.float64)
        cvd, x_hi, x_lo = float(cum[-1]), max(0.0, float(cum.max())), min(0.0, float(cum.min()))
        c = self.C[-1]
        if c > max(self.H[-sn:-1]):
            if cvd < x_hi:
                self._mkt(ctx, "short")
        elif c < min(self.L[-sn:-1]):
            if cvd > x_lo:
                self._mkt(ctx, "long")


class SweepFollow(_Flow):
    """F4 sweep_follow: tf bar whose sweep volume is in the top 5% of the trailing 60 bars (and > 0) -> follow the
    side with the larger sweep volume (FAMILIES.md)."""
    DEFAULTS = {"q": 95.0}
    SCHEMA = {"q": ("float", 50.0, 99.9)}
    FEATURES = ("f_sweep_buy_vol", "f_sweep_sell_vol", "t_utc", "book_ok")

    def fam_signal(self, ctx):
        T = self._on_time(ctx)
        if T is None:
            return
        (vb, vs), valid = self._bars(ctx, T, ("f_sweep_buy_vol", "f_sweep_sell_vol"))
        v = vb + vs
        if not valid[0] or not top_quantile(v[0], v[1:][valid[1:]], self.p["q"]):
            return
        if vb[0] > vs[0]:
            self._mkt(ctx, "long")
        elif vs[0] > vb[0]:
            self._mkt(ctx, "short")


FAMILIES = {
    "delta_follow": (DeltaFollow, {}, False,
                     "F1: tf-bar |delta| >= P90 of the trailing 60 tf bars and the bar closes with the delta -> follow"),
    "absorption": (Absorption, {}, False,
                   "F2: same |delta| trigger and |close - open| <= 0.25 ATR -> fade the delta "
                   "(adjacent to the refuted 2026-09-24 absorption program)"),
    "cvd_div": (CvdDiv, {}, False,
                "F3: tf close beyond the prior session high / low while session cum-delta is short of its session extreme -> fade"),
    "sweep_follow": (SweepFollow, {}, False,
                     "F4: tf-bar sweep volume >= P95 of the trailing 60 tf bars (and > 0) -> follow the larger sweep side"),
}

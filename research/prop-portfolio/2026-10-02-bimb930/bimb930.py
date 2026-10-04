"""bimb930: at 09:30:00 ET take ONE market trade on the side the top-10 book points to (SPEC.md in this folder).

    mode "imb"   sign of imb10 of the row stamped 09:29 (usable at 09:30:00): > 0 long, < 0 short
    mode "long"  always long   } same days: only those where the 09:29 book row is valid (control)
    mode "short" always short  }

Stop 25 pts, target 2 x stop = 50 pts, one trade per day, held to the stop / target or flat at 15:58 ET. Features are read through ctx.feat_window only, and only when
the row is exactly the minute that just ended.
"""
from __future__ import annotations

import sys

import numpy as np

L = "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2"
if L not in sys.path:
    sys.path.insert(0, L)
import l2sim as S  # noqa: E402

R = "/Users/ramoscapital/ramos-quant-homebase"
if R not in sys.path:
    sys.path.insert(0, R)
from homebase import gate as G  # noqa: E402  (house ADX gate: Wilder ADX(14) on completed daily bars)

ADX_MIN, RSI_N = 20.0, 14


def rsi14(closes):
    """Wilder RSI(14) of a list of closes (the house RMA helper, seeded at the first value)."""
    up = [None] + [max(closes[i] - closes[i - 1], 0.0) for i in range(1, len(closes))]
    dn = [None] + [max(closes[i - 1] - closes[i], 0.0) for i in range(1, len(closes))]
    u, d = G._rma(up, RSI_N), G._rma(dn, RSI_N)
    if u[-1] is None or d[-1] is None:
        return None
    return 100.0 if d[-1] == 0 else 100.0 - 100.0 / (1.0 + u[-1] / d[-1])

OPEN_S = 9 * 3600 + 1800
DAY_END_S = 57480                       # 15:58 ET: the simulator's own day end (pm session end), before the 16:00 close
S.SESS["day"] = (OPEN_S, DAY_END_S)     # one session 09:30 -> 15:58: the trade runs to its stop / target or the day end


class Imb930(S.Template):
    """09:30 market entry on the side of the heavier top-10 book (mode imb), or the always-long / always-short control."""
    DEFAULTS = {"mode": "imb", "sess": "day", "stop_mode": "pts", "stop_val": 25.0, "tgt_r": 2.0, "max_tr": 1, "filt": "off"}
    SCHEMA = {"mode": ("choice", ("imb", "imb_inv", "long", "short")), "sess": ("choice", ("day",)), "filt": ("choice", ("off", "adx", "rsi"))}
    SCREEN_TFS = ("5",)
    FEATURES = ("imb10", "t_utc")

    def _filt_ok(self, side, f):
        if f == "adx":                                   # trend forming and above: house daily ADX > 20 and rising
            a = G.adx_series(self.dl) if self.dl else []
            return len(a) >= 2 and a[-1] is not None and a[-2] is not None and a[-1] > ADX_MIN and a[-1] > a[-2]
        if f == "rsi":                                   # good momentum: 5-minute RSI(14) agrees with the side
            if len(self.C) < 30:
                return False
            r = rsi14(list(self.C))
            return r is not None and ((r > 50.0) if side == "long" else (r < 50.0))
        return True

    def _mkt(self, ctx, side, **kw):
        f = self.p["filt"]
        if f != "off" and not self._filt_ok(side, f):
            return None
        return super()._mkt(ctx, side, **kw)

    def fam_filter(self, ids):
        return [s for s in ids if s == "day"]

    def fam_times(self):
        return [S._hms(OPEN_S) for s in self.sessions() if s == "day"]

    def _sig(self, ctx):
        """imb10 of the row stamped exactly one minute before now, or None (missing / masked / not that minute)."""
        t = ctx.feat_window("t_utc", 1)
        if len(t) != 1 or int(t[0]) != ctx.now_ns // S.NS - 60:
            return None
        v = float(ctx.feat_window("imb10", 1)[0])
        return v if np.isfinite(v) else None

    def fam_time(self, ctx, sec):
        if sec != OPEN_S or self.sid != "day" or not self.can_enter(ctx):
            return
        lp, v = ctx.last_price, self._sig(ctx)
        if lp is None or v is None:                    # no print / no valid book: no trade (same day set in every mode)
            return
        m = self.p["mode"]
        if m not in ("long", "short"):
            sgn = (v > 0) - (v < 0)
            sgn = -sgn if m.endswith("_inv") else sgn
            side = "long" if sgn > 0 else "short" if sgn < 0 else None
        else:
            side = m
        if side is not None:
            self._mkt(ctx, side, ref=lp)


FLOW_MIN, FLOW_VALID = 15, 8                       # the pilot's pre-registered flow window (families/opendir.py)


class Flow930(Imb930):
    """flow930 (SPEC_flow.md): side = sign of the summed f_delta of the 15 minutes before 09:30 (>= 8 finite minutes)."""
    DEFAULTS = {"mode": "flow"}
    SCHEMA = {"mode": ("choice", ("flow", "flow_inv", "long", "short"))}
    FEATURES = ("f_delta", "t_utc")

    def _sig(self, ctx):
        t = ctx.feat_window("t_utc", FLOW_MIN)
        now_s = ctx.now_ns // S.NS
        if len(t) != FLOW_MIN or not np.array_equal(t, now_s - 60 * np.arange(FLOW_MIN, 0, -1)):
            return None
        w = np.asarray(ctx.feat_window("f_delta", FLOW_MIN), np.float64)
        ok = np.isfinite(w)
        return float(w[ok].sum()) if int(ok.sum()) >= FLOW_VALID else None


class WImb930(Imb930):
    """wimb930 (SPEC_wide.md): side from the sign of the whole-near-ladder imbalance `wimb` at the 09:29 snapshot."""
    DEFAULTS = {"mode": "wimb"}
    SCHEMA = {"mode": ("choice", ("wimb", "wimb_inv", "long", "short"))}
    FEATURES = ("wimb", "t_utc")

    def _sig(self, ctx):
        t = ctx.feat_window("t_utc", 1)
        if len(t) != 1 or int(t[0]) != ctx.now_ns // S.NS - 60:
            return None
        v = float(ctx.feat_window("wimb", 1)[0])
        return v if np.isfinite(v) else None


def _row_ok(ctx, n):
    t = ctx.feat_window("t_utc", n)
    now_s = ctx.now_ns // S.NS
    return len(t) == n and np.array_equal(t, now_s - 60 * np.arange(n, 0, -1))


class Combo930(Imb930):
    """combo930 (SPEC_heatmap2.md): volume sign v (15-min pre-open f_delta) x orders sign o (wide-ladder wimb) at 09:30."""
    MODES = ("agree", "agree_inv", "dis", "dis_inv", "long_agree", "short_agree", "long_dis", "short_dis", "long_all", "short_all")
    DEFAULTS = {"mode": "agree"}
    SCHEMA = {"mode": ("choice", MODES)}
    FEATURES = ("f_delta", "wimb", "t_utc")

    def _v(self, ctx):
        if not _row_ok(ctx, FLOW_MIN):
            return None
        w = np.asarray(ctx.feat_window("f_delta", FLOW_MIN), np.float64)
        ok = np.isfinite(w)
        return float(w[ok].sum()) if int(ok.sum()) >= FLOW_VALID else None

    def _o(self, ctx):
        if not _row_ok(ctx, 1):
            return None
        x = float(ctx.feat_window("wimb", 1)[0])
        return x if np.isfinite(x) else None

    def fam_time(self, ctx, sec):
        if sec != OPEN_S or self.sid != "day" or not self.can_enter(ctx):
            return
        lp, v, o = ctx.last_price, self._v(ctx), self._o(ctx)
        if lp is None or v is None or o is None:
            return
        a, b = (v > 0) - (v < 0), (o > 0) - (o < 0)
        if a == 0 or b == 0:
            return
        agree, m = a == b, self.p["mode"]
        vol_side = "long" if a > 0 else "short"
        flip = {"long": "short", "short": "long"}
        side = None
        if m == "agree" and agree: side = vol_side
        elif m == "agree_inv" and agree: side = flip[vol_side]
        elif m == "dis" and not agree: side = vol_side
        elif m == "dis_inv" and not agree: side = flip[vol_side]
        elif m.endswith("_agree") and agree: side = m.split("_")[0]
        elif m.endswith("_dis") and not agree: side = m.split("_")[0]
        elif m.endswith("_all"): side = m.split("_")[0]
        if side is not None:
            self._mkt(ctx, side, ref=lp)

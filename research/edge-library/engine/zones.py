"""zones -- FOUR FILTER BLOCKS the owner asked for on 2026-10-06 (premium / discount, OTE, the higher-timeframe trend, SMT), written from the
definitions below BEFORE any result. They are FIRST GUESSES: the owner goes through each of them on charts and may change any number. Every
block reads closed bars only, at the signal bar's close, and a block that cannot be computed yet (too little history, no range, a close
exactly on the line) has NO SIGNAL and blocks the entry on both sides. NQ, ES and GC, except SMT (NQ and ES only).

  pdz     with | against   The DEALING RANGE = the high and low of the completed 1-minute bars since 00:00 ET of the trade date (at the New York
          open this is the overnight range; it grows during the day). It must be at least PDZ_MIN_ATR = 1 ATR of the idea's bars tall. The
          midpoint splits it: above = PREMIUM, below = DISCOUNT; a close exactly on the midpoint has no signal. with: a long needs the close
          in DISCOUNT, a short in PREMIUM (buy cheap, sell dear); against: the mirror (a breakout bought high).
  ote     in | out         The OPTIMAL TRADE ENTRY zone: the 62 % .. 79 % retracement of the day's range leg (same range as pdz, at least 1 ATR).
          The leg points UP when its low came before its high (the LAST bar holding each extreme), DOWN when its high came first. A long
          needs an UP leg and a close inside [high - 0.79 R, high - 0.62 R] (R = high - low); a short needs a DOWN leg and a close inside
          [low + 0.62 R, low + 0.79 R]. in: the close is inside the zone; out: a leg of the trade's direction exists and the close is
          NOT inside. No leg in the trade's direction (or both extremes in one bar): no signal.
  htf15, htf60  with | against   The TREND on bigger bars: 15-minute / 60-minute bars made of the 1-minute bars since 00:00 ET (aligned to the
          clock; a bar counts once its last minute has closed; its close = the close of its last 1-minute bar). The trend is the close of the
          last closed big bar against the EMA of the big closes (seeded with the first close, as the Template's EMAs): EMA(20) of the 15-minute
          closes, EMA(8) of the 60-minute closes, at least that many closes needed. with: a long needs the close above the EMA, a short below
          it; against: the mirror.
  smt     agree | disagree  (NQ and ES) The two indices DIVERGE at a new extreme. On the 5-minute bars both markets have (from 18:00 ET the
          evening before, only bars both have), the last SMT_W = 6 bars are the WINDOW and the SMT_L = 36 bars before them the REFERENCE.
          A market makes a new high when the window's highest high is above the reference's highest high (a new low: below its lowest low).
          BEARISH SMT = exactly one of the two markets made a new high; BULLISH SMT = exactly one made a new low. Both at once, or neither,
          has no signal. agree: a long needs a bullish SMT, a short a bearish one (a reversal against the stretched index); disagree: the mirror.
          Needs the 5-minute bar cache of both markets (levels.build_bars_cache); the partner's bars are read up to the decision only.
"""
from __future__ import annotations

import datetime as dt

import numpy as np

import l2sim as S
import levels as LV

PDZ_MIN_ATR = 1.0
OTE_LO, OTE_HI = 0.62, 0.79
HTF = {"htf15": (15, 20), "htf60": (60, 8)}           # block -> (minutes per big bar, EMA length)
SMT_L, SMT_W = 36, 6
PARTNER = {"NQ": "ES", "ES": "NQ"}


def prep_roots(root: str, family, filt) -> list:
    """The markets whose 5-minute bar cache (levels.build_bars_cache) a unit reads: its own for the liquidity levels (the swing level),
    both for SMT."""
    out = []
    if family == "liq" or (filt and filt[0] in ("level", "swept", "smt")):
        out.append(root)
    if filt and filt[0] == "smt" and root in PARTNER:
        out.append(PARTNER[root])
    return out


def _now_s(st) -> int:
    return (st._cx.now_ns - st.t0) // S.NS


def day_leg(st):
    """(high, low, up) of the completed 1-minute bars since 00:00 ET, or None (no bar, or the bars' range is under PDZ_MIN_ATR ATRs, or no ATR yet);
    up = the low came before the high (the last bar holding each extreme); None for `up` when one bar holds both."""
    b = _now_s(st)
    xs = [m for m in st.M if 0 <= m[0] and m[0] + 60 <= b]
    if not xs or st.atr is None:
        return None
    hi, lo = max(m[2] for m in xs), min(m[3] for m in xs)
    if hi - lo < PDZ_MIN_ATR * st.atr:
        return None
    th = max(m[0] for m in xs if m[2] == hi)
    tl = max(m[0] for m in xs if m[3] == lo)
    return hi, lo, (None if th == tl else tl < th)


def pdz(st):
    """'premium' | 'discount' | None: the close against the midpoint of the day's range."""
    r = day_leg(st)
    if r is None:
        return None
    mid = (r[0] + r[1]) / 2.0
    c = st.C[-1]
    return None if c == mid else "premium" if c > mid else "discount"


def ote(st, sd: int):
    """True / False: the close is inside / outside the OTE zone of a leg in the trade's direction; None: no such leg."""
    r = day_leg(st)
    if r is None or r[2] is None or r[2] != (sd > 0):
        return None
    hi, lo, up = r
    R = hi - lo
    a, b = (hi - OTE_HI * R, hi - OTE_LO * R) if up else (lo + OTE_LO * R, lo + OTE_HI * R)
    return a <= st.C[-1] <= b


def htf(st, block: str):
    """+1 | -1 | None: the last closed big bar's close above / below the EMA of the big closes."""
    mins, n = HTF[block]
    step, b = mins * 60, _now_s(st)
    last = {}
    for m in st.M:
        k = m[0] // step
        if m[0] >= 0 and (k + 1) * step <= b:
            last[k] = m[4]                                      # the close of the bar's last 1-minute bar
    closes = [last[k] for k in sorted(last)]
    if len(closes) < n:
        return None
    e, a = None, 2.0 / (n + 1)
    for c in closes:
        e = c if e is None else e + a * (c - e)
    return None if closes[-1] == e else 1 if closes[-1] > e else -1


def _bars(st, root: str):
    """(end_ns, high, low) of a market's 5-minute bars of the trade date from 18:00 ET the evening before, closed by this decision, or None."""
    now = st._cx.now_ns
    if root == st._cx.root:
        s, d = st._cx._s, st._cx.date
        hi = int(np.searchsorted(s.ts, now, side="left"))
        return LV.hl_bars(s.ts, s.px, hi, S.et_ns(d - dt.timedelta(days=1), LV.SW_OPEN), now, LV.SW_TF)
    got = LV.session_bars(root, st.day)
    if got is None:
        return None
    k = int(np.searchsorted(got[0], now, side="right"))        # bars whose end <= now
    return got[0][:k], got[1][:k], got[2][:k]


def smt(st):
    """'bull' | 'bear' | None (module docstring)."""
    other = PARTNER.get(st._cx.root)
    if other is None:
        return None
    a, b = _bars(st, st._cx.root), _bars(st, other)
    if a is None or b is None:
        return None
    common = np.intersect1d(a[0], b[0])
    if len(common) < SMT_L + SMT_W:
        return None
    ia, ib = np.isin(a[0], common), np.isin(b[0], common)
    ha, la, hb, lb = a[1][ia], a[2][ia], b[1][ib], b[2][ib]
    w, r = slice(-SMT_W, None), slice(-SMT_W - SMT_L, -SMT_W)
    bear = bool(ha[w].max() > ha[r].max()) != bool(hb[w].max() > hb[r].max())
    bull = bool(la[w].min() < la[r].min()) != bool(lb[w].min() < lb[r].min())
    return None if bear == bull else "bear" if bear else "bull"

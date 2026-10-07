"""indicators -- the pure math of BATCH 4 of the filter blocks (bbw, atrp, er, macd, rsidiv, mfi, deltadiv, candle), written from the
definitions below BEFORE any result. They are FIRST GUESSES the owner reviews one by one. Every function takes lists of CLOSED tf bars (oldest
first, since the indicator restart) and no engine state; None = no signal (too little history, a flat line, nothing exactly on a threshold).
The thresholds of each block's sides (tight / wide, high / low, trend / chop ...) are families/blocks.py's.

  bbw      Bollinger BANDWIDTH = (upper - lower) / middle of the 20-bar, 2-sigma band of the closes (population sigma). Its RANK = where the
           bandwidth of the last bar stands among the 120 bandwidths before it (140 closes needed): the share of them below it, ties half.
  atrp     Wilder ATR(14) (the Template's own: the first bar's true range = high - low, the first ATR = the mean of 14 true ranges, then
           (ATR x 13 + TR) / 14). Its RANK among the 100 ATR values before it (114 bars needed), counted as the bandwidth's.
  er       Kaufman's EFFICIENCY RATIO of 14 bars = |close[-1] - close[-15]| / the sum of |close changes| over those 14 steps (15 closes needed;
           no movement at all: no signal).
  macd     EMA(12) - EMA(26) of the closes (every EMA seeded with the first close), the signal = EMA(9) of that line (seeded with its first
           value), histogram = line - signal; 35 closes needed. +1 = histogram above 0 and not below the previous bar's; -1 = the mirror.
  rsidiv   RSI(14) DIVERGENCE over the last 20 bars: the last bar against the LOWEST low of the bars [-20:-3] (the last bar holding it).
           Bullish = the last low is below that low while the last bar's RSI is ABOVE the RSI of that earlier bar; bearish = the mirror on
           the highs. Both at once, or either RSI not computable (fewer than 15 closes up to it): no signal.
  mfi      MONEY FLOW INDEX of 14 bars: typical price (high + low + close) / 3 x volume; a bar's flow is positive when its typical price is
           above the bar before, negative when below (equal: none); MFI = 100 x positive / (positive + negative). 15 bars needed.
  deltadiv price against DELTA over the last 20 tf bars: +1 = the close fell over them (close[-1] < close[-21]) while the net delta of the
           window was positive (buyers absorbed it); -1 = the close rose while the net delta was negative. Else no signal.
  candle   the signal bar's SHAPE for a side (sd = +1 a long, -1 a short), body = |close - open|:
           displace  body >= 1.5 ATR and the close in the top 25 % of the bar's range (a long) / the bottom 25 % (a short)
           engulf    the bar's body covers the previous bar's body, the two bars have opposite colours, and the new bar points the trade's way
           reject    a rejection wick: body > 0 and the lower wick (a long) / upper wick (a short) is at least 2 x the body
"""
from __future__ import annotations

import numpy as np

BB_N, BB_REF = 20, 120                              # bbw: band length, the bandwidths it is ranked among
ATR_N, ATR_REF = 14, 100                            # atrp
ER_N = 14
MACD_FAST, MACD_SLOW, MACD_SIG = 12, 26, 9
DIV_N, DIV_SKIP = 20, 3                             # rsidiv / deltadiv: the window; rsidiv compares with the bars [-DIV_N:-DIV_SKIP]
MFI_N = 14
DISP_ATR, DISP_EDGE, WICK_X = 1.5, 0.25, 2.0        # candle


def _midrank(x: float, ref) -> float:
    """The share of `ref` below x, with ties counted half (a flat series sits in the middle, never at an end)."""
    r = np.asarray(ref, float)
    return (float((r < x).sum()) + 0.5 * float((r == x).sum())) / len(r)


def bbw_rank(C):
    """Rank (0 .. 1) of the last bar's Bollinger bandwidth among the 120 before it, or None (fewer than 140 closes)."""
    if len(C) < BB_N + BB_REF:
        return None
    w = np.lib.stride_tricks.sliding_window_view(np.asarray(C[-(BB_N + BB_REF):], float), BB_N)      # BB_REF + 1 bands
    mid, sd = w.mean(axis=1), w.std(axis=1)
    bw = ((mid + 2.0 * sd) - (mid - 2.0 * sd)) / mid
    return _midrank(bw[-1], bw[:-1])


def atr_series(H, L, C, n: int = ATR_N) -> list:
    """Wilder ATR(n) after every bar from the n-th on (module docstring), [] with fewer than n bars."""
    if len(C) < n:
        return []
    tr = [H[0] - L[0]] + [max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1])) for i in range(1, len(C))]
    a = sum(tr[:n]) / n
    out = [a]
    for x in tr[n:]:
        a = (a * (n - 1) + x) / n
        out.append(a)
    return out


def atr_rank(H, L, C):
    """Rank (0 .. 1) of the last ATR(14) among the 100 before it, or None (fewer than 114 bars)."""
    a = atr_series(H, L, C)
    return None if len(a) < ATR_REF + 1 else _midrank(a[-1], a[-ATR_REF - 1:-1])


def efficiency(C):
    """Kaufman's efficiency ratio of the last 14 steps (0 .. 1), or None (fewer than 15 closes, or no movement)."""
    if len(C) < ER_N + 1:
        return None
    w = C[-ER_N - 1:]
    path = sum(abs(b - a) for a, b in zip(w, w[1:]))
    return None if path == 0 else abs(w[-1] - w[0]) / path


def macd_dir(C):
    """+1 | -1 | None: the MACD histogram above 0 and not below the previous bar's (+1) / below 0 and not above it (-1); None with
    fewer than 35 closes, a histogram of exactly 0, or one that points the other way from its sign (a fading one)."""
    if len(C) < MACD_SLOW + MACD_SIG:
        return None
    kf, ks, kg = (2.0 / (n + 1) for n in (MACD_FAST, MACD_SLOW, MACD_SIG))
    f = s = sig = None
    h = hp = None
    for c in C:
        f = c if f is None else f + kf * (c - f)
        s = c if s is None else s + ks * (c - s)
        m = f - s
        sig = m if sig is None else sig + kg * (m - sig)
        hp, h = h, m - sig
    return 1 if h > 0 and h >= hp else -1 if h < 0 and h <= hp else None


def rsidiv(H, L, rsi_at):
    """+1 (bullish) | -1 (bearish) | None. rsi_at(i) = the RSI at the close of bar i (or None): blocks.rsi of the closes up to it."""
    N = len(L)
    if N < DIV_N:
        return None
    a, b = N - DIV_N, N - DIV_SKIP
    lo, hi = min(L[a:b]), max(H[a:b])
    jl, jh = max(i for i in range(a, b) if L[i] == lo), max(i for i in range(a, b) if H[i] == hi)

    def rsi_vs(j, up):                              # the last bar's RSI above (up) / below the RSI at bar j
        r0, r1 = rsi_at(N - 1), rsi_at(j)
        return r0 is not None and r1 is not None and (r0 > r1 if up else r0 < r1)
    bull = L[-1] < lo and rsi_vs(jl, True)
    bear = H[-1] > hi and rsi_vs(jh, False)
    return None if bull == bear else 1 if bull else -1


def mfi_last(H, L, C, V):
    """Money Flow Index (0 .. 100) of the last 14 bars, or None (fewer than 15 bars, or no flow at all)."""
    if len(C) < MFI_N + 1:
        return None
    tp = [(h + l + c) / 3.0 for h, l, c in zip(H[-MFI_N - 1:], L[-MFI_N - 1:], C[-MFI_N - 1:])]
    pos = neg = 0.0
    for i in range(1, MFI_N + 1):
        flow = tp[i] * V[-MFI_N - 1 + i]
        if tp[i] > tp[i - 1]:
            pos += flow
        elif tp[i] < tp[i - 1]:
            neg += flow
    return None if pos + neg == 0 else 100.0 * pos / (pos + neg)


def delta_div(move: float, net: float):
    """+1 | -1 | None: price fell while the net delta is positive (+1) / price rose while it is negative (-1)."""
    return 1 if move < 0 and net > 0 else -1 if move > 0 and net < 0 else None


def candle(kind: str, sd: int, O, H, L, C, atr) -> bool:
    """The signal bar's shape (module docstring) for a side: True / False. displace needs an ATR."""
    o, h, l, c = O[-1], H[-1], L[-1], C[-1]
    body, rng = abs(c - o), h - l
    if kind == "displace":
        if atr is None or rng <= 0 or body < DISP_ATR * atr:
            return False
        return c - l >= (1.0 - DISP_EDGE) * rng if sd > 0 else c - l <= DISP_EDGE * rng
    if kind == "engulf":
        if len(C) < 2:
            return False
        po, pc = O[-2], C[-2]
        return ((c - o) * sd > 0 and (pc - po) * sd < 0
                and min(o, c) <= min(po, pc) and max(o, c) >= max(po, pc))
    wick = (min(o, c) - l) if sd > 0 else (h - max(o, c))                         # reject
    return body > 0 and wick >= WICK_X * body

"""STAGE 2a day labels (EDGE_SPEC "STAGE 2a"): every label of trade date D is built from daily bars dated BEFORE D only.
  T1 trend       Wilder ADX(14) of the daily bars through the prior trading day: >= 25 / < 25
  T2 volatility  the prior day's range (h - l) above / not above the median of the 20 daily ranges ending with the prior day
  T3 news        D carries an 08:30 ET CPI or NFP release or an FOMC decision: only / never
  T4 direction   long-only / short-only (a per-trade split, not a day label)
Daily bars: l2sim.load_daily(root) = the engine's own whole-day bars {date, h, l, c, contract}; they start on 2021-09-22, so the
first 28 sessions have no ADX and the first 20 no range median: those days are in NEITHER side of T1 / T2.
Roll days (the bar's contract differs from the bar before): true range = h - l and both directional moves = 0 (a price gap
between two contracts is not a market move). Fixed before any deepen number was read.
News dates: research/prop-portfolio/2026-09-29/news_days.csv (built from ForexFactory red USD events; 12 CPI + 12 NFP + 8 FOMC
per year 2021-2024, checked date by date). The engine itself (score.py / families/timed.py) holds no date list."""
import bisect
import csv
import datetime as dt
import sys
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(W))
sys.path.insert(0, str(W / "engine"))

NEWS_CSV = W.parents[0] / "prop-portfolio" / "2026-09-29" / "news_days.csv"
ADX_N, ADX_CUT, VOL_N = 14, 25.0, 20
SEAL = "2025-01-01"                               # nothing dated on / after this is ever read here
SIDES = ("adx_hi", "adx_lo", "vol_hi", "vol_lo", "news_only", "news_never", "long", "short")
TOOL = {"adx_hi": "T1", "adx_lo": "T1", "vol_hi": "T2", "vol_lo": "T2", "news_only": "T3", "news_never": "T3", "long": "T4", "short": "T4"}
PLAIN = {"adx_hi": "only days whose prior-day daily ADX(14) is 25 or more (a trending market)",
         "adx_lo": "only days whose prior-day daily ADX(14) is below 25 (no clear trend)",
         "vol_hi": "only days after a daily range above its own 20-day median (an active market)",
         "vol_lo": "only days after a daily range at or below its own 20-day median (a quiet market)",
         "news_only": "only days with an 08:30 ET CPI or jobs (NFP) release or a Fed (FOMC) decision",
         "news_never": "never on days with a CPI or jobs (NFP) release or a Fed (FOMC) decision",
         "long": "long trades only", "short": "short trades only"}


def adx_series(rows: list, n: int = ADX_N) -> np.ndarray:
    """Wilder ADX(n) per daily bar (NaN until bar index 2n - 1). rows: [{date, h, l, c, contract}] ascending."""
    N = len(rows)
    out = np.full(N, np.nan)
    if N < 2 * n:
        return out
    tr, pdm, mdm = np.zeros(N), np.zeros(N), np.zeros(N)
    for i in range(1, N):
        a, b = rows[i], rows[i - 1]
        if a.get("contract") != b.get("contract"):
            tr[i] = a["h"] - a["l"]
            continue
        tr[i] = max(a["h"] - a["l"], abs(a["h"] - b["c"]), abs(a["l"] - b["c"]))
        up, dn = a["h"] - b["h"], b["l"] - a["l"]
        pdm[i] = up if (up > dn and up > 0) else 0.0
        mdm[i] = dn if (dn > up and dn > 0) else 0.0
    st, sp, sm = tr[1:n + 1].sum(), pdm[1:n + 1].sum(), mdm[1:n + 1].sum()
    dx = np.full(N, np.nan)

    def _dx(st, sp, sm):
        if st <= 0:
            return 0.0
        pdi, mdi = 100.0 * sp / st, 100.0 * sm / st
        return 100.0 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) > 0 else 0.0

    dx[n] = _dx(st, sp, sm)
    for i in range(n + 1, N):
        st, sp, sm = st - st / n + tr[i], sp - sp / n + pdm[i], sm - sm / n + mdm[i]
        dx[i] = _dx(st, sp, sm)
    out[2 * n - 1] = dx[n:2 * n].mean()
    for i in range(2 * n, N):
        out[i] = (out[i - 1] * (n - 1) + dx[i]) / n
    return out


def day_labels(rows: list, dates: list) -> dict:
    """{ISO date D: {'adx': ADX through the last bar dated < D or None, 'vol_hi': bool or None}} for every D in `dates`."""
    rows = [r for r in rows if r["date"] < SEAL]
    ds = [r["date"] for r in rows]
    adx = adx_series(rows)
    rng = np.array([r["h"] - r["l"] for r in rows], float)
    out = {}
    for d in dates:
        if d >= SEAL:
            raise ValueError("EXAM is sealed")
        j = bisect.bisect_left(ds, d)                  # bars dated < d: rows[:j]
        a = None if j < 1 or np.isnan(adx[j - 1]) else float(adx[j - 1])
        v = None if j < VOL_N else bool(rng[j - 1] > float(np.median(rng[j - VOL_N:j])))
        out[d] = {"adx": a, "vol_hi": v}
    return out


def news_days() -> dict:
    """{ISO date: tags} for CPI / NFP / FOMC days before the seal."""
    out = {}
    with NEWS_CSV.open() as fh:
        for r in csv.DictReader(fh):
            if r["date"] < SEAL and any(t in r["tags"] for t in ("CPI", "NFP", "FOMC")):
                out[r["date"]] = r["tags"]
    return out


_MEMO: dict = {}


def root_labels(root: str) -> dict:
    """{ordinal: (adx or nan, vol flag 1 / 0 / -1 = none, news 1 / 0)} for every BUILD + PICK session of a root."""
    if root not in _MEMO:
        import l2sim
        import library as LB
        dates = LB.calendar("build", root) + LB.calendar("pick", root)
        lab = day_labels(l2sim.load_daily(root), dates)
        nd = news_days()
        _MEMO[root] = {dt.date.fromisoformat(d).toordinal(): (np.nan if lab[d]["adx"] is None else lab[d]["adx"],
                                                             -1 if lab[d]["vol_hi"] is None else int(lab[d]["vol_hi"]),
                                                             int(d in nd)) for d in dates}
    return _MEMO[root]


def side_mask(side: str, root: str, date: np.ndarray, trade_side: np.ndarray) -> np.ndarray:
    """Boolean mask of the trades (by trade date ordinal / trade side) that belong to a side."""
    if side == "long":
        return np.asarray(trade_side) == 1
    if side == "short":
        return np.asarray(trade_side) == -1
    lab = root_labels(root)
    date = np.asarray(date)
    uniq, inv = np.unique(date, return_inverse=True)
    ok = np.array([day_in_side(side, lab.get(int(o))) for o in uniq], bool) if len(uniq) else np.zeros(0, bool)
    return ok[inv] if len(uniq) else np.zeros(0, bool)


def day_in_side(side: str, lab) -> bool:
    if lab is None:
        return False
    adx, vol, news = lab
    if side == "adx_hi":
        return bool(adx == adx and adx >= ADX_CUT)
    if side == "adx_lo":
        return bool(adx == adx and adx < ADX_CUT)
    if side == "vol_hi":
        return vol == 1
    if side == "vol_lo":
        return vol == 0
    if side == "news_only":
        return news == 1
    if side == "news_never":
        return news == 0
    raise ValueError(side)


def day_labelled(side: str, lab) -> bool:
    """Is the day in the universe of the side's tool (either side of it)?"""
    if lab is None:
        return False
    adx, vol, _ = lab
    t = TOOL[side]
    return bool(adx == adx) if t == "T1" else (vol != -1 if t == "T2" else True)

"""NQ Level-2 data layer (pilot 2026-10-01-l2). Contract: SPEC.md; evidence and column docs: DATA.md.

One row per Globex minute M of the OFB grid, indexed by ``usable_at`` = the earliest decision time at which the row
may legally be used.

TIMESTAMP LAW (measured, see DATA.md / ts_law.py): a depth.bin / hist.bin row keyed ``yyyymmddHHMM00`` (US-Eastern
wall clock) is the book 59.02 .. 59.98 s INTO minute M (constant within a calendar month, median 59.3 s), i.e. the
END of the minute, never its start. Our own flow row ``t_utc == M`` aggregates the prints of [M, M+60 s). Both are
therefore usable for decisions at >= M + 60 s: ``usable_at(M) = M + 60 s``. A decision at a minute boundary T reads
the row whose ``usable_at == T`` (stamp T-60 s) and executes on the first print AFTER T. The margin is as thin as
0.02 s in some months: ``phase_check(months)`` must pass on every month of new data before it is used.

Tiers
* deployable book features: ONLY the top 10 near-book levels per side (far-cluster slots dropped with the
  ``ladder_split`` rule), all relative to the best price (sizes, level index, tick distance).
  ``features_from_book(bids, asks)`` is the single implementation: the cache builder calls the same vectorised
  core, so a desk DOM snapshot ([[px, sz], ...] best first) reproduces the columns exactly.
* price anchors (``bid_px`` / ``ask_px``): the snapshot's best bid / ask, the ONLY absolute OFB prices stored
  (== ofb_tick ``prev_best_bid/ask``). They are tape coordinates only while the OFB book is on the tape's contract,
  which is what ``book_ok`` certifies: ``load_features`` NaNs them wherever it is False. A wall's price is
  ``bid_px - bid_wall_dist * 0.25`` / ``ask_px + ask_wall_dist * 0.25`` (B4 / B5). Anchors are not features:
  never z-score, threshold or C2-shuffle them.
* deployable flow features (``f_*``): our own tick flow, ``~/futures_derived/flow_1m/NQ.parquet``.
* research tier (``rt_*``): OFB vendor hist slots. Never promotable (not reproducible live).

Holdout: any row of a Globex session dated >= 2025-01-01 is SEALED, i.e. every OFB key >= 2024-12-31 17:00 ET
(``SEAL_KEY``; the New Year's Eve evening is the 2025-01-01 session). Every reader here raises ``HoldoutSealed``
unless ``allow_holdout=True`` (only the orchestrator's "holdout" stage may pass it), including row access on
``BinFile``.

CLI:  python l2data.py build      (in-sample cache, single process, ~15 s)
      python l2data.py report     (out/data_sanity.json + out/data_sanity.md)
      python l2data.py phase      (per-month snapshot-phase check, RTH + overnight, in-sample -> out/phase_check.json
                                   and cache/phase_guard.json = the months l2sim runs with the 1 s execution guard)
"""
from __future__ import annotations

import collections
import datetime as dt
import glob
import json
import os
import struct
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

L = Path(__file__).resolve().parent
CACHE = L / "cache"
OUT = L / "out"
FLOW_1M = Path.home() / "futures_derived" / "flow_1m" / "NQ.parquet"
TICKS_DIR = Path.home() / "futures_ticks" / "NQ"
OFB_TICK_DIR = Path.home() / "futures_derived" / "ofb_tick" / "NQ"      # execution tape, one parquet per session
DESK_DEPTH_DIR = Path.home() / "futures_depth" / "NQ"

IS_START = dt.date(2021, 9, 22)          # first tape session (Globex open 2021-09-21 18:00 ET)
IS_END = dt.date(2024, 12, 31)
HOLDOUT_START = dt.date(2025, 1, 1)      # Globex sessions dated >= this are sealed
SEAL_KEY = 20241231170000                # first sealed OFB key: 2024-12-31 17:00 ET (the 2025-01-01 session's rows)
ET = "America/New_York"

TICK = 0.25
NLEV = 10                                 # near-book levels per side (the desk DOM depth)
MAX_GAP = 10.0                            # points; ladder_split's near/far valley
SNAPSHOT_OFFSET_S = 59.3                  # measured: an OFB row stamped M is the book ~59.3 s into M (pooled median;
                                          # constant within a calendar month, 59.02 .. 59.98 s across months)
LIVE_SNAPSHOT_S = 59.0                    # live sampling instant: never fresher than the earliest research month
USABLE_LAG_S = 60                         # usable_at(M) = M + 60 s
EXEC_GUARD_MS = 1000                      # optional execution guard for thin-margin months (DATA.md section 1)
PHASE_GRID_S = np.round(np.arange(58.0, 61.0001, 0.02), 2)     # phase_check: candidate snapshot instants in M
PHASE_MAX_S = 59.99                       # phase_check fails a month whose snapshot instant is >= this
PHASE_MIN_MINUTES = 150                   # phase_check: fewer two-sided RTH minutes = session not measurable
PHASE_ON_MIN_MINUTES = 2000               # ... fewer pooled overnight minutes in a month = overnight not measurable
PHASE_GUARD = CACHE / "phase_guard.json"  # persisted verdicts per month; l2sim enforces EXEC_GUARD_MS on failed months
MED_WIN, MED_MIN = 15, 8                  # trailing-median window (minutes) / minimum valid snapshots
TOD_DAYS, TOD_MIN = 20, 10                # same-time-of-day median: prior sessions / minimum valid
MISMATCH_PTS = 2.0                        # session median |OFB mid - tape close| above this = other contract
MISMATCH_WIN, MISMATCH_MINP = 61, 5       # per-minute check: centred window (minutes) / minimum valid minutes
MISMATCH_MIN_PTS = 1.0                    # ... median distance of the tape close to [best bid, best ask] above this
MISMATCH_PAD = 2                          # ... and this many minutes either side of a flagged minute

SESSIONS = (("asia", 0, 180), ("london", 180, 505), ("nyam", 570, 660), ("mid", 660, 810), ("pm", 810, 958))

STATIC_COLS = ["bid_top1", "bid_top3", "bid_top10", "ask_top1", "ask_top3", "ask_top10", "imb3", "imb10",
               "spread_ticks", "bid_wall_sz", "bid_wall_dist", "ask_wall_sz", "ask_wall_dist",
               "bid_med_sz", "ask_med_sz", "bid_n", "ask_n", "depth10"]
DYN_COLS = ["bid10_chg", "ask10_chg", "bid10_rel15", "ask10_rel15"]
TOD_COLS = ["depth10_rel20d"]
BOOK_COLS = STATIC_COLS + DYN_COLS + TOD_COLS
PX_COLS = ["bid_px", "ask_px"]            # best bid / ask of the snapshot: price ANCHORS (tape coordinates), not features
FLOW_SRC = ["o", "h", "l", "c", "volume", "buy_vol", "sell_vol", "delta", "cum_delta", "sweep_buy_vol",
            "sweep_sell_vol", "sweeps_buy", "sweeps_sell", "big_print", "big_print_side", "big_order",
            "big_order_side", "big_order_levels"]
FLOW_COLS = ["f_" + c for c in FLOW_SRC]
RT_SLOTS = {5: "size_imb", 7: "qdepl_bid", 8: "qdepl_ask", 9: "pulled_bid", 10: "pulled_ask", 11: "ice_bid",
            12: "ice_ask", 14: "cum_delta"}
RT_COLS = ["rt_" + v for v in RT_SLOTS.values()]
FLAG_COLS = ["book_valid", "in_tape", "roll_block", "ofb_mismatch", "book_ok"]
TAG_COLS = ["t_utc", "date", "globex_date", "et_min", "session", "contract"]


class HoldoutSealed(PermissionError):
    """Raised when a call would read rows dated >= 2025-01-01 without allow_holdout=True."""


class PhaseCheckFailed(RuntimeError):
    """phase_check: a month's snapshot instant is >= PHASE_MAX_S into the stamped minute (or cannot be measured),
    so ``usable_at = M + 60 s`` is not proven safe there. ``.result`` holds the full per-month table."""

    def __init__(self, msg, result=None):
        super().__init__(msg)
        self.result = result


# ------------------------------------------------------------------------------------------------ time helpers
def usable_at(minute_utc):
    """Earliest legal decision time (UTC epoch seconds) for a row stamped minute ``minute_utc`` (its start)."""
    return minute_utc + USABLE_LAG_S


def _utc_offset_h(y: int, m: int, d: int) -> int:
    """US Eastern -> UTC offset by DATE (4 EDT / 5 EST), as onyx/lab/ofb.py: flips happen while futures are shut."""
    mar = dt.date(y, 3, 8 + (6 - dt.date(y, 3, 8).weekday()) % 7)
    nov = dt.date(y, 11, 1 + (6 - dt.date(y, 11, 1).weekday()) % 7)
    return 4 if mar <= dt.date(y, m, d) < nov else 5


def key_to_utc(keys) -> np.ndarray:
    """OFB ``yyyymmddHHMMSS`` ET wall-clock keys -> UTC epoch seconds (vectorised)."""
    k = np.asarray(keys, dtype=np.int64)
    ymd, hms = k // 10**6, k % 10**6
    u, inv = np.unique(ymd, return_inverse=True)
    day0 = np.empty(len(u), dtype=np.int64)
    for i, v in enumerate(u):
        y, m, d = int(v) // 10000, int(v) // 100 % 100, int(v) % 100
        day0[i] = (dt.date(y, m, d) - dt.date(1970, 1, 1)).days * 86400 + _utc_offset_h(y, m, d) * 3600
    return day0[inv] + (hms // 10000) * 3600 + (hms // 100 % 100) * 60 + hms % 100


def _date_key(d: dt.date) -> int:
    return (d.year * 10000 + d.month * 100 + d.day) * 10**6


def _as_date(x) -> dt.date:
    if isinstance(x, dt.datetime):
        return x.date()
    if isinstance(x, dt.date):
        return x
    return dt.date.fromisoformat(str(x)[:10])


def _guard(end: dt.date, allow_holdout: bool) -> None:
    if end >= HOLDOUT_START and not allow_holdout:
        raise HoldoutSealed(f"rows through {end} requested: everything dated >= {HOLDOUT_START} is sealed "
                            "(pass allow_holdout=True only when the orchestrator says 'holdout')")


def session_of(et_min) -> np.ndarray:
    """R/SPEC session key for a decision at ET minute-of-day ``et_min`` ('' outside every session)."""
    m = np.asarray(et_min)
    out = np.full(m.shape, "", dtype=object)
    for name, a, b in SESSIONS:
        out[(m >= a) & (m < b)] = name
    return out


# ------------------------------------------------------------------------------------------------ OFB binaries
def ofb_dir() -> Path:
    env = os.environ.get("L2_OFB_DIR")
    if env:
        return Path(env)
    hits = sorted(glob.glob(str(Path.home() / "Downloads" / "Desktop - Alejandro*" / "OFB_data" / "globex")))
    if not hits:
        raise FileNotFoundError("OFB globex directory not found (set L2_OFB_DIR)")
    return Path(hits[0])


def ofb_files(kind: str, allow_holdout: bool = False) -> list:
    """depth|hist file chain. The 2026-06-01 -> 2026-07-08 file is entirely holdout: listed only when allowed."""
    names = [f"nqv0_20170601_20260601.{kind}.bin"] + ([f"nqv0_20260601_20260708.{kind}.bin"] if allow_holdout else [])
    return [ofb_dir() / n for n in names]


class BinFile:
    """Memory-mapped OFB binary (16-byte header ``magic, ver, count, n`` + fixed rows ``int64 key + payload``).
    depth: payload = n (px, sz) float32 bids then n asks; hist: n float64 slots. Nothing is read at open except
    the header; ``bounds`` bisects on single keys, so rows outside the asked range are never touched.

    Rows are reached only through ``row(i)`` / ``rows(i, j)``, which raise ``HoldoutSealed`` for any row keyed
    >= SEAL_KEY unless the file was opened with ``allow_holdout=True``; the raw memmap ``mm`` is refused the same
    way. ``key(i)`` / ``bounds`` read stamps only (never a payload) and are not guarded."""

    MAGIC = {"depth": b"2DBF", "hist": b"2HBF"}

    def __init__(self, path, kind: str, allow_holdout: bool = False):
        self.path, self.kind, self.allow_holdout = str(path), kind, allow_holdout is True
        self._open_n = None
        with open(self.path, "rb") as f:
            magic, self.ver, self.count, self.n = struct.unpack("<4sIII", f.read(16))
        if magic != self.MAGIC[kind]:
            raise ValueError(f"bad magic {magic!r} in {path}")
        if kind == "depth":
            self.dtype = np.dtype([("key", "<i8"), ("bid", "<f4", (self.n, 2)), ("ask", "<f4", (self.n, 2))])
        else:
            self.dtype = np.dtype([("key", "<i8"), ("s", "<f8", (self.n,))])
        if os.path.getsize(self.path) != 16 + self.count * self.dtype.itemsize:
            raise ValueError(f"size mismatch in {path}")
        self._mm = np.memmap(self.path, dtype=self.dtype, mode="r", offset=16, shape=(self.count,))

    @property
    def mm(self):
        """The raw memmap: holdout stage only (in-sample code uses row / rows)."""
        if not self.allow_holdout:
            raise HoldoutSealed(f"raw memmap of {Path(self.path).name} holds sealed rows: use row()/rows(), or "
                                "open with allow_holdout=True when the orchestrator says 'holdout'")
        return self._mm

    @property
    def open_n(self) -> int:
        """Number of leading rows that may be read: all of them with allow_holdout, else those keyed < SEAL_KEY."""
        if self._open_n is None:
            self._open_n = self.count if self.allow_holdout else self._bisect(SEAL_KEY)
        return self._open_n

    def key(self, i: int) -> int:
        """Stamp of row i (0 <= i < count). Stamps are not market data and are not sealed."""
        if not 0 <= i < self.count:
            raise IndexError(i)
        return int(self._mm[i]["key"])

    def rows(self, i: int, j: int) -> np.ndarray:
        """A copy of rows [i, j) (0 <= i <= j <= count). HoldoutSealed if the range reaches a sealed row."""
        i, j = int(i), int(j)
        if not 0 <= i <= j <= self.count:
            raise IndexError((i, j))
        if j > self.open_n and j > i:
            raise HoldoutSealed(f"{Path(self.path).name} rows [{i}, {j}) reach key {self.key(j - 1)}: rows keyed "
                                f">= {SEAL_KEY} are sealed")
        return np.array(self._mm[i:j])

    def row(self, i: int):
        """A copy of row i (structured scalar). HoldoutSealed if it is a sealed row."""
        if not 0 <= int(i) < self.count:
            raise IndexError(i)
        return self.rows(i, int(i) + 1)[0]

    def _bisect(self, key: int) -> int:
        lo, hi = 0, self.count
        while lo < hi:
            mid = (lo + hi) // 2
            if int(self._mm[mid]["key"]) < key:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def bounds(self, key_lo: int, key_hi: int):
        """Row index range with key_lo <= key < key_hi (keys are strictly increasing in the files)."""
        return self._bisect(key_lo), self._bisect(key_hi)


def iter_bin(kind: str, key_lo: int, key_hi: int, allow_holdout: bool = False, chunk: int = 100_000, files=None):
    """Yield structured-array chunks with key_lo <= key < key_hi across the file chain (overlap dropped)."""
    if key_hi > SEAL_KEY and not allow_holdout:
        raise HoldoutSealed(f"{kind}.bin rows up to key {key_hi} requested: keys >= {SEAL_KEY} "
                            f"(Globex sessions >= {HOLDOUT_START}) are sealed")
    last = -1
    for path in (files if files is not None else ofb_files(kind, allow_holdout)):
        bf = BinFile(path, kind, allow_holdout)
        i, j = bf.bounds(max(key_lo, last + 1), key_hi)
        while i < j:
            blk = bf.rows(i, min(i + chunk, j))
            i += len(blk)
            last = int(blk["key"][-1])
            yield blk


# ------------------------------------------------------------------------------------------------ book features
def _near(px, sz, descending: bool):
    """Top-NLEV near-book levels of one side, vectorised ``ladder_split``: zero-size slots dropped (order kept),
    then the best-first prefix that keeps stepping away from the best by <= MAX_GAP points. Returns
    (px, sz, keep), each (rows, NLEV); ``keep`` is a prefix mask."""
    px = np.asarray(px, dtype=np.float64)
    sz = np.asarray(sz, dtype=np.float64)
    if px.shape[1] < NLEV:                                    # short snapshot: pad with empty slots
        pad = ((0, 0), (0, NLEV - px.shape[1]))
        px, sz = np.pad(px, pad), np.pad(sz, pad)
    valid = sz > 0
    if not valid[:, :NLEV].all():                             # compact populated slots to the left, order kept
        order = np.argsort(~valid, axis=1, kind="stable")[:, :NLEV]
        px, sz, valid = (np.take_along_axis(a, order, 1) for a in (px, sz, valid))
    else:
        px, sz, valid = px[:, :NLEV], sz[:, :NLEV], valid[:, :NLEV]
    d = np.diff(px, axis=1)
    step = ((d < 0) if descending else (d > 0)) & (np.abs(d) <= MAX_GAP) & valid[:, 1:]
    keep = np.logical_and.accumulate(np.concatenate([valid[:, :1], step], axis=1), axis=1)
    return px, sz, keep


def _side(px, sz, keep):
    szk = np.where(keep, sz, 0.0)
    wi = szk.argmax(axis=1)                                   # first max = the wall nearest the touch
    r = np.arange(len(px))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)       # all-NaN rows (dead grid minutes) -> NaN
        med = np.nanmedian(np.where(keep, sz, np.nan), axis=1)
    return {"top1": szk[:, 0], "top3": szk[:, :3].sum(1), "top10": szk.sum(1), "n": keep.sum(1).astype(np.float64),
            "wall_sz": szk[r, wi], "wall_dist": np.abs(px[r, wi] - px[:, 0]) / TICK, "med_sz": med,
            "best": px[:, 0]}


def book_features_arrays(bid_px, bid_sz, ask_px, ask_sz, with_mid: bool = False, with_px: bool = False) -> dict:
    """Static deployable features for many snapshots: arrays (rows, slots), slots best first as in depth.bin or
    a DOM message. Returns {column: float64 array}; every column is NaN where the book is not two-sided with a
    positive spread (``book_valid`` False). ``with_px`` adds the price anchors ``bid_px`` / ``ask_px`` (best
    bid / ask of the snapshot); ``with_mid`` adds the internal ``_mid`` (never cached)."""
    b = _side(*_near(bid_px, bid_sz, True))
    a = _side(*_near(ask_px, ask_sz, False))
    ok = (b["n"] >= 1) & (a["n"] >= 1) & (a["best"] > b["best"])
    with np.errstate(all="ignore"):
        f = {
            "bid_top1": b["top1"], "bid_top3": b["top3"], "bid_top10": b["top10"],
            "ask_top1": a["top1"], "ask_top3": a["top3"], "ask_top10": a["top10"],
            "imb3": (b["top3"] - a["top3"]) / (b["top3"] + a["top3"]),
            "imb10": (b["top10"] - a["top10"]) / (b["top10"] + a["top10"]),
            "spread_ticks": np.round((a["best"] - b["best"]) / TICK),
            "bid_wall_sz": b["wall_sz"], "bid_wall_dist": np.round(b["wall_dist"]),
            "ask_wall_sz": a["wall_sz"], "ask_wall_dist": np.round(a["wall_dist"]),
            "bid_med_sz": b["med_sz"], "ask_med_sz": a["med_sz"], "bid_n": b["n"], "ask_n": a["n"],
            "depth10": b["top10"] + a["top10"],
        }
    f = {k: np.where(ok, v, np.nan) for k, v in f.items()}
    f["book_valid"] = ok
    if with_px:
        f["bid_px"], f["ask_px"] = np.where(ok, b["best"], np.nan), np.where(ok, a["best"], np.nan)
    if with_mid:
        f["_mid"] = np.where(ok, (a["best"] + b["best"]) / 2.0, np.nan)
    return f


def _levels(side):
    a = np.asarray(side, dtype=np.float64).reshape(-1, 2) if len(side) else np.zeros((0, 2))
    return a[None, :, 0], a[None, :, 1]


def features_from_book(bids, asks, with_px: bool = False) -> dict:
    """Static deployable features of ONE snapshot. ``bids`` / ``asks`` = [[px, sz], ...] best first (desk
    ``*.depth.jsonl.gz`` lines ``{"t", "b", "a"}``, or an OFB row). Same code path as the cache builder.
    Returns {column: float} for STATIC_COLS plus ``book_valid`` (bool); NaN features when not valid.
    ``with_px`` adds the price anchors PX_COLS (best bid / ask)."""
    bp, bs = _levels(bids)
    ap, as_ = _levels(asks)
    f = book_features_arrays(bp, bs, ap, as_, with_px=with_px)
    return {k: (bool(v[0]) if k == "book_valid" else float(v[0])) for k, v in f.items()}


def dynamic_features(t_utc, bid_top10, ask_top10) -> dict:
    """Pulled/added proxies from a per-minute series (NaN = no valid in-hours snapshot that minute).
    ``*10_chg``   = top-10 depth minus the snapshot exactly one minute earlier.
    ``*10_rel15`` = top-10 depth / median of the PREVIOUS 15 minutes' snapshots (>= 8 valid) - 1.
    Strictly backward looking; minutes missing from ``t_utc`` count as missing snapshots."""
    t = np.asarray(t_utc, dtype=np.int64)
    out = {}
    if len(t) == 0:
        return {c: np.array([]) for c in DYN_COLS}
    grid = pd.RangeIndex(int(t.min()), int(t.max()) + 60, 60)
    for side, v in (("bid", bid_top10), ("ask", ask_top10)):
        s = pd.Series(np.asarray(v, dtype=np.float64), index=t).reindex(grid)
        prev = s.shift(1)
        med = prev.rolling(MED_WIN, min_periods=MED_MIN).median()
        out[f"{side}10_chg"] = (s - prev).reindex(t).to_numpy()
        out[f"{side}10_rel15"] = (s / med - 1.0).reindex(t).to_numpy()
    return out


class LiveFeatureState:
    """Minute-by-minute live twin of the cache columns STATIC_COLS + DYN_COLS + PX_COLS. Call ``update`` once
    per minute M with the DOM snapshot taken at the END of M (research books are 59.02 .. 59.98 s into the
    minute depending on the month; live samples at M + LIVE_SNAPSHOT_S, see ``desk_minute_books``); the returned
    dict is usable from M + 60 s. Feed only in-hours snapshots; a crossed / one-sided book yields NaN features
    and counts as a missing snapshot in the trailing medians."""

    def __init__(self):
        self._h = collections.OrderedDict()           # minute_utc -> (bid_top10, ask_top10)

    def update(self, minute_utc: int, bids, asks) -> dict:
        minute_utc = int(minute_utc)
        f = features_from_book(bids, asks, with_px=True)
        cur = (f["bid_top10"], f["ask_top10"])
        for i, side in enumerate(("bid", "ask")):
            prev = self._h.get(minute_utc - 60)
            f[f"{side}10_chg"] = cur[i] - prev[i] if prev is not None else float("nan")
            past = [self._h[m][i] for m in range(minute_utc - 60 * MED_WIN, minute_utc, 60) if m in self._h]
            past = [x for x in past if x == x]
            f[f"{side}10_rel15"] = (cur[i] / float(np.median(past)) - 1.0) if len(past) >= MED_MIN else float("nan")
        self._h[minute_utc] = cur
        while self._h and next(iter(self._h)) < minute_utc - 60 * MED_WIN:
            self._h.popitem(last=False)
        f["t_utc"] = minute_utc
        f["usable_at"] = usable_at(minute_utc)
        return f


def desk_minute_books(path, offset_s: float = LIVE_SNAPSHOT_S, now_ms: int | None = None, settle_ms: int = 5000):
    """Yield (minute_utc, bids, asks) from a desk ``*.depth.jsonl.gz``: for each minute M the LAST line stamped
    in (M-1 + offset_s, M + offset_s], i.e. the book standing at the snapshot instant M + offset_s. A minute with
    no DOM line in that 60 s span is skipped (treated as a missing snapshot).
    Only COMPLETED minutes are yielded: a minute is complete once a later line (stamped after its snapshot
    instant) exists, so its value can never change on a re-read. The trailing minute of the file has no such
    line; it is yielded only if the clock (``now_ms``, default the wall clock) is more than ``settle_ms`` past
    its snapshot instant, i.e. the file is a finished recording or the feed has gone quiet, never while the
    minute is still in progress. Live-parity helper only: desk recordings start 2026-09-25, outside every
    research window."""
    import gzip
    import time
    off_ms = int(round(offset_s * 1000))
    cur_m, cur = None, None
    with gzip.open(path, "rt") as fh:
        while True:
            try:
                line = fh.readline()
            except (EOFError, OSError):                       # today's file is still being written
                break
            if not line:
                break
            try:
                j = json.loads(line)
                t = int(j["t"])
            except (ValueError, KeyError, TypeError):
                continue                                      # truncated last line
            m = (t - off_ms + 59_999) // 60_000 * 60          # minute whose snapshot instant is the first >= t
            if cur is not None and m != cur_m:
                yield cur_m, cur[0], cur[1]
            cur_m, cur = m, (j.get("b") or [], j.get("a") or [])
    if cur is not None:
        now_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
        if now_ms > cur_m * 1000 + off_ms + settle_ms:        # never the in-progress minute
            yield cur_m, cur[0], cur[1]


# ------------------------------------------------------------------------------------------------ rolls
def roll_days(allow_holdout: bool = False):
    """(roll session dates, all tape session dates) exactly as R/gen_drafts.build_rolls: a session whose front
    contract (most ticks in the archive manifests) differs from the previous session's. Reads manifest names and
    tick counts only; dates >= 2025 are skipped unless allowed (detection is sequential, the list is unchanged)."""
    best = {}
    for m in TICKS_DIR.glob("20[2-9][0-9]/*.json"):
        d, c = m.name[:10], m.name[11:-5]
        if not allow_holdout and d >= HOLDOUT_START.isoformat():
            continue
        try:
            n = int(json.loads(m.read_text())["ticks"])
        except (OSError, ValueError, KeyError):
            continue
        if d not in best or n > best[d][1]:
            best[d] = (c, n)
    rolls, prev = [], None
    for d in sorted(best):
        if prev and best[d][0] != prev:
            rolls.append(d)
        prev = best[d][0]
    return [dt.date.fromisoformat(d) for d in rolls], [dt.date.fromisoformat(d) for d in sorted(best)]


def roll_block_dates(rolls, sessions) -> set:
    """Sessions where the OFB book may belong to another contract than our tape: the roll session, the one
    BEFORE it (SPEC) and the one AFTER it (measured 2021-2024: nqv0 stays on the OLD contract through roll day
    and roll day + 1, and usually through the first 1-2 evening hours of roll day + 2, which only the per-minute
    check ``mismatch_minutes`` sees; DATA.md)."""
    idx = {d: i for i, d in enumerate(sessions)}
    out = set()
    for r in rolls:
        i = idx[r]
        out.update(sessions[max(i - 1, 0):i + 2])
    return out


def mismatch_minutes(t_utc, bid_px, ask_px, tape_close) -> np.ndarray:
    """Per-minute OFB-vs-tape contract check. For each minute the signed distance (points) of our tape's close
    to the snapshot's [best bid, best ask] (0 inside; NaN without a print or a valid book). A minute is flagged
    when the median of that distance over the centred MISMATCH_WIN minutes (>= MISMATCH_MINP valid) is beyond
    +/- MISMATCH_MIN_PTS, plus MISMATCH_PAD minutes either side. A book on another contract sits a calendar
    spread away for hours, so the median crosses the tolerance exactly where the contract switches; a fast
    market moves single minutes, never the 61-minute median (in-sample maximum on clean sessions: 0.75 pts).
    Hindsight data-quality mask (it looks up to 32 minutes ahead), never a signal; live the book and the tape
    are one feed, so there is nothing to reproduce."""
    t = np.asarray(t_utc, dtype=np.int64)
    if len(t) == 0:
        return np.zeros(0, dtype=bool)
    b, a, c = (np.asarray(x, dtype=np.float64) for x in (bid_px, ask_px, tape_close))
    with np.errstate(invalid="ignore"):
        d = np.where(c > a, c - a, np.where(c < b, c - b, 0.0))
    d[~(np.isfinite(a) & np.isfinite(b) & np.isfinite(c))] = np.nan
    grid = pd.RangeIndex(int(t.min()), int(t.max()) + 60, 60)
    med = pd.Series(d, index=t).reindex(grid).rolling(MISMATCH_WIN, center=True, min_periods=MISMATCH_MINP).median()
    bad = (med.abs() > MISMATCH_MIN_PTS).astype(np.float64)
    bad = bad.rolling(2 * MISMATCH_PAD + 1, center=True, min_periods=1).max() > 0
    return bad.reindex(t).to_numpy()


# ------------------------------------------------------------------------------------------------ builder
def _flow(cut_utc: int, lo_utc: int) -> pd.DataFrame:
    return pd.read_parquet(FLOW_1M, columns=["t_utc", "session", "contract"] + FLOW_SRC,
                           filters=[("t_utc", ">=", lo_utc), ("t_utc", "<", cut_utc)])


def build_features(start=IS_START, end=IS_END, allow_holdout: bool = False, verbose: bool = True,
                   with_mid: bool = False) -> pd.DataFrame:
    """Compute the full feature table for Globex sessions ``start`` .. ``end`` (session dates; the first session
    opens 18:00 ET the evening before). Single process. Every feature is backward looking, so a longer build
    reproduces a shorter one row for row (the hindsight masks ``in_tape`` / ``ofb_mismatch`` aside).
    Without ``allow_holdout`` no OFB or flow row at or after SEAL_KEY (2024-12-31 17:00 ET) is read."""
    start, end = _as_date(start), _as_date(end)
    _guard(end, allow_holdout)
    key_lo = _date_key(start - dt.timedelta(days=1)) + 180000
    key_hi = _date_key(end + dt.timedelta(days=1))
    cut = int(pd.Timestamp(end + dt.timedelta(days=1), tz=ET).value // 10**9)      # flow rows: t_utc < cut
    if not allow_holdout:                                      # never touch the New Year's Eve evening rows
        key_hi, cut = min(key_hi, SEAL_KEY), min(cut, int(key_to_utc([SEAL_KEY])[0]))
    cols = collections.defaultdict(list)
    for blk in iter_bin("depth", key_lo, key_hi, allow_holdout):
        f = book_features_arrays(blk["bid"][:, :, 0], blk["bid"][:, :, 1], blk["ask"][:, :, 0], blk["ask"][:, :, 1],
                                 with_mid=True, with_px=True)
        cols["key"].append(blk["key"])
        for k, v in f.items():
            cols[k].append(v)
        if verbose:
            print(f"  depth rows through {blk['key'][-1]}", flush=True)
    df = pd.DataFrame({k: np.concatenate(v) for k, v in cols.items()})
    hk, hs = [], []
    for blk in iter_bin("hist", key_lo, key_hi, allow_holdout):
        hk.append(blk["key"])
        hs.append(blk["s"][:, list(RT_SLOTS)])
    h = pd.DataFrame(np.concatenate(hs), columns=RT_COLS)
    h["key"] = np.concatenate(hk)
    df = df.merge(h, on="key", how="left", validate="one_to_one")

    # ---- clock: ET wall-clock fields straight from the key, UTC through the date-offset rule
    k = df["key"].to_numpy()
    hhmm = (k // 100) % 10000
    day = pd.to_datetime((k // 10**6).astype(str), format="%Y%m%d")
    dow = day.dayofweek.to_numpy()
    in_hours = (((dow <= 3) & ((hhmm < 1700) | (hhmm >= 1800))) | ((dow == 4) & (hhmm < 1700))
                | ((dow == 6) & (hhmm >= 1800)))
    df["t_utc"] = key_to_utc(k)
    d64 = day.values.astype("datetime64[D]")
    df["globex_date"] = d64 + (hhmm >= 1700).astype(np.int64).astype("timedelta64[D]")
    df["date"] = d64 + (hhmm == 2359).astype(np.int64).astype("timedelta64[D]")   # ET date of usable_at
    df["et_min"] = (((hhmm // 100) * 60 + hhmm % 100 + 1) % 1440).astype(np.int16)
    df = df[in_hours].drop(columns="key").sort_values("t_utc", kind="mergesort").reset_index(drop=True)
    df["session"] = session_of(df["et_min"].to_numpy())

    # ---- own flow (minute M = prints in [M, M+60 s)) and tape bounds per session
    fl = _flow(cut, int(df["t_utc"].min()))
    fl = fl.rename(columns={c: "f_" + c for c in FLOW_SRC})
    df = df.merge(fl.drop(columns="session"), on="t_utc", how="left", validate="one_to_one")
    b = fl.groupby("session")["t_utc"].agg(["min", "max"])
    b.index = pd.to_datetime(b.index).values.astype("datetime64[D]")
    gd = df["globex_date"].to_numpy().astype("datetime64[D]")
    lo = pd.Series(b["min"]).reindex(gd).to_numpy()
    hi = pd.Series(b["max"]).reindex(gd).to_numpy()
    t = df["t_utc"].to_numpy()
    df["in_tape"] = (t >= lo) & (t <= hi)                                  # NaN bounds (no tape) -> False

    # ---- contract hygiene
    rolls, sessions = roll_days(allow_holdout)
    blk_days = np.array(sorted(roll_block_dates(rolls, sessions)), dtype="datetime64[D]")
    df["roll_block"] = np.isin(gd, blk_days)
    diff = (df["_mid"] - df["f_c"]).abs().where(df["in_tape"])
    med = diff.groupby(df["globex_date"]).median()
    bad = med.index[med > MISMATCH_PTS].values.astype("datetime64[D]")           # whole session on another contract
    df["ofb_mismatch"] = np.isin(gd, bad) | mismatch_minutes(t, df["bid_px"], df["ask_px"],   # ... or these minutes
                                                             df["f_c"].where(df["in_tape"]))
    df["book_valid"] = df["book_valid"].astype(bool)
    df["book_ok"] = df["book_valid"] & df["in_tape"] & ~df["roll_block"] & ~df["ofb_mismatch"]

    # ---- dynamic features on snapshots that are valid, inside the traded session and on the tape's contract
    live = (df["book_valid"] & df["in_tape"] & ~df["ofb_mismatch"]).to_numpy()
    dyn = dynamic_features(t, np.where(live, df["bid_top10"], np.nan), np.where(live, df["ask_top10"], np.nan))
    for c in DYN_COLS:
        df[c] = dyn[c]
    d10 = df["depth10"].where(df["book_ok"])
    tod = df["et_min"]
    med20 = d10.groupby(tod).transform(lambda s: s.shift(1).rolling(TOD_DAYS, min_periods=TOD_MIN).median())
    df["depth10_rel20d"] = d10 / med20 - 1.0

    # ---- index, dtypes, window
    df["usable_at"] = pd.to_datetime(usable_at(df["t_utc"]), unit="s", utc=True)
    keep = (df["globex_date"] >= np.datetime64(start)) & (df["date"] <= np.datetime64(end))
    if not allow_holdout:                                      # New Year's Eve evening belongs to a 2025 session
        keep &= df["globex_date"] < np.datetime64(HOLDOUT_START)
    df = df[keep.to_numpy()].set_index("usable_at")
    for c in BOOK_COLS + PX_COLS + RT_COLS + FLOW_COLS:
        df[c] = df[c].astype(np.float64 if c in PX_COLS + ["f_o", "f_h", "f_l", "f_c", "rt_cum_delta", "f_cum_delta"]
                             else np.float32)
    df["date"] = df["date"].dt.date
    df["globex_date"] = df["globex_date"].dt.date
    order = TAG_COLS + FLAG_COLS + BOOK_COLS + PX_COLS + FLOW_COLS + RT_COLS + (["_mid"] if with_mid else [])
    return df[order]


def cache_path(year: int) -> Path:
    return CACHE / f"l2feat_NQ_{year}.parquet"


def build_cache(start=IS_START, end=IS_END, allow_holdout: bool = False, verbose: bool = True,
                rewrite_in_sample: bool = False, phase_checked: bool = False) -> list:
    """Build and write one parquet per ET year of ``usable_at``. The in-sample call writes 2021..2024. A holdout
    call (``allow_holdout=True``, keep ``start`` at IS_START so trailing features are warm) writes ONLY the
    2025+ files, leaving the frozen in-sample files byte-identical, unless ``rewrite_in_sample``.
    A holdout call RUNS ``phase_check`` itself on every holdout month of the build (RTH + overnight) before any
    feature is computed and PERSISTS the verdicts (cache/phase_guard.json): l2sim then runs the months that
    failed with the 1 s execution guard and refuses holdout months that were never checked. ``phase_checked`` is
    the old honour flag: accepted, ignored. The check's result is kept in ``build_cache.last_phase``."""
    end = _as_date(end)
    _guard(end, allow_holdout)
    build_cache.last_phase = None
    if allow_holdout and end >= HOLDOUT_START:
        months = [str(m) for m in pd.period_range(max(_as_date(start), HOLDOUT_START), end, freq="M")]
        res = phase_check(months, allow_holdout=True, raise_on_fail=False, persist=True)
        build_cache.last_phase = res
        if verbose:
            print(f"  phase check {months[0]}..{months[-1]}: " + ("ok" if res["ok"] else
                  f"FAILED {res['failed']} -> 1 s execution guard enforced by l2sim ({PHASE_GUARD.name})"), flush=True)
    df = build_features(start, end, allow_holdout, verbose)
    CACHE.mkdir(parents=True, exist_ok=True)
    out = []
    years = pd.DatetimeIndex(pd.to_datetime(df["date"])).year
    for y in sorted(set(years)):
        if allow_holdout and y < HOLDOUT_START.year and not rewrite_in_sample:
            continue
        p = cache_path(int(y))
        tmp = p.with_name(p.name + ".tmp")                     # atomic: readers never see a half-written file
        df[years == y].to_parquet(tmp, compression="zstd")
        os.replace(tmp, p)
        out.append(p)
        if verbose:
            print(f"  wrote {p.name}: {int((years == y).sum()):,} rows", flush=True)
    return out


# ------------------------------------------------------------------------------------------------ loader
def load_features(start=None, end=None, allow_holdout: bool = False, columns=None,
                  mask_bad_book: bool = True) -> pd.DataFrame:
    """Feature table for ET dates ``start`` .. ``end`` inclusive (``date`` = ET calendar date of ``usable_at``),
    indexed by ``usable_at`` (UTC, ns). Defaults = the whole in-sample window (first row: Globex open
    2021-09-21 18:00 ET, usable 18:01; last date 2024-12-31). Raises HoldoutSealed if ``end`` >= 2025-01-01
    unless ``allow_holdout``.
    ``mask_bad_book`` (default) sets book, price-anchor and research-tier columns to NaN wherever ``book_ok`` is
    False (roll block, other-contract sessions / minutes, crossed / halted book, outside the traded session); flow
    columns are untouched. Unmasked, ``bid_px`` / ``ask_px`` are raw OFB prices and NOT tape coordinates there."""
    start = IS_START - dt.timedelta(days=1) if start is None else _as_date(start)
    end = IS_END if end is None else _as_date(end)
    _guard(end, allow_holdout)
    if columns is not None:
        columns = list(dict.fromkeys(list(columns) + ["date", "book_ok"]))
    parts = []
    for y in range(start.year, end.year + 1):
        p = cache_path(y)
        if y >= HOLDOUT_START.year and not allow_holdout:      # belt and braces: never open a sealed file
            raise HoldoutSealed(f"{p.name} is sealed")
        if p.exists():
            parts.append(pd.read_parquet(p, columns=columns))
    if not parts:
        raise FileNotFoundError(f"no cache for {start}..{end} under {CACHE} (run: python l2data.py build)")
    df = pd.concat(parts)
    d = df["date"]
    df = df[(d >= start) & (d <= end)]
    if not allow_holdout and len(df) and df["date"].max() >= HOLDOUT_START:
        raise HoldoutSealed("cache returned sealed rows")
    if mask_bad_book:
        bad = ~df["book_ok"].to_numpy()
        for c in df.columns:
            if c in BOOK_COLS or c in PX_COLS or c in RT_COLS:
                df[c] = df[c].where(~bad)
    return df


# ------------------------------------------------------------------------------------------------ phase check
def _phase_keys(d: dt.date, part: str) -> list:
    """OFB key ranges [lo, hi) of one Globex session ``d`` for a phase bucket: 'rth' = stamps 09:30 .. 15:59 ET;
    'overnight' = every other in-hours stamp of the session (18:00 .. 23:59 the evening before, 00:00 .. 09:29,
    16:00 .. 16:59), i.e. the rows asia / london / the 03:00 and 09:30 opens decide on."""
    k = _date_key(d)
    if part == "rth":
        return [(k + 93000, k + 160000)]
    e = _date_key(d - dt.timedelta(days=1))
    return [(e + 180000, e + 240000), (k, k + 93000), (k + 160000, k + 170000)]


def _session_phase(d: dt.date, depth: BinFile, part: str = "rth", tape=None):
    """Snapshot phase of one session and bucket (``_phase_keys``): for every row with a two-sided book, the
    distance (points) from the last tape print before ``M + tau`` to [best bid, best ask], for every tau of
    PHASE_GRID_S. Returns (n_minutes, per-tau distance sums) or None when the session has no tape / too few
    rows. The tau minimising the mean distance is the instant the vendor took the book.
    'overnight' keeps the minutes whose book is on the tape's contract only (the first evening hours after a
    roll block still show the old contract, a calendar spread away at every tau) and has no per-session
    minimum: its minutes are pooled per month by ``phase_check``. ``tape`` = (ts, px) already loaded."""
    if tape is None:
        p = OFB_TICK_DIR / f"{d:%Y}" / f"{d:%m}" / f"{d:%Y-%m-%d}.parquet"
        if not p.exists():
            return None
        tk = pd.read_parquet(p, columns=["ts_ns", "price"])
        tape = (tk["ts_ns"].to_numpy(), tk["price"].to_numpy())
    ts, px = tape
    rth = part == "rth"
    blks = []
    for lo, hi in _phase_keys(d, part):
        i, j = depth.bounds(lo, hi)
        if j > i:
            blks.append(depth.rows(i, j))
    n_rows = sum(len(b) for b in blks)
    if n_rows < (PHASE_MIN_MINUTES if rth else 1) or len(ts) == 0:
        return None
    blk = blks[0] if len(blks) == 1 else np.concatenate(blks)
    f = book_features_arrays(blk["bid"][:, :, 0], blk["bid"][:, :, 1], blk["ask"][:, :, 0], blk["ask"][:, :, 1],
                             with_px=True)
    m_ns = key_to_utc(blk["key"]) * 10**9
    q = m_ns[:, None] + np.round(PHASE_GRID_S * 1e9).astype(np.int64)[None, :]
    k = np.searchsorted(ts, q, side="left")
    ok = f["book_valid"] & (k.min(axis=1) > 0) & (ts[np.minimum(k[:, 0], len(ts) - 1) - 1] >= m_ns - 60 * 10**9)
    if rth and ok.sum() < PHASE_MIN_MINUTES:
        return None
    last = px[k[ok] - 1]
    dist = np.maximum(np.maximum(f["bid_px"][ok, None] - last, last - f["ask_px"][ok, None]), 0.0)
    if not rth:
        dist = dist[dist.min(axis=1) <= MISMATCH_PTS]          # the book of another contract measures nothing
    if not len(dist):
        return None
    return int(len(dist)), dist.sum(axis=0)


def _argmin_s(curve) -> float:
    """Latest grid instant attaining the minimum (ties resolve towards the boundary: the conservative side)."""
    c = np.asarray(curve, dtype=np.float64)
    return float(PHASE_GRID_S[np.flatnonzero(c <= c.min() + 1e-12)[-1]])


def persist_phase(result: dict, path=None) -> Path:
    """Merge a ``phase_check`` result into cache/phase_guard.json: {"guard_ms", "max_phase_s", "months": {ym:
    {"ok", "failed_parts", "phase_s", "sess_max_s", "on_phase_s", "overnight"}}, "failed": [ym, ...]}. Months
    checked earlier and not in ``result`` keep their verdict. This file is what l2sim ENFORCES: a run that reads
    book features uses EXEC_GUARD_MS of extra placement latency on every session of a failed month, and a
    holdout run refuses months that are not in it. Atomic (own temp name per process)."""
    p = Path(path) if path is not None else PHASE_GUARD
    cur = json.loads(p.read_text()) if p.exists() else {}
    months = dict(cur.get("months") or {})
    for ym, r in result["months"].items():
        months[ym] = {"ok": bool(r["ok"]), "failed_parts": list(r.get("failed_parts") or ([] if r["ok"] else ["rth"])),
                      "phase_s": r.get("phase_s"), "sess_max_s": r.get("sess_max_s"), "on_phase_s": r.get("on_phase_s"),
                      "overnight": bool(result.get("overnight", False))}
    out = {"guard_ms": EXEC_GUARD_MS, "max_phase_s": result["max_phase_s"], "months": dict(sorted(months.items())),
           "failed": sorted(m for m, r in months.items() if not r["ok"]),
           "updated_et": pd.Timestamp.now(tz=ET).isoformat(timespec="seconds")}
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(out, indent=1))
    os.replace(tmp, p)
    return p


def guard_months(path=None) -> list:
    """Months whose book features need the 1 s execution guard (failed the persisted phase check)."""
    p = Path(path) if path is not None else PHASE_GUARD
    return list(json.loads(p.read_text()).get("failed") or []) if p.exists() else []


def phase_check(months=None, allow_holdout: bool = False, max_phase_s: float = PHASE_MAX_S,
                raise_on_fail: bool = True, verbose: bool = False, overnight: bool = True, persist: bool = False) -> dict:
    """Mechanical timestamp-law check, per calendar month (the vendor's snapshot phase is constant within a
    month and differs between months). ``months`` = iterable of 'YYYY-MM' (None = every in-sample month).

    RTH bucket (stamps 09:30 .. 15:59 ET): every tape session outside the roll block is measured with
    ``_session_phase``; the month's ``phase_s`` is the instant minimising the pooled distance over all its
    sessions, ``sess_min/med/max_s`` the per-session instants (0.02 s grid).
    OVERNIGHT bucket (every other in-hours stamp: the evening before, 00:00 .. 09:29, 16:00 .. 16:59; the rows
    asia, london and the 03:00 / 09:30 opens decide on): the minutes of the same sessions are POOLED per month
    (per-session overnight estimates are too noisy) -> ``on_phase_s``, ``on_minutes``, ``on_dist_at_phase_pts``.
    A month FAILS (``failed_parts``) when ``phase_s`` or ``sess_max_s`` ('rth') or ``on_phase_s`` ('overnight')
    is >= ``max_phase_s`` (59.99: the book would be taken at or after the minute boundary, so reading it at
    M + 60 s could be a look-ahead), when it has OFB rows but no measurable session, or when it has measured
    RTH sessions but fewer than PHASE_ON_MIN_MINUTES measurable overnight minutes although overnight rows exist.
    A month with no OFB depth rows at all has no book features and passes vacuously (``sessions = 0``).
    ``overnight=False`` = the RTH bucket alone (the pre-2026-10-02 check).

    Returns {"ok", "max_phase_s", "failed": [...], "range_s", "sess_range_s", "on_range_s", "months": {ym: {...}}}
    and raises PhaseCheckFailed (with ``.result``) when a month fails, unless ``raise_on_fail=False``.
    ``persist=True`` merges the verdicts into cache/phase_guard.json (``persist_phase``) BEFORE raising: l2sim
    runs every book-feature session of a failed month with the 1 s execution guard (DATA.md section 1). The
    holdout build (``build_cache(allow_holdout=True)``) calls this itself, persisted, on its own months."""
    if months is None:
        months = [str(m) for m in pd.period_range(IS_START, IS_END, freq="M")]
    months = sorted({str(m)[:7] for m in months})
    last_day = max((pd.Period(m, freq="M").end_time.date() for m in months), default=IS_START)
    if last_day > IS_END and not allow_holdout:
        raise HoldoutSealed(f"phase_check through {last_day}: months after {IS_END:%Y-%m} are sealed "
                            "(pass allow_holdout=True only when the orchestrator says 'holdout')")
    rolls, sessions = roll_days(allow_holdout)
    block = roll_block_dates(rolls, sessions)
    files = [BinFile(f, "depth", allow_holdout) for f in ofb_files("depth", allow_holdout)]
    out = {}
    for ym in months:
        per = pd.Period(ym, freq="M")
        k0, k1 = _date_key(per.start_time.date()), _date_key((per + 1).start_time.date())
        n_rows = sum(max(0, b - a) for a, b in (bf.bounds(k0, k1) for bf in files))
        n_min, curve, per_sess = 0, np.zeros(len(PHASE_GRID_S)), []
        on_min, on_curve, on_rows = 0, np.zeros(len(PHASE_GRID_S)), 0
        for d in sessions:
            if not (d.year == per.year and d.month == per.month) or d in block:
                continue
            tp = OFB_TICK_DIR / f"{d:%Y}" / f"{d:%m}" / f"{d:%Y-%m-%d}.parquet"
            if not tp.exists():
                continue
            tk = pd.read_parquet(tp, columns=["ts_ns", "price"])
            tape = (tk["ts_ns"].to_numpy(), tk["price"].to_numpy())
            for bf in files:
                r = _session_phase(d, bf, "rth", tape)
                if r is not None:
                    n_min += r[0]
                    curve += r[1]
                    per_sess.append(_argmin_s(r[1]))
                    break
            if overnight:
                for bf in files:
                    on_rows += sum(max(0, b - a) for a, b in (bf.bounds(lo, hi) for lo, hi in _phase_keys(d, "overnight")))
                    r = _session_phase(d, bf, "overnight", tape)
                    if r is not None:
                        on_min += r[0]
                        on_curve += r[1]
                        break
        parts = []
        if per_sess:
            row = {"phase_s": _argmin_s(curve), "sess_min_s": float(np.min(per_sess)),
                   "sess_med_s": round(float(np.median(per_sess)), 2), "sess_max_s": float(np.max(per_sess)),
                   "sessions": len(per_sess), "minutes": n_min,
                   "dist_at_phase_pts": round(float(curve.min() / n_min), 4)}
            if not max(row["phase_s"], row["sess_max_s"]) < max_phase_s:
                parts.append("rth")
        else:
            row = {"phase_s": None, "sess_min_s": None, "sess_med_s": None, "sess_max_s": None, "sessions": 0,
                   "minutes": 0, "dist_at_phase_pts": None}
            if n_rows:
                parts.append("rth")
        row["margin_s"] = None if row["phase_s"] is None else round(60.0 - max(row["phase_s"], row["sess_max_s"]), 2)
        if overnight:
            measured = on_min >= PHASE_ON_MIN_MINUTES
            row.update(on_phase_s=_argmin_s(on_curve) if measured else None, on_minutes=int(on_min),
                       on_dist_at_phase_pts=round(float(on_curve.min() / on_min), 4) if measured else None)
            row["on_margin_s"] = None if not measured else round(60.0 - row["on_phase_s"], 2)
            if (measured and not row["on_phase_s"] < max_phase_s) or (not measured and on_rows and per_sess):
                parts.append("overnight")
        row["failed_parts"] = parts
        row["ok"] = not parts
        row["ofb_rows"] = int(n_rows)
        out[ym] = row
        if verbose:
            print(f"  {ym}: {row}", flush=True)
    failed = [m for m, r in out.items() if not r["ok"]]
    ph = [r["phase_s"] for r in out.values() if r["phase_s"] is not None]
    ps = [x for r in out.values() if r["phase_s"] is not None for x in (r["sess_min_s"], r["sess_max_s"])]
    on = [r["on_phase_s"] for r in out.values() if r.get("on_phase_s") is not None]
    res = {"ok": not failed, "max_phase_s": max_phase_s, "failed": failed, "overnight": bool(overnight),
           "range_s": [min(ph), max(ph)] if ph else None, "sess_range_s": [min(ps), max(ps)] if ps else None,
           "on_range_s": [min(on), max(on)] if on else None, "months": out}
    if persist:
        persist_phase(res)
    if failed and raise_on_fail:
        raise PhaseCheckFailed(f"snapshot phase not proven < {max_phase_s} s in {failed}: do not use usable_at = "
                               "M + 60 s there without the 1 s execution guard (DATA.md section 1)", res)
    return res


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "build":
        for p in build_cache():
            print(p)
    elif cmd == "phase":
        r = phase_check(verbose=True, raise_on_fail=False, persist=True)
        OUT.mkdir(exist_ok=True)
        (OUT / "phase_check.json").write_text(json.dumps(r, indent=1))
        print("ok" if r["ok"] else f"FAILED {r['failed']} (1 s execution guard enforced by l2sim)", "rth range",
              r["range_s"], "overnight range", r["on_range_s"], "->", PHASE_GUARD)
        sys.exit(0 if r["ok"] else 1)
    elif cmd == "report":
        import data_report
        data_report.main()
    else:
        print(__doc__)

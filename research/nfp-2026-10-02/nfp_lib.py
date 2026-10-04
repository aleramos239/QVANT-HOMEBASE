"""Shared engine for the 2026-10-02 NFP LucidPro full-port study.

Tick replay of an 08:30 ET OCO stop-entry straddle (anchor = last print before 08:30:00.000,
entries anchor +/- offset live at +85 ms, cancel 08:45, flat 09:55), same fill model as
research/gc_0830_redfolder_straddle_ticks.py (stop entry pays the gap, target is a resting limit
needing 1-tick penetration, stop is touch / pays the gap), plus pessimistic knobs:
  * entry slippage and stop slippage in ticks (target fills get none),
  * "cascade": a stop that triggers within 2 s of 08:30:00 fills at the worst print of the
    following 1 s window (the 08:30:01 stop cascade), then slippage on top.
Python: /Users/ramoscapital/ONYX TRADING/.venv/bin/python (numpy + pandas).
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ET = ZoneInfo("America/New_York")
HERE = Path(__file__).resolve().parent
CACHE = Path("/private/tmp/claude-501/-Users-ramoscapital-Library-Application-Support-Claude-scratch-workspaces-bede25d7-4e1b-4b3e-b8ef-70c7ef831e62-9ebb0405-7969-47e0-923d-777091be95f0-scratch-2026-09-30-896b12/db1f7d1a-1c40-4988-9502-1482f7a31fc2/scratchpad")
ARCH = Path.home() / "futures_ticks"
CAL = Path.home() / "ramos-quant-homebase/homebase/strategies/data/gc_0830_redfolder_days_2021_2026.csv"

IS_END = dt.date(2024, 12, 31)
HO_START = dt.date(2025, 1, 1)
PLACEMENT_NS = 85_000_000
MLL_START = -2000.0     # LucidPro 50K: balance may not reach start - 2000
TARGET = 3000.0

# root -> (full-size $/pt, tick, micro root, micro $/pt)
SPEC = {
    "GC": dict(pv=100.0, tick=0.10, mpv=10.0),
    "NQ": dict(pv=20.0, tick=0.25, mpv=2.0),
    "ES": dict(pv=50.0, tick=0.25, mpv=5.0),
    "SI": dict(pv=5000.0, tick=0.005, mpv=1000.0),   # SIL = 1,000 oz
}
COMM_MINI, COMM_MICRO = 4.00, 1.50     # USD round turn per contract (micro = assumption)


def ns(d: dt.date, h: int, m: int, s: int = 0) -> int:
    return int(dt.datetime(d.year, d.month, d.day, h, m, s, tzinfo=ET).timestamp() * 1e9)


def events() -> list[tuple[dt.date, str]]:
    out = []
    with open(CAL, newline="") as fh:
        for r in csv.DictReader(fh):
            d = dt.date.fromisoformat(r["date"])
            if d < dt.date(2021, 9, 22):
                continue
            tags = set(r["tag"].split("+"))
            if "NFP" in tags:
                out.append((d, "NFP"))
            elif "CPI" in tags:
                out.append((d, "CPI"))
    return sorted(out)


def front_path(root: str, d: dt.date) -> Path | None:
    ydir = ARCH / root / str(d.year)
    best, bn = None, 0
    for man in ydir.glob(f"{d:%Y-%m-%d}_*.json"):
        try:
            n = json.loads(man.read_text())["ticks"]
        except Exception:
            continue
        if n > bn:
            best, bn = man, n
    return best.with_suffix(".csv.gz") if best and bn >= 1000 else None


def load_event(args):
    root, d = args
    p = front_path(root, d)
    if p is None:
        return (root, d, None)
    df = pd.read_csv(p, usecols=["price", "ts_ns"], dtype={"price": "float64", "ts_ns": "int64"})
    t0, t1 = ns(d, 8, 20), ns(d, 9, 56)
    df = df[(df.ts_ns >= t0) & (df.ts_ns < t1)]
    if len(df) < 50:
        return (root, d, None)
    return (root, d, (df.ts_ns.to_numpy(), df.price.to_numpy()))


# ---------------------------------------------------------------- replay
def first_idx(mask: np.ndarray, start: int) -> int:
    if start >= len(mask):
        return -1
    sub = mask[start:]
    j = int(sub.argmax())
    return start + j if sub[j] else -1


def prep(d: dt.date, ts: np.ndarray, px: np.ndarray) -> dict | None:
    t_fire = ns(d, 8, 30)
    i_pre = int(np.searchsorted(ts, t_fire, side="left")) - 1
    if i_pre < 0:
        return None
    ts, px = ts[i_pre:], px[i_pre:]
    t_live = t_fire + PLACEMENT_NS
    return dict(ts=ts, px=px, anchor=float(px[0]), t_fire=t_fire,
                i0=int(np.searchsorted(ts, t_live, side="left")),
                i_c=int(np.searchsorted(ts, ns(d, 8, 45), side="left")),
                i_f=int(np.searchsorted(ts, ns(d, 9, 55), side="right")))


def first_minute_range(P: dict) -> float:
    ts, px = P["ts"], P["px"]
    a = int(np.searchsorted(ts, P["t_fire"], side="left"))
    b = int(np.searchsorted(ts, P["t_fire"] + 60_000_000_000, side="left"))
    seg = px[a:b]
    return float(seg.max() - seg.min()) if len(seg) else float("nan")


def replay(P: dict, off: float, sl: float, tp: float, tick: float, pv: float, comm: float,
           e_slip: float, s_slip: float, cascade: bool) -> tuple[float, str]:
    """Returns (net USD, outcome) with outcome in NOFILL / TP / SL / FLAT."""
    ts, px = P["ts"], P["px"]
    buy, sell = P["anchor"] + off, P["anchor"] - off
    i0, i_c, i_f = P["i0"], P["i_c"], P["i_f"]
    ib = first_idx(px >= buy, i0)
    is_ = first_idx(px <= sell, i0)
    c = [(i, s) for i, s in ((ib, 1), (is_, -1)) if i != -1 and i < i_c]
    if not c:
        return 0.0, "NOFILL"
    i_e, side = min(c)
    trig = buy if side == 1 else sell
    es, ss = e_slip * tick, s_slip * tick
    fill = (max(trig, px[i_e]) + es) if side == 1 else (min(trig, px[i_e]) - es)
    slp, tpp = fill - side * sl, fill + side * tp
    if side == 1:
        i_sl, i_tp = first_idx(px <= slp, i_e), first_idx(px >= tpp + tick, i_e)
    else:
        i_sl, i_tp = first_idx(px >= slp, i_e), first_idx(px <= tpp - tick, i_e)
    ends = [(i, w) for i, w in ((i_sl, "SL"), (i_tp, "TP")) if i != -1 and i < i_f]
    if ends:
        i_x, why = min(ends)
        if why == "SL":
            base = min(slp, px[i_x]) if side == 1 else max(slp, px[i_x])
            if cascade and ts[i_x] <= P["t_fire"] + 2_000_000_000:
                j = int(np.searchsorted(ts, ts[i_x] + 1_000_000_000, side="right"))
                w = px[i_x:j]
                base = min(base, float(w.min())) if side == 1 else max(base, float(w.max()))
            exit_px = base - side * ss
        else:
            exit_px = tpp
    else:
        i_x, why = min(i_f, len(px)) - 1, "FLAT"
        exit_px = float(px[i_x]) - side * ss
    return side * (exit_px - fill) * pv - comm, why


def tick_floor(x: float, tick: float) -> float:
    return math.floor(x / tick + 1e-9) * tick


def tick_ceil(x: float, tick: float) -> float:
    return math.ceil(x / tick - 1e-9) * tick


def bracket(pv: float, comm: float, tick: float, sl_usd: float, tp_net_usd: float):
    """Stop in pts so the stop is <= sl_usd gross; target in pts so the TP nets >= tp_net_usd after commission."""
    return (tick_floor(sl_usd / pv, tick), tick_ceil((tp_net_usd + comm) / pv, tick))


# ---------------------------------------------------------------- eval simulation
def eval_run(nets: list[float], target=TARGET) -> tuple[str, int]:
    """Run one LucidPro 50K eval through consecutive event P&Ls (EOD trail, one event per day).
    Returns (pass|bust|alive, events used). Bust when balance P&L <= trailing MLL (realised exits)."""
    pnl, peak = 0.0, 0.0
    for k, r in enumerate(nets, 1):
        pnl += r
        mll = min(peak - 2000.0, 100.0)
        if pnl <= mll:
            return "bust", k
        if pnl >= target:
            return "pass", k
        peak = max(peak, pnl)
    return "alive", len(nets)


def wilson(k: int, n: int, z=1.96):
    if n == 0:
        return (float("nan"),) * 2
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return c - h, c + h

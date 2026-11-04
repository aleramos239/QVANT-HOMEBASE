"""More book / tape filters for the two-account 9:30 test (2 NQ, 50-pt stop), in-sample days only.

Book (vendor 1-min top-10, rows 09:20..09:29 = known at 09:30, book_ok only):
  L5 depth trend, L9 wall size / distance, L10 size per level, L11 contracts at top 3 levels, L12 spread,
  L13 book churn, L14 icebergs*, L15 queue depletion*, L16 vendor delta*   (* research tier: not reproducible live)
  (the vendor book has no per-level order count: bid_n is just the level count, always 10)
Flow (our own 1-min flow f_*, 08:30-09:29): sweeps, biggest print, biggest resting order
Tape (ticks, 08:30-09:29:59, tick-rule side): prints (how many orders), contracts, avg / 90th pct print size, |delta|
Writes the full tables to two_account_filters_more.md and prints a short summary.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import glob
import io
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "engine"))
sys.path.insert(0, str(HERE))
import l2sim as S  # noqa: E402
import pair_filters as P  # noqa: E402

TICK_CACHE = HERE / "tickfeat2.csv"
LAB = ["lowest 20%", "20-40%", "40-60%", "60-80%", "highest 20%"]


def rel(s):  # vs the prior 20 in-sample days with data
    return s / s.rolling(20, min_periods=10).mean().shift(1)


def book(days):
    files = sorted(glob.glob(str(HERE.parent / "engine/cache/l2feat_NQ_*.parquet")))
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    df["date"] = df["date"].astype(str)
    df = df[df.date.isin(set(days))].drop_duplicates("t_utc")
    df["hm"] = pd.to_datetime(df.t_utc, unit="s", utc=True).dt.tz_convert("America/New_York").dt.strftime("%H:%M")
    pm = df[(df.hm >= "08:30") & (df.hm <= "09:29")]
    fg = pm.groupby("date")
    w = df[(df.hm >= "09:20") & (df.hm <= "09:29") & df.book_ok.astype(bool)]
    g = w.groupby("date")
    last = w[w.hm == "09:29"].set_index("date")
    first = w[w.hm == "09:20"].set_index("date")
    rt = df[(df.hm >= "08:30") & (df.hm <= "09:29") & df.book_ok.astype(bool)].groupby("date")
    f = pd.DataFrame({
        "depth_trend": last.depth10 / first.depth10 - 1,
        "wall_sz": np.maximum(last.bid_wall_sz, last.ask_wall_sz),
        "wall_dist": np.minimum(last.bid_wall_dist, last.ask_wall_dist),
        "lvl_sz": (last.bid_med_sz + last.ask_med_sz) / 2,
        "top3": last.bid_top3 + last.ask_top3,
        "spread": g.spread_ticks.mean(),
        "churn": g.apply(lambda x: ((x.bid10_chg.abs() + x.ask10_chg.abs()) / x.depth10).mean()),
        "ice": g.rt_ice_bid.sum() + g.rt_ice_ask.sum(),
        "qdepl": g.rt_qdepl_bid.mean() + g.rt_qdepl_ask.mean(),
        "vdelta": (rt.rt_cum_delta.last() - rt.rt_cum_delta.first()).abs() / fg.f_volume.sum(),
        "sweeps": fg.f_sweeps_buy.sum() + fg.f_sweeps_sell.sum(),
        "bigprint": fg.f_big_print.max(),
        "bigorder": fg.f_big_order.max(),
        "rows": g.size(),
    }).reindex(days)
    f.loc[f.rows < 8, ["spread", "churn", "ice", "qdepl"]] = np.nan
    for c in ["wall_sz", "lvl_sz", "top3", "ice", "qdepl", "sweeps", "bigprint", "bigorder"]:
        f[c + "_rel"] = rel(f[c])
    return f


def one(d: str):
    tp = S.load_tape(d, "NQ", allow_holdout=S.ALLOW_WF_IS)
    if tp is None:
        return d, np.nan, np.nan, np.nan, np.nan, np.nan
    day = dt.date.fromisoformat(d)
    a, c = (np.searchsorted(tp.ts, S.et_ns(day, x)) for x in ("08:30", "09:30"))
    px, sz = tp.px[a:c], tp.size[a:c]
    if len(px) < 2:
        return d, np.nan, np.nan, np.nan, np.nan, np.nan
    step = np.sign(np.diff(px, prepend=px[0]))
    side = pd.Series(np.where(step == 0, np.nan, step)).ffill().fillna(0).to_numpy()
    return d, len(sz), float(sz.sum()), float(sz.mean()), float(np.percentile(sz, 90)), abs(float((side * sz).sum()))


def tape(days):
    if TICK_CACHE.exists():
        t = pd.read_csv(TICK_CACHE, index_col=0)
        if set(days) <= set(t.index):
            return t.reindex(days)
    with Pool(8) as pool:
        rows = pool.map(one, days, chunksize=8)
    t = pd.DataFrame(rows, columns=["date", "prints", "contracts", "avg_sz", "p90_sz", "absdelta"]).set_index("date")
    t.to_csv(TICK_CACHE)
    return t.reindex(days)


FILTERS = [  # (title, column, rule)  rule: "q" quintiles
    ("L5. Depth trend: top-10 depth 09:29 vs 09:20", "depth_trend"),
    ("L9a. Biggest wall (top 10) at 09:29 vs 20-day avg", "wall_sz_rel"),
    ("L9b. Nearest wall distance at 09:29 (ticks)", "wall_dist"),
    ("L10. Size per price level (median) at 09:29 vs 20-day avg", "lvl_sz_rel"),
    ("L11. Contracts at the top 3 levels at 09:29 vs 20-day avg", "top3_rel"),
    ("L12. Spread, mean ticks 09:20-09:29", "spread"),
    ("L13. Book churn: mean |depth change| / depth, 09:20-09:29", "churn"),
    ("L14. Icebergs 09:20-09:29 vs 20-day avg (vendor, research tier)", "ice_rel"),
    ("L15. Queue depletion 09:20-09:29 vs 20-day avg (vendor, research tier)", "qdepl_rel"),
    ("L16. Vendor delta 08:30-09:29 |delta| / volume (research tier)", "vdelta"),
    ("F1. Sweeps 08:30-09:29 vs 20-day avg", "sweeps_rel"),
    ("F2. Biggest print 08:30-09:29 vs 20-day avg", "bigprint_rel"),
    ("F3. Biggest resting order 08:30-09:29 vs 20-day avg", "bigorder_rel"),
    ("P1. Prints (how many orders) 08:30-09:29 vs 20-day avg", "prints_rel"),
    ("P2. Contracts traded 08:30-09:29 vs 20-day avg", "contracts_rel"),
    ("P3. Avg print size 08:30-09:29 vs 20-day avg", "avg_sz_rel"),
    ("P4. 90th-pct print size 08:30-09:29", "p90_sz"),
    ("P5. |Delta| contracts 08:30-09:29 vs 20-day avg", "absdelta_rel"),
]


def bins_of(s):
    e = np.unique(s.dropna().quantile([.2, .4, .6, .8]).values)
    edges = [-np.inf] + list(e) + [np.inf]
    labs = LAB if len(edges) == 6 else [f"group {i + 1}" for i in range(len(edges) - 1)]
    return edges, labs


def summary(name, col, edges, labs, f, pairs):
    cut = pd.cut(f[col], edges, labels=labs)
    rows = []
    for lab in labs:
        ds = cut[cut == lab].index
        for rr in ("1:3", "1:4"):
            q = pairs[rr].loc[pairs[rr].index.intersection(ds)]
            c = q.l + q.s
            yrs = c.groupby(c.index.str[:4]).sum()
            rows.append((lab, rr, len(q), ((q.l > 0) | (q.s > 0)).mean() * 100, c.mean(), c.sum() / P.weeks(pairs[rr].index),
                         int((yrs > 0).sum()), len(yrs)))
    return rows


def main():
    pairs = P.paired()
    days = list(sorted(pairs["1:1.5"].index))
    f = book(days).join(tape(days))
    for c in ["prints", "contracts", "avg_sz", "absdelta"]:
        f[c + "_rel"] = rel(f[c])
    buf, out = io.StringIO(), []
    for name, col in FILTERS:
        edges, labs = bins_of(f[col])
        with contextlib.redirect_stdout(buf):
            P.table(name, col, edges, labs, f, pairs)
            print("   cutoffs:", ", ".join(f"{x:.3g}" for x in edges[1:-1]), f"({int(f[col].notna().sum())} days with data)")
        out.append((name, summary(name, col, edges, labs, f, pairs)))
    (HERE / "two_account_filters_more.md").write_text("# Two accounts at 9:30, 2 NQ, 50-pt stop: more book / tape filters (in-sample)\n" + buf.getvalue())
    for name, rows in out:
        print("\n" + name)
        for r in rows:
            print(f"  {r[0]:12s} {r[1]} {r[2]:4d}d  >=1 {r[3]:3.0f}%  avg/day {r[4]:+7.0f}  avg/wk {r[5]:+6.0f}  green yrs {r[6]}/{r[7]}")


if __name__ == "__main__":
    main()

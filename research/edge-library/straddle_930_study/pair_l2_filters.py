"""Level-2 filters for the two-account 9:30 test (2 NQ, 50-pt stop), in-sample days only.

Data: the OFB vendor 1-minute book table (engine/cache/l2feat_NQ_*.parquet, built by l2data.py / bpfeat.py; ends 2026-07-07).
A row stamped minute M is the book ~59 s into M, usable from M + 60 s: rows 09:20..09:29 are all known at 09:30:00.
Rows with book_ok False are dropped. Only the 943 in-sample days are kept (the test-months rows in the files are never read out).
L1 depth: top-10 depth both sides at 09:29 vs the 20-session same-minute median (depth10_rel20d)
L2 imbalance: mean |imb10| over 09:20-09:29 (direction-free: one account is long, one short)
L4 pulled: vendor pulled-order count (bid + ask) 09:20-09:29 vs the prior 20 in-sample days (research tier: not reproducible live)
Usage: python straddle_930_study/pair_l2_filters.py
"""
from __future__ import annotations

import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pair_filters as P  # noqa: E402

COLS = ["t_utc", "date", "book_ok", "depth10_rel20d", "imb10", "rt_pulled_bid", "rt_pulled_ask"]


def features(days):
    files = sorted(glob.glob(str(HERE.parent / "engine/cache/l2feat_NQ_*.parquet")))
    df = pd.concat([pd.read_parquet(f, columns=COLS) for f in files], ignore_index=True)
    df["date"] = df["date"].astype(str)
    df = df[df.date.isin(set(days)) & df.book_ok.astype(bool)].drop_duplicates("t_utc")
    hm = pd.to_datetime(df.t_utc, unit="s", utc=True).dt.tz_convert("America/New_York").dt.strftime("%H:%M")
    w = df[(hm >= "09:20") & (hm <= "09:29")].assign(hm=hm)
    g = w.groupby("date")
    f = pd.DataFrame({
        "depth_rel": w[w.hm == "09:29"].set_index("date").depth10_rel20d,
        "imb": g.imb10.apply(lambda s: s.abs().mean()),
        "pulled": g.rt_pulled_bid.sum() + g.rt_pulled_ask.sum(),
        "rows": g.size(),
    }).reindex(days)
    f.loc[f.rows < 8, ["imb", "pulled"]] = np.nan            # need most of the 10 minutes
    f["pulled_rel"] = f.pulled / f.pulled.rolling(20, min_periods=10).mean().shift(1)
    return f


def main():
    pairs = P.paired()
    days = list(sorted(pairs["1:1.5"].index))
    f = features(days)
    print("days", len(days), "with depth", int(f.depth_rel.notna().sum()), "with imbalance", int(f.imb.notna().sum()),
          "with pulled", int(f.pulled_rel.notna().sum()), "last book day", f.rows.last_valid_index())
    q = lambda s: [-np.inf] + list(s.quantile([.2, .4, .6, .8]).values) + [np.inf]
    lab = ["lowest 20%", "20-40%", "40-60%", "60-80%", "highest 20%"]
    for name, col, fmt in [("L1. Book depth (top 10) at 09:29 vs 20-session median (−19% = thinner)", "depth_rel", "{:+.0%}"),
                           ("L2. Book imbalance |imb10|, mean 09:20-09:29", "imb", "{:.3f}"),
                           ("L4. Pulled orders 09:20-09:29 vs 20-day avg (vendor, research tier)", "pulled_rel", "{:.2f}x")]:
        cuts = q(f[col].dropna())
        P.table(name, col, cuts, lab, f, pairs)
        print("   cutoffs:", ", ".join(fmt.format(x) for x in cuts[1:-1]))


if __name__ == "__main__":
    main()

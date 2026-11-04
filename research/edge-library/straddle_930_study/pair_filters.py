"""Two accounts at 9:30 (one long, one short), 2 NQ, 50-pt stop: bucket the paired days by filters known at 9:30.

Reads the saved tester runs (draft_nq_930_side) and barstore 1m bars (3:1 in-sample months only).
Rolling averages use the prior in-sample days only, so after a skipped test month they reach back across it.
Usage: python straddle_930_study/pair_filters.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))
import barstore as B  # noqa: E402

RUNS = Path(__file__).resolve().parents[3] / "homebase/.state/tester/runs"
SETS = {"1:1.5": ("151000", "c796", "59e3"), "1:2": ("151019", "90c7", "ca6c"),
        "1:3": ("151043", "0424", "00e7"), "1:4": ("151111", "0741", "33ba")}


def paired():
    out = {}
    for rr, (t, lk, sk) in SETS.items():
        L, S = ({x["date"]: x["net"] for x in json.load(open(RUNS / f"20261101-{t}-draft_nq_930_side-{k}/trades.json"))}
                for k in (lk, sk))
        out[rr] = pd.DataFrame({"l": L, "s": S})
    return out


def features():
    df = B.load("NQ", "1m")
    et = pd.to_datetime(df.t, utc=True).dt.tz_convert("America/New_York")
    hm = et.dt.strftime("%H:%M")
    df = df.assign(hm=hm)
    g = df.groupby("session")
    day = pd.DataFrame({"h": g.h.max(), "l": g.l.min(), "c": g.c.last()})
    day["open930"] = df[df.hm == "09:30"].groupby("session").o.first()
    day["close1559"] = df[df.hm < "16:00"].groupby("session").c.last()
    day["pmvol"] = df[(df.hm >= "08:30") & (df.hm < "09:30")].groupby("session").v.sum()
    day = day.sort_index()
    # prior in-sample session's values (the session before may be a skipped test month: then this reaches across it)
    prev_c = day.c.shift(1)
    tr = np.maximum(day.h, prev_c) - np.minimum(day.l, prev_c)
    day["atr14"] = tr.rolling(14).mean().shift(1)            # known at 9:30: yesterday's ATR
    day["gap"] = day.open930 - day.close1559.shift(1)
    day["gap_atr"] = day.gap.abs() / day.atr14
    day["pm_rel"] = day.pmvol / day.pmvol.rolling(20).mean().shift(1)
    day["atr_rank"] = day.atr14.rolling(60, min_periods=20).apply(lambda a: (a[:-1] < a[-1]).mean(), raw=True)
    # skip gaps across a test month: prior session must be within 5 calendar days
    idx = pd.to_datetime(day.index)
    near = (idx.to_series().diff().dt.days <= 5).values
    day.loc[~near, ["gap", "gap_atr"]] = np.nan
    return day


def weeks(days) -> int:
    """In-sample trading weeks (distinct ISO weeks among the days)."""
    return len({d.isocalendar()[:2] for d in pd.to_datetime(pd.Index(days))})


def money(v):
    return ("+" if v > 0 else "−" if v < 0 else "") + f"${abs(v):,.0f}"


def section(title, cut, labels, pairs, days):
    """One table: every bucket x RR on `days` only; Days/wk and Avg/week over those days' in-sample weeks."""
    wk = weeks(days)
    print(f"\n#### {title} ({len(days)} days, {wk} weeks)\n| Bucket | RR | Days | Days/wk | ≥1 wins | Both lose | Net | Avg/day | Avg/week |")
    print("|---|---|---|---|---|---|---|---|---|")
    for lab in labels:
        ds = cut[cut == lab].index.intersection(days)
        for rr, p in pairs.items():
            q = p.loc[p.index.intersection(ds)]
            if not len(q):
                print(f"| {lab} | {rr} | 0 | 0.0 | - | - | - | - | - |")
                continue
            c = q.l + q.s
            one = ((q.l > 0) | (q.s > 0)).mean() * 100
            print(f"| {lab} | {rr} | {len(q)} | {len(q) / wk:.1f} | {one:.0f}% | {100 - one:.0f}% | {money(c.sum())} | "
                  f"{money(c.mean())} | {money(c.sum() / wk)} |")


def table(name, col, bins, labels, day, pairs):
    """All years combined, then one section per year."""
    print(f"\n### {name}")
    cut = pd.cut(day[col], bins, labels=labels)
    days = next(iter(pairs.values())).index
    section("All years", cut, labels, pairs, days)
    for y in sorted({d[:4] for d in days}):
        section(y, cut, labels, pairs, days[days.str[:4] == y])


def main():
    pairs, day = paired(), features()
    base = pairs["1:1.5"].index
    day = day.reindex(base)
    print("days", len(base), "missing gap", int(day.gap.isna().sum()), "missing pm", int(day.pm_rel.isna().sum()),
          "missing atr", int(day.atr14.isna().sum()))
    table("All days", "atr14", [-np.inf, np.inf], ["all"], day.fillna({"atr14": 1}), pairs)
    table("1. Gap size (|gap| / daily ATR)", "gap_atr", [0, .1, .25, .5, np.inf],
          ["< 0.10 ATR", "0.10-0.25", "0.25-0.50", "> 0.50 ATR"], day, pairs)
    table("4. Premarket volume 08:30-09:29 vs 20-day avg", "pm_rel", [0, .75, 1, 1.25, 1.75, np.inf],
          ["< 0.75x", "0.75-1x", "1-1.25x", "1.25-1.75x", "> 1.75x"], day, pairs)
    table("5a. Daily ATR(14) in points", "atr14", [0, 200, 300, 400, np.inf],
          ["< 200", "200-300", "300-400", "> 400"], day, pairs)
    table("5b. Daily ATR rank vs last 60 days", "atr_rank", [-.01, 1 / 3, 2 / 3, 1.01],
          ["low third", "middle", "high third"], day, pairs)


if __name__ == "__main__":
    main()

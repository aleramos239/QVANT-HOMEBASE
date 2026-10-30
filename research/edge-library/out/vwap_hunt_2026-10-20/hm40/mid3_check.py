"""Amendment M's in-sample check of the middle-third skip (PREREG_HM40.md): every NQ New York store on file, every box, the hunt's reader.
A MIDDLE day = the 09:30 open in the middle third of the 01:00-09:30 ET range (onr_orb.read_bias). Writes MID3_CHECK.md + mid3_check.csv.
In-sample months only (the stores' is/ trades); the day tags come from ~/futures_1m/NQ_1m.csv (front month). Nothing is picked here."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
EL = HERE.parents[2]
sys.path[:0] = [str(EL), str(EL / "engine")]
os.environ.setdefault("HOMEBASE_WF_LAST", "2026-05")
import library as LB  # noqa: E402
from blueprint import runner as RUN  # noqa: E402

NY = [LB.SESS_CODE[s] for s in ("nyam", "mid", "pm")]
HALF = "2024-01-01"


def middle_days(root="NQ") -> dict:
    """{ordinal: True/False}: the date's 09:30 open in the middle third of its 01:00-09:30 range (onr_orb.read_bias == 0 with a range)."""
    df = pd.read_csv(Path.home() / f"futures_1m/{root}_1m.csv", usecols=["ts_event", "open", "high", "low"])
    t = pd.to_datetime(df["ts_event"], utc=True).dt.tz_convert("America/New_York")
    df["d"], df["m"] = t.dt.date, t.dt.hour * 60 + t.dt.minute
    ov = df[(df.m >= 60) & (df.m < 570)].groupby("d").agg(hi=("high", "max"), lo=("low", "min"))
    op = df[(df.m >= 570) & (df.m <= 575)].groupby("d")["open"].first()      # the first bar from 09:30, at most 5 minutes late
    b = ov.join(op.rename("o"), how="inner")
    th = (b.hi - b.lo) / 3
    mid = (b.hi > b.lo) & (b.o >= b.lo + th) & (b.o <= b.lo + 2 * th)
    return {d.toordinal(): bool(x) for d, x in zip(b.index, mid)}


def main() -> None:
    M = middle_days()
    rows = []
    for sp in sorted((HERE / "specs").glob("*.json")):
        s = json.loads(sp.read_text())
        if s["markets"][0] != "NQ" or not set(s["sessions"]) & {"nyam", "mid", "pm"}:
            continue
        home = RUN.RUNS_WF / f"{s['name']}-NQ-tf{s['bar_sizes'][0]}"
        if not (home / "is" / "cells.npz").exists():
            continue
        u = LB.load_unit("is", home)
        for i, c in enumerate(u["meta"]["cells"]):
            x = LB.unit_cell(u, i)
            k = np.isin(np.asarray(x["sess"]), NY)
            net, date = np.asarray(x["net"], float)[k], np.asarray(x["date"])[k]
            if len(net) < 50:
                continue
            tag = np.array([M.get(int(d)) for d in date], dtype=object)
            known = tag != None  # noqa: E711
            net, date, tag = net[known], date[known], tag[known].astype(bool)
            iso = np.array([pd.Timestamp.fromordinal(int(d)).strftime("%Y-%m-%d") for d in date])
            r = {"store": home.name, "idea": int(s["name"].split("_")[1][1:]), "cell": c["id"], "n": len(net), "share_mid": tag.mean(),
                 "avg_mid": net[tag].mean() if tag.any() else np.nan, "avg_other": net[~tag].mean() if (~tag).any() else np.nan}
            for name, sel in (("h1", iso < HALF), ("h2", iso >= HALF)):
                m, o = tag & sel, ~tag & sel
                r[f"{name}_mid"], r[f"{name}_other"] = (net[m].mean() if m.any() else np.nan), (net[o].mean() if o.any() else np.nan)
            for y in range(2021, 2027):
                sel = np.char.startswith(iso.astype(str), str(y))
                m, o = tag & sel, ~tag & sel
                r[f"y{y}"] = (net[o].mean() - net[m].mean()) if m.sum() >= 5 and o.sum() >= 5 else np.nan
            rows.append(r)
    D = pd.DataFrame(rows)
    D.to_csv(HERE / "mid3_check.csv", index=False)
    g = D.groupby("store").agg(cells=("cell", "size"), n=("n", "mean"), share_mid=("share_mid", "mean"), avg_mid=("avg_mid", "mean"),
                               avg_other=("avg_other", "mean"), h1_mid=("h1_mid", "mean"), h1_other=("h1_other", "mean"),
                               h2_mid=("h2_mid", "mean"), h2_other=("h2_other", "mean"),
                               **{f"y{y}": (f"y{y}", "mean") for y in range(2021, 2027)})
    g["holds"] = g.avg_other > g.avg_mid
    g["holds_h1"], g["holds_h2"] = g.h1_other > g.h1_mid, g.h2_other > g.h2_mid
    ns = len(g)
    yrs = {y: int((g[f"y{y}"] > 0).sum()) for y in range(2021, 2027)}
    L = ["# The middle-third skip: in-sample check (Amendment M; every NQ New York store, every box; nothing picked here)", "",
         f"{ns} stores, {len(D)} boxes. A middle day = the 09:30 open in the middle third of the 01:00-09:30 range. Averages = the average box of each store.", "",
         "| Test (expected, written first) | Result |", "|---|---|",
         f"| Holds (other > middle) in >= 70 % of stores, all months | {int(g.holds.sum())} of {ns} ({g.holds.mean() * 100:.0f} %) |",
         f"| ... in the first half (2021-10..2023-12) | {int(g.holds_h1.sum())} of {ns} ({g.holds_h1.mean() * 100:.0f} %) |",
         f"| ... in the second half (2024-01..2026-04) | {int(g.holds_h2.sum())} of {ns} ({g.holds_h2.mean() * 100:.0f} %) |",
         f"| Holds in >= 4 of the 5 full years (stores where other - middle > 0, by year) | " +
         ", ".join(f"{y}: {yrs[y]}/{int(g[f'y{y}'].notna().sum())}" for y in range(2021, 2027)) + " |",
         f"| Share of trades on middle days (mean over stores) | {g.share_mid.mean() * 100:.0f} % |",
         f"| Average trade, middle vs other days (mean over stores) | ${g.avg_mid.mean():,.1f} vs ${g.avg_other.mean():,.1f} |",
         f"| First half, middle vs other | ${g.h1_mid.mean():,.1f} vs ${g.h1_other.mean():,.1f} |",
         f"| Second half, middle vs other | ${g.h2_mid.mean():,.1f} vs ${g.h2_other.mean():,.1f} |", "",
         "## Per store", "", "| Store | Boxes | Middle share | Avg middle | Avg other | H1 mid / other | H2 mid / other | Holds all / H1 / H2 |",
         "|---|---|---|---|---|---|---|---|"]
    for st, r in g.sort_values("avg_other", ascending=False).iterrows():
        L.append(f"| {st} | {r.cells} | {r.share_mid * 100:.0f} % | {r.avg_mid:,.0f} | {r.avg_other:,.0f} | {r.h1_mid:,.0f} / {r.h1_other:,.0f} | "
                 f"{r.h2_mid:,.0f} / {r.h2_other:,.0f} | {'Y' if r.holds else 'n'} / {'Y' if r.holds_h1 else 'n'} / {'Y' if r.holds_h2 else 'n'} |")
    (HERE / "MID3_CHECK.md").write_text("\n".join(L) + "\n")
    print("\n".join(L[:14]))


if __name__ == "__main__":
    main()

"""Note N's day-type study (PREREG_HM40.md): every NQ New York store on file, every box with >= 50 NY trades, in-sample months only (the
stores' is/ trades), the hunt's reader (as onr_side_study.py / mid3_check.py). Four DAY features known by 09:30 ET, each cut in thirds over
the in-sample days; the average box of each store on each third, by halves (2021-10..2023-12 vs 2024-01..2026-04). Day tags from
~/futures_1m/NQ_1m.csv (front month, ET). Writes DAYTYPE_STUDY.md + daytype_study.csv. Nothing is picked here."""
from __future__ import annotations

import datetime as dt
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
HALF = dt.date(2024, 1, 1).toordinal()
BAR = 0.70                                              # Note N: a lead holds in >= 70 % of stores in BOTH halves
# feature -> (what it is, the names of its three thirds). "pos" is already 0/1/2 (the middle-third definition); the rest are tertiles.
FEATS = {"onr": ("overnight range (01:00-09:30) / 20-day daily range", ("small", "mid", "big")),
         "gap": ("09:30 open - prior session's 16:00 close, / 20-day daily range (signed)", ("down", "flat", "up")),
         "gap_abs": ("|gap| / 20-day daily range", ("small", "mid", "big")),
         "drift": ("09:30 open - 18:00 open the evening before, / 20-day daily range (signed)", ("down", "flat", "up")),
         "drift_abs": ("|drift| / 20-day daily range", ("small", "mid", "big")),
         "pos": ("the 09:30 open's place in the 01:00-09:30 range (the middle-third definition)", ("bottom", "middle", "top"))}


def day_table(root="NQ") -> pd.DataFrame:
    """One row per RTH date (ET, keyed by ordinal): the raw day features, before the thirds."""
    df = pd.read_csv(Path.home() / f"futures_1m/{root}_1m.csv", usecols=["ts_event", "open", "high", "low", "close"])
    t = pd.to_datetime(df["ts_event"], utc=True).dt.tz_convert("America/New_York")
    df["d"], df["m"] = t.dt.date, t.dt.hour * 60 + t.dt.minute
    df["td"] = (t + pd.Timedelta(hours=6)).dt.date                              # the trade date: 18:00 the evening before -> 17:00
    ov = df[(df.m >= 60) & (df.m < 570)].groupby("d").agg(hi=("high", "max"), lo=("low", "min"))
    op = df[(df.m >= 570) & (df.m <= 575)].groupby("d")["open"].first()          # the first bar from 09:30, at most 5 minutes late
    c16 = df[(df.m >= 930) & (df.m < 960)].groupby("d")["close"].last()          # the last bar before 16:00, at most 30 minutes early
    o18 = df[(df.m >= 1080) & (df.m <= 1085)].groupby("td")["open"].first()      # 18:00 the evening before, at most 5 minutes late
    rng = df.groupby("td").agg(hi=("high", "max"), lo=("low", "min"))
    avg20 = (rng.hi - rng.lo).shift(1).rolling(20).mean()                          # the 20 prior trade dates only
    b = ov.join(op.rename("o"), how="inner")
    b["pc"] = c16.reindex(op.index).shift(1).reindex(b.index)                     # the previous RTH date's 16:00 close
    b["o18"], b["avg20"] = o18.reindex(b.index), avg20.reindex(b.index)
    th = (b.hi - b.lo) / 3
    b["pos"] = np.where(b.hi <= b.lo, np.nan, np.where(b.o > b.lo + 2 * th, 2, np.where(b.o < b.lo + th, 0, 1)))
    b["onr"] = (b.hi - b.lo) / b.avg20
    b["gap"], b["drift"] = (b.o - b.pc) / b.avg20, (b.o - b.o18) / b.avg20
    b["gap_abs"], b["drift_abs"] = b.gap.abs(), b.drift.abs()
    b.index = [d.toordinal() for d in b.index]
    return b


def load_boxes() -> list:
    """[(store, idea, cell, net, date)] for every NQ New York store's box with >= 50 NY in-sample trades."""
    boxes = []
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
            net, date = np.asarray(x["net"], float)[k], np.asarray(x["date"]).astype(int)[k]
            if len(net) < 50:
                continue
            boxes.append((home.name, int(s["name"].split("_")[1][1:]), c["id"], net, date))
    return boxes


def main() -> None:
    B, boxes = day_table(), load_boxes()
    is_days = np.unique(np.concatenate([d for *_, d in boxes]))                   # the in-sample days: the thirds are cut on these only
    T, cuts = pd.DataFrame(index=B.index), {}
    for f in FEATS:
        if f == "pos":
            T[f] = B.pos
            continue
        q1, q2 = np.nanpercentile(B[f].reindex(is_days).dropna(), [100 / 3, 200 / 3])
        cuts[f] = (q1, q2)
        T[f] = np.where(B[f].isna(), np.nan, np.where(B[f] <= q1, 0, np.where(B[f] <= q2, 1, 2)))
    rows = []
    for store, idea, cell, net, date in boxes:
        h1, tags = date < HALF, T.reindex(date)
        r = {"store": store, "idea": idea, "cell": cell, "n": len(net), "avg_all": net.mean()}
        for f in FEATS:
            tg = tags[f].to_numpy()
            known = ~np.isnan(tg)
            r[f"{f}_known"] = known.mean()
            for t in range(3):
                m = known & (tg == t)
                r[f"{f}_share{t}"] = m.sum() / max(known.sum(), 1)
                for nm, sel in (("avg", known), ("h1", h1), ("h2", ~h1)):
                    mm = m & sel
                    r[f"{f}_{nm}{t}"] = net[mm].mean() if mm.any() else np.nan
        rows.append(r)
    D = pd.DataFrame(rows)
    D.to_csv(HERE / "daytype_study.csv", index=False)
    # self-check: the "pos" middle share is the middle-third skip's share_mid, box for box (mid3_check.csv, same definition)
    m3 = HERE / "mid3_check.csv"
    if m3.exists():
        chk = D.merge(pd.read_csv(m3, usecols=["store", "cell", "share_mid"]), on=["store", "cell"])
        gap = (chk.pos_share1 - chk.share_mid).abs().max()
        assert len(chk) == len(D) and gap < 1e-9, f"pos thirds differ from mid3_check: {len(chk)}/{len(D)} boxes, max gap {gap}"
    g = D.groupby("store").mean(numeric_only=True)
    g["cells"] = D.groupby("store").size()
    ns, nb = len(g), len(D)
    S, per_store = [], {}
    for f, (desc, names) in FEATS.items():
        a = [g[f"{f}_avg{t}"].mean() for t in range(3)]                           # mean over stores of the store's average box
        best, worst = int(np.nanargmax(a)), int(np.nanargmin(a))
        a1 = [g[f"{f}_h1{t}"].mean() for t in range(3)]
        b1, w1 = int(np.nanargmax(a1)), int(np.nanargmin(a1))                     # the thirds chosen on the first half alone
        h = pd.DataFrame({"all": g[f"{f}_avg{best}"] > g[f"{f}_avg{worst}"], "h1": g[f"{f}_h1{best}"] > g[f"{f}_h1{worst}"],
                          "h2": g[f"{f}_h2{best}"] > g[f"{f}_h2{worst}"], "h2_strict": g[f"{f}_h2{b1}"] > g[f"{f}_h2{w1}"]})
        per_store[f] = h
        bps = g[[f"{f}_avg{t}" for t in range(3)]].fillna(-np.inf).to_numpy().argmax(1)
        lead = h.h1.mean() >= BAR and h.h2.mean() >= BAR
        S.append({"f": f, "desc": desc, "names": names, "best": best, "worst": worst, "b1": b1, "w1": w1, "a": a, "lead": lead,
                  "h1": [g[f"{f}_h1{t}"].mean() for t in range(3)], "h2": [g[f"{f}_h2{t}"].mean() for t in range(3)],
                  "share": [g[f"{f}_share{t}"].mean() for t in range(3)], "known": g[f"{f}_known"].mean(),
                  "nbest": [int((bps == t).sum()) for t in range(3)], "holds": {k: int(h[k].sum()) for k in h}})
    leads = [s for s in S if s["lead"]]
    noise = [s for s in S if not s["lead"]]
    P = lambda n: f"{n} of {ns} ({n / ns * 100:.0f} %)"  # noqa: E731
    L = ["# The day-type study: in-sample check (Note N; every NQ New York store, every box; nothing picked here)", "",
         f"{ns} stores, {nb} boxes (>= 50 NY in-sample trades each), {len(is_days)} in-sample days. Each feature is known by 09:30 ET of the trade "
         "date and cut in thirds over the in-sample days (tertiles; the open's place in the range keeps the middle-third definition). "
         "Averages = the average box of each store, $ a trade. Halves: H1 = 2021-10..2023-12, H2 = 2024-01..2026-04. "
         "'Holds' = the store's best third (chosen on all months, over all stores) beats its worst; the strict column chooses the thirds on H1 "
         "alone and reads H2. Day tags from ~/futures_1m/NQ_1m.csv (front month; may differ from the engine's contract on roll days).", "",
         "## The answer", "",
         "**Leads** (hold in >= 70 % of stores in BOTH halves): " + (", ".join(f"{s['f']} ({s['names'][s['best']]} beats {s['names'][s['worst']]})"
                                                                               for s in leads) if leads else "none") + ".  ",
         "**Noise**: " + (", ".join(s["f"] for s in noise) if noise else "none") + ".  ",
         "A lead found in-sample proves nothing in-sample (Note N): it is not applied to any stack; it may become a day tag in STACK_REPORT.md "
         "with its own written forward bar, read once at the stacks' read dates.", "",
         "## Verdicts against Note N's EXPECTED line (written before the run)", "",
         "| Feature | Best third | Worst third | Holds, all months | H1 | H2 | H2, thirds chosen on H1 | Verdict |", "|---|---|---|---|---|---|---|---|"]
    for s in S:
        h = s["holds"]
        L.append(f"| {s['f']} | {s['names'][s['best']]} (${s['a'][s['best']]:,.1f}) | {s['names'][s['worst']]} (${s['a'][s['worst']]:,.1f}) | "
                 f"{P(h['all'])} | {P(h['h1'])} | {P(h['h2'])} | {s['names'][s['b1']]} vs {s['names'][s['w1']]}: {P(h['h2_strict'])} | "
                 f"{'LEAD' if s['lead'] else 'noise'} |")
    L += ["", "## Per feature", ""]
    for i, s in enumerate(S, 1):
        f, names = s["f"], s["names"]
        cut = (f"Cuts (units of the 20-day daily range): {names[0]} <= {cuts[f][0]:.3f}, {names[1]} to {cuts[f][1]:.3f}, {names[2]} above."
               if f in cuts else "Cuts: the open below the bottom third / inside the middle third / above the top third of the range.")
        L += [f"### {i}. {f}: {s['desc']}", "", cut + f" Tagged trades: {s['known'] * 100:.0f} %.", "",
              "| Third | Share of trades | Avg all | Avg H1 | Avg H2 | Stores where it is the best third |", "|---|---|---|---|---|---|"]
        for t in range(3):
            L.append(f"| {names[t]} | {s['share'][t] * 100:.0f} % | ${s['a'][t]:,.1f} | ${s['h1'][t]:,.1f} | ${s['h2'][t]:,.1f} | {s['nbest'][t]} |")
        h = s["holds"]
        L += ["", f"{names[s['best']]} beats {names[s['worst']]} in {P(h['all'])} of stores (all months), {P(h['h1'])} in H1, {P(h['h2'])} in H2. "
              f"Thirds chosen on H1 alone ({names[s['b1']]} vs {names[s['w1']]}): hold in H2 in {P(h['h2_strict'])}. "
              f"**Verdict: {'LEAD' if s['lead'] else 'noise'}** (the bar: >= 70 % in both halves).", ""]
    L += ["## Per store", "", "Y / n = holds (best third beats worst, the thirds above) on all months / H1 / H2.", "",
          "| Store | Boxes | " + " | ".join(S_["f"] for S_ in S) + " |", "|---|---|" + "---|" * len(S)]
    for st, r in g.sort_values("avg_all", ascending=False).iterrows():
        flags = [" / ".join("Y" if per_store[s["f"]].loc[st, k] else "n" for k in ("all", "h1", "h2")) for s in S]
        L.append(f"| {st} | {int(r.cells)} | " + " | ".join(flags) + " |")
    L += ["", "## Per store, the average box on each third ($ a trade; all months, then H1 / H2)", ""]
    for s in S:
        f, names = s["f"], s["names"]
        L += [f"### {f}", "", "| Store | " + " | ".join(names) + " | H1 " + " / ".join(names) + " | H2 " + " / ".join(names) + " |", "|---|---|---|---|---|---|"]
        for st, r in g.sort_values("avg_all", ascending=False).iterrows():
            L.append(f"| {st} | " + " | ".join(f"{r[f'{f}_avg{t}']:,.0f}" for t in range(3)) + " | " +
                     " / ".join(f"{r[f'{f}_h1{t}']:,.0f}" for t in range(3)) + " | " + " / ".join(f"{r[f'{f}_h2{t}']:,.0f}" for t in range(3)) + " |")
    (HERE / "DAYTYPE_STUDY.md").write_text("\n".join(L) + "\n")
    print("\n".join(L[:20 + len(S)]))


if __name__ == "__main__":
    main()

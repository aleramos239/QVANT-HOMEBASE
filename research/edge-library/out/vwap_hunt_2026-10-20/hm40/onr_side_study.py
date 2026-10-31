"""In-sample filter study (no backtest): split every NQ / ES hunt store's NY-group in-sample trades by the day's overnight-third side
(onr_orb's bias: the 09:30 open in the top / bottom third of the 01:00-09:30 ET range -> +1 / -1, else 0). Question fixed before looking:
does a trade WITH the side win more often than one AGAINST it, at the same exit cell, broadly across stores (average of all boxes)?
Bias from ~/futures_1m (front month; may differ from the engine's contract on roll days)."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
EL = Path("/Users/ramoscapital/ramos-quant-homebase/research/edge-library")
sys.path.insert(0, str(EL)); sys.path.insert(0, str(EL / "engine"))
import library as LB
from blueprint import runner as RUN
HM = EL / "out/vwap_hunt_2026-10-20/hm40"
NYC = [LB.SESS_CODE[s] for s in ("nyam", "mid", "pm")]

def bias_table(root):
    df = pd.read_csv(Path.home() / f"futures_1m/{root}_1m.csv", usecols=["ts_event", "open", "high", "low"])
    t = pd.to_datetime(df["ts_event"], utc=True).dt.tz_convert("America/New_York")
    df["d"] = t.dt.date; df["m"] = t.dt.hour * 60 + t.dt.minute
    ov = df[(df.m >= 60) & (df.m < 570)].groupby("d").agg(hi=("high", "max"), lo=("low", "min"))
    op = df[(df.m >= 570) & (df.m <= 575)].groupby("d")["open"].first()
    b = ov.join(op.rename("o"), how="inner")
    th = (b.hi - b.lo) / 3
    bias = np.where(b.hi <= b.lo, 0, np.where(b.o > b.lo + 2 * th, 1, np.where(b.o < b.lo + th, -1, 0)))
    return {d.toordinal(): int(x) for d, x in zip(b.index, bias)}

out = []
for root in ("NQ", "ES"):
    B = bias_table(root)
    for sp in sorted(HM.glob("specs/*.json")):
        s = json.loads(sp.read_text())
        if s["markets"][0] != root or not set(s["sessions"]) & {"nyam", "mid", "pm"}:
            continue
        home = RUN.RUNS_WF / f"{s['name']}-{root}-tf{s['bar_sizes'][0]}"
        if not (home / "is" / "cells.npz").exists():
            continue
        u = LB.load_unit("is", home)
        for i, c in enumerate(u["meta"]["cells"]):
            x = LB.unit_cell(u, i)
            k = np.isin(np.asarray(x["sess"]), NYC)
            net, side, date = np.asarray(x["net"], float)[k], np.asarray(x["side"])[k], np.asarray(x["date"])[k]
            if len(net) < 50:
                continue
            bb = np.array([B.get(int(d), 0) for d in date])
            w, a, z = (bb != 0) & (side == bb), (bb != 0) & (side == -bb), bb == 0
            row = {"store": s["name"], "root": root, "idea": int(s["name"].split("_")[1][1:]), "cell": c["id"], "n": len(net),
                   "win_all": (net > 0).mean(), "avg_all": net.mean()}
            for nm, m in (("with", w), ("against", a), ("mid", z)):
                row[f"n_{nm}"] = int(m.sum()); row[f"win_{nm}"] = (net[m] > 0).mean() if m.any() else np.nan
                row[f"avg_{nm}"] = net[m].mean() if m.any() else np.nan
            out.append(row)
D = pd.DataFrame(out)
D.to_csv(Path(sys.argv[1]) / "onr_side_study.csv", index=False)
D["dwin"] = (D.win_with - D.win_against) * 100; D["davg"] = D.avg_with - D.avg_against
D["dwin_all"] = (D.win_with - D.win_all) * 100; D["share_with"] = D.n_with / D.n
g = D.groupby(["root", "store"]).agg(cells=("cell", "size"), share_with=("share_with", "mean"), dwin=("dwin", "mean"), davg=("davg", "mean"),
                                     dwin_vs_all=("dwin_all", "mean"), avg_all=("avg_all", "mean"), avg_with=("avg_with", "mean"))
pd.set_option("display.width", 220); pd.set_option("display.max_rows", 200)
print(g.round(2).sort_values("dwin"))
for r in ("NQ", "ES"):
    q = g.loc[r]
    print(r, "stores", len(q), "| with beats against in", int((q.dwin > 0).sum()), "| mean dwin %.2f pts, median %.2f | mean davg $%.1f | with vs all %.2f pts | share of trades with %.2f"
          % (q.dwin.mean(), q.dwin.median(), q.davg.mean(), q.dwin_vs_all.mean(), q.share_with.mean()))

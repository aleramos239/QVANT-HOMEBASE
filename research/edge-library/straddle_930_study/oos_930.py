"""Test months (3:1 blocks) for the two-account NQ 9:30 setup, 2 NQ, 50 / 100 (1:2), market orders:
every day vs the saved 4 filters (cutoffs frozen from in-sample, saved_4filters.json). Owner said run it, 2026-11-01.
Runs: draft_nq_930_side 2021-10-01 -> 2026-09-30 (16bd long, 20e3 short); only the out-of-sample months are scored here."""
import json, sys, warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import pandas as pd
from homebase.backtest.stats.stats import _sharpe
import pair_filters as P, pair_l2_filters as L2, pair_l2_more as LM
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import l2sim as S, barstore as B
from blueprint import wfmonths

def load(k):
    m = list(P.RUNS.glob(f"20261101-*-draft_nq_930_side-{k}")); assert len(m) == 1
    tr = json.load(open(m[0] / "trades.json"))
    return pd.DataFrame({x["date"]: (x["net"], x["exit_reason"] == "tp") for x in tr}, index=["net", "tp"]).T

L, Sh = load("16bd"), load("20e3")
full = pd.DataFrame({"l": L.net, "s": Sh.net, "a": L.tp, "b": Sh.tp}).dropna()
import datetime as dt
ins_s, oos_s = wfmonths._sets("NQ", dt.date.today().isoformat())
oos_m = sorted(oos_s & set(full.index.str[:7])); ins_m = sorted(ins_s & set(full.index.str[:7]))
oos = full[full.index.str[:7].isin(oos_m)]; ins = full[full.index.str[:7].isin(ins_m)]

# features with test-month bars added (ATR = yesterday's 14-day, so it reaches into the month before, as live would)
bars = [B.load("NQ", "1m", fresh=False)]
for m in oos_m:
    end = (pd.Period(m) .end_time).date().isoformat()
    bars.append(B.load("NQ", "1m", allow=S.ALLOW_WF_OOS, start=f"{m}-01", end=end, fresh=False))
allbars = pd.concat(bars).sort_values("t")
P.B.load = lambda root, tf: allbars
days = list(sorted(full.index))
f = L2.features(days)[["depth_rel"]].join(LM.book(days)[["top3_rel", "lvl_sz_rel"]]).join(P.features().reindex(days)[["atr14"]])
fire = (f.depth_rel >= 0.2127) | f.top3_rel.between(1.0345, 1.1855) | (f.lvl_sz_rel >= 1.2239) | f.atr14.between(200, 300)
print(f"test months: {', '.join(oos_m)} ({len(oos)} days); book data on {int(f.loc[oos.index].depth_rel.notna().sum())} of them, "
      f"last book day {f.depth_rel.last_valid_index()}")
print(f"in-sample check (should be 943 / 498): {len(ins)} / {int(fire.reindex(ins.index).sum())}\n")

def row(lab, q, wk):
    c = q.l + q.s; eq = c.cumsum(); y = c.groupby(c.index.str[:4]).sum()
    one = ((q.l > 0) | (q.s > 0)).mean() * 100; tp = (q.a.astype(bool) | q.b.astype(bool)).mean() * 100
    return (f"| {lab} | {len(q)} | {len(q)/wk:.1f} | {tp:.1f}% | {one:.1f}% | {P.money(c.sum())} | {P.money(c.mean())} | "
            f"{P.money(c.sum()/wk)} | {P.money((eq-eq.cummax()).min())} | {_sharpe(list(c)):.2f} | {(y>0).sum()}/{len(y)} |")

print("| Setup | Days | Days/wk | ≥1 hits full TP | ≥1 wins | Net | Avg/day | Avg/week | Max DD | Sharpe | Green years |\n|" + "---|" * 11)
for lab, q in [("Every day", None), ("4 filters", fire)]:
    for part, d in [("in-sample", ins), ("TEST MONTHS", oos)]:
        qq = d if q is None else d.loc[q.reindex(d.index).fillna(False).astype(bool)]
        print(row(f"{lab}, {part}", qq, P.weeks(d.index)))
print("\n### Test months, net by year\n| Setup | " + " | ".join(sorted(set(oos.index.str[:4]))) + " |\n|---|" + "---|" * len(set(oos.index.str[:4])))
for lab, q in [("Every day", oos), ("4 filters", oos.loc[fire.reindex(oos.index).fillna(False).astype(bool)])]:
    c = q.l + q.s; print(f"| {lab} | " + " | ".join(P.money(v) for v in c.groupby(c.index.str[:4]).sum()) + " |")
q = oos.loc[fire.reindex(oos.index).fillna(False).astype(bool)]; c = q.l + q.s
print("\n### Test months, 4 filters, by month\n| Month | Days | Net |\n|---|---|---|")
for m, g in c.groupby(c.index.str[:7]): print(f"| {m} | {len(g)} | {P.money(g.sum())} |")

"""Two accounts (one long, one short, market orders), 2 contracts, 1:2, in-sample, both accounts together:
gold CPI/NFP 08:29:59 (5 / 10 pts) | NQ CPI/NFP 08:29:59 (50 / 100) | NQ 9:30 every day (50 / 100) | NQ 9:30 with the saved 4 filters."""
import json, warnings; warnings.filterwarnings("ignore")
import pandas as pd
from homebase.backtest.stats.stats import _sharpe
import pair_filters as P, pair_l2_filters as L2, pair_l2_more as LM

def load(glob):
    m = list(P.RUNS.glob(glob)); assert len(m) == 1, glob
    tr = json.load(open(m[0] / "trades.json"))
    return pd.DataFrame({x["date"]: (x["net"], x["exit_reason"] == "tp") for x in tr}, index=["net", "tp"]).T

def pair(lg, sg):
    L, S = load(lg), load(sg)
    return pd.DataFrame({"l": L.net, "s": S.net, "a": L.tp, "b": S.tp})

gc = pair("20261101-*-draft_gc_news_side-f5bc", "20261101-*-draft_gc_news_side-1ae9")
nqn = pair("20261101-165328-draft_nq_news_side-a4fa", "20261101-165328-draft_nq_news_side-a8b4")
nq = pair("20261101-151019-draft_nq_930_side-90c7", "20261101-151019-draft_nq_930_side-ca6c")

# the saved 4 filters (saved_4filters.json): trade if ANY fires
days = list(sorted(nq.index))
f = L2.features(days)[["depth_rel"]].join(LM.book(days)[["top3_rel", "lvl_sz_rel"]]).join(P.features().reindex(days)[["atr14"]])
fire = (f.depth_rel >= 0.2127) | f.top3_rel.between(1.0345, 1.1855) | (f.lvl_sz_rel >= 1.2239) | f.atr14.between(200, 300)
nq4 = nq.loc[fire[fire].index]
assert len(nq4) == 498, len(nq4)

all_wk = P.weeks(nq.index)        # every in-sample week (202)
H = "| Setup | Days | Days/wk | ≥1 hits full TP | ≥1 wins | Both lose | Net | Avg/day | Avg/week | Max DD | Sharpe | Green years |"
print(H + "\n|" + "---|" * 12)
for lab, q in [("Gold, CPI/NFP days, 08:29:59", gc), ("NQ, CPI/NFP days, 08:29:59", nqn),
               ("NQ, every day, 09:30 (no filter)", nq), ("NQ, 09:30, 4 filters", nq4)]:
    c = q.l + q.s; eq = c.cumsum(); y = c.groupby(c.index.str[:4]).sum()
    one = ((q.l > 0) | (q.s > 0)).mean() * 100
    tp = (q.a.astype(bool) | q.b.astype(bool)).mean() * 100
    print(f"| {lab} | {len(q)} | {len(q)/all_wk:.1f} | {tp:.1f}% | {one:.1f}% | {100-one:.1f}% | {P.money(c.sum())} | {P.money(c.mean())} | "
          f"{P.money(c.sum()/all_wk)} | {P.money((eq-eq.cummax()).min())} | {_sharpe(list(c)):.2f} | {(y>0).sum()}/{len(y)} |")
print(f"\nPer week = over all {all_wk} in-sample weeks. Gold: 2 GC, 5-pt stop ($1,000) / 10-pt target. NQ: 2 NQ, 50-pt stop ($2,000) / 100-pt target.")

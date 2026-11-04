"""Gold (GC) CPI/NFP, two accounts (long / short), 2 GC, 5-pt stop, 10-pt target (1:2): market at 08:29:59 vs stop
entries 0.5-2.5 pts off the 08:29:59 print (NQ's 5-25 scaled by the ~0.1 GC/NQ daily-range ratio). In-sample only."""
import json, warnings; warnings.filterwarnings("ignore")
import pandas as pd
from homebase.backtest.stats.stats import _sharpe
import pair_filters as P

RUNS = {"Market": ("f5bc", "1ae9"), "Stop ±0.5": ("869e", "e544"), "Stop ±1": ("e5de", "88c5"), "Stop ±1.5": ("d47f", "460c"),
        "Stop ±2": ("a808", "dcdc"), "Stop ±2.5": ("5e0d", "5810")}

def side(k):
    m = list(P.RUNS.glob(f"20261101-*-draft_gc_news_side-{k}")); assert len(m) == 1, k
    tr = json.load(open(m[0] / "trades.json"))
    return pd.DataFrame({x["date"]: (x["net"], x["exit_reason"] == "tp") for x in tr}, index=["net", "tp"]).T, tr

days = side("f5bc")[0].index
months = len({d[:7] for d in days})
print(f"{len(days)} CPI/NFP days in-sample, {months} months\n")
print("| Entry | Days traded | ≥1 hits full TP | Both hit TP | ≥1 wins | Net | Avg/day | Max DD | Sharpe | Green years |\n|---|---|---|---|---|---|---|---|---|---|")
yr = {}
for lab, (l, s) in RUNS.items():
    (L, _), (S, _) = side(l), side(s)
    df = pd.DataFrame({"l": L.net, "s": S.net, "a": L.tp, "b": S.tp}).reindex(days)
    q = df[df.l.notna() | df.s.notna()].fillna({"l": 0, "s": 0, "a": False, "b": False})
    a, b = q.a.astype(bool), q.b.astype(bool)
    c = q.l + q.s; eq = c.cumsum(); y = c.groupby(c.index.str[:4]).sum(); yr[lab] = y
    print(f"| {lab} | {len(q)} | {(a|b).mean()*100:.1f}% | {(a&b).mean()*100:.1f}% | {((q.l>0)|(q.s>0)).mean()*100:.1f}% | "
          f"{P.money(c.sum())} | {P.money(c.mean())} | {P.money((eq-eq.cummax()).min())} | {_sharpe(list(c)):.2f} | {(y>0).sum()}/{len(y)} |")
print("\n### Net by year\n| Entry | " + " | ".join(yr["Market"].index) + " |\n|---|" + "---|" * len(yr["Market"]))
for lab, y in yr.items():
    print(f"| {lab} | " + " | ".join(P.money(v) for v in y) + " |")

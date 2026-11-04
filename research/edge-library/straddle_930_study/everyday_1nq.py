"""NQ 9:30 two accounts, 1 NQ each, $1,000 stop (50 pts), 1:2 (100 pts), market orders, every day. Saved for later (owner).
In-sample: runs bcc2 / 4b5a. Test months: the 2-NQ full-range runs 16bd / 20e3 halved (same trades; months already read 2026-11-01)."""
import json, datetime as dt, warnings; warnings.filterwarnings("ignore")
import pandas as pd
from homebase.backtest.stats.stats import _sharpe
import pair_filters as P
from blueprint import wfmonths

def load(k, scale=1.0):
    m = list(P.RUNS.glob(f"20261101-*-draft_nq_930_side-{k}")); assert len(m) == 1
    tr = json.load(open(m[0] / "trades.json"))
    return pd.DataFrame({x["date"]: (x["net"] * scale, x["exit_reason"] == "tp") for x in tr}, index=["net", "tp"]).T

ins_s, oos_s = wfmonths._sets("NQ", dt.date.today().isoformat())
ins = pd.DataFrame({"l": load("bcc2").net, "s": load("4b5a").net, "a": load("bcc2").tp, "b": load("4b5a").tp})
fl, fs = load("16bd", .5), load("20e3", .5)
oos = pd.DataFrame({"l": fl.net, "s": fs.net, "a": fl.tp, "b": fs.tp})
oos = oos[oos.index.str[:7].isin(oos_s)]

def row(lab, q):
    c = q.l + q.s; eq = c.cumsum(); y = c.groupby(c.index.str[:4]).sum(); wk = P.weeks(q.index)
    one = ((q.l > 0) | (q.s > 0)).mean() * 100; tp = (q.a.astype(bool) | q.b.astype(bool)).mean() * 100
    print(f"| {lab} | {len(q)} | {len(q)/wk:.1f} | {tp:.1f}% | {one:.1f}% | {100-one:.1f}% | {P.money(c.sum())} | {P.money(c.mean())} | "
          f"{P.money(c.sum()/wk)} | {P.money((eq-eq.cummax()).min())} | {_sharpe(list(c)):.2f} | {(y>0).sum()}/{len(y)} |")
    return y

print("| Part | Days | Days/wk | ≥1 hits full TP | ≥1 wins | Both lose | Net | Avg/day | Avg/week | Max DD | Sharpe | Green years |\n|" + "---|" * 12)
yi, yo = row("In-sample", ins), row("Test months", oos)
print("\n| Year | In-sample net | Test-months net |\n|---|---|---|")
for y in sorted(set(yi.index) | set(yo.index)):
    print(f"| {y} | {P.money(yi.get(y, 0))} | {P.money(yo.get(y, 0)) if y in yo else '-'} |")

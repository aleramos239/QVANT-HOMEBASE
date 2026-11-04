"""Owner's five groups (top 5 picked at 1:2 or 1:1.5: argv[1]), enter if one or more qualify."""
import contextlib, io, sys, warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from homebase.backtest.stats.stats import _sharpe
with contextlib.redirect_stdout(io.StringIO()):
    import beats_no_filter as B
P, pairs, days = B.P, B.pairs, B.days
SETS = {"1:2": ["L11 Contracts at the top 3 levels at: 60-80%", "T1 Premarket delta imbalance: 40-60%", "5a Daily ATR: 200-300",
        "L12 Spread: 20-40%", "L1 Book depth: highest 20%"],
        "1:1.5": ["L10 Size per price level (median) at: highest 20%", "L14 Icebergs: lowest 20%", "L1 Book depth: highest 20%",
                  "5a Daily ATR: 200-300", "T1 Premarket delta imbalance: 40-60%"]}
SETS["all4"] = ["L1 Book depth: highest 20%", "L11 Contracts at the top 3 levels at: 60-80%",
                 "L10 Size per price level (median) at: highest 20%", "5a Daily ATR: 200-300"]
PICK = sys.argv[1] if len(sys.argv) > 1 else "1:2"
FIVE = SETS[PICK]
ORDER = [r for r in ["1:1.5", "1:2", "1:3", "1:4"] if r != PICK] if PICK == "all4" else [PICK] + [r for r in ["1:1.5", "1:2", "1:3", "1:4"] if r != PICK]
m = pd.concat([B.groups[n].fillna(False).astype(bool) for n in FIVE], axis=1)
anyhit = m.any(axis=1)

def row(label, p, mask, wk):
    q = p.loc[mask[mask].index]; c = q.l + q.s; eq = c.cumsum(); one = ((q.l > 0) | (q.s > 0)).mean() * 100
    return (f"| {label} | {len(q)} | {len(q)/wk:.1f} | {one:.1f}% | {100-one:.1f}% | {P.money(c.sum())} | {P.money(c.mean())} | "
            f"{P.money((eq - eq.cummax()).min())} | {_sharpe(list(c)):.2f} | {P.money(c.sum()/wk)} |")

H = "| {} | Days | Days/wk | ≥1 wins | Both lose | Net | Avg/day | Max DD | Sharpe | Avg/week |\n|---|---|---|---|---|---|---|---|---|---|"
print("Days per hit count:", m.sum(axis=1).value_counts().sort_index().to_dict())
print("\n### All years\n" + H.format("Rule / RR"))
for rr in ORDER:
    wk = P.weeks(days)
    print(row(f"No filter {rr}", pairs[rr], pd.Series(True, index=days), wk))
    print(row(f"**Any hit hits {rr}**", pairs[rr], anyhit, wk))
idx = pd.Index(days)
for rr in ORDER:
    print(f"\n### By year, {rr}\n" + H.format("Year / rule"))
    for y in sorted({d[:4] for d in days}):
        yd = pd.Series(idx.str[:4] == y, index=days); wk = P.weeks(idx[yd.values])
        print(row(f"{y} no filter", pairs[rr], yd, wk))
        print(row(f"{y} any hit", pairs[rr], yd & anyhit, wk))

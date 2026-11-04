"""Enter only if at least one filter group that beat no filter (on 'at least one wins', at the chosen RR) is hit.
Groups come from beats_no_filter.py; 'Combo:' rows are left out (they are built from the same filters)."""
import contextlib, io, sys, warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from homebase.backtest.stats.stats import _sharpe
with contextlib.redirect_stdout(io.StringIO()):
    import beats_no_filter as B
P, pairs, days, wk = B.P, B.pairs, B.days, B.wk

def win_pct(p, m):
    q = p.loc[m[m].index]; return ((q.l > 0) | (q.s > 0)).mean() * 100, len(q)

def metrics(name, p, m):
    q = p.loc[m[m].index]; c = q.l + q.s; eq = c.cumsum(); y = c.groupby(c.index.str[:4]).sum()
    one = ((q.l > 0) | (q.s > 0)).mean() * 100
    return (f"| {name} | {len(q)} | {len(q)/wk:.1f} | {one:.1f}% | {100-one:.1f}% | {P.money(c.sum())} | {P.money(c.mean())} | "
            f"{P.money((eq - eq.cummax()).min())} | {_sharpe(list(c)):.2f} | {P.money(c.sum()/wk)} | {(y>0).sum()}/{len(y)} |")

masks = {n: m.fillna(False).astype(bool) for n, m in B.groups.items() if not n.startswith("Combo")}
everyday = pd.Series(True, index=days)
for pick in ["1:2", "1:1.5"]:
    base, _ = win_pct(pairs[pick], everyday)
    beat = sorted([(win_pct(pairs[pick], m)[0], n) for n, m in masks.items() if win_pct(pairs[pick], m)[1] >= 30 and win_pct(pairs[pick], m)[0] > base], reverse=True)
    any_all = pd.concat([masks[n] for _, n in beat], axis=1).any(axis=1)
    any10 = pd.concat([masks[n] for _, n in beat[:10]], axis=1).any(axis=1)
    hits = pd.concat([masks[n] for _, n in beat], axis=1).sum(axis=1)
    print(f"\n## Filters picked at {pick}: {len(beat)} groups beat no filter ({base:.1f}%)")
    print("Days with 0 hits:", int((hits == 0).sum()), "| median hits per day:", int(hits.median()))
    for rr in [pick] + [r for r in pairs if r != pick]:
        print(f"\n### Result at {rr}\n| Rule | Days | Days/wk | ≥1 wins | Both lose | Net | Avg/day | Max DD | Sharpe | Avg/week | Green yrs |\n|---|---|---|---|---|---|---|---|---|---|---|")
        print(metrics("No filter", pairs[rr], everyday))
        print(metrics(f"Any of all {len(beat)} hits", pairs[rr], any_all))
        print(metrics("Any of top 10 hits", pairs[rr], any10))
        for k in (10, 15, 20):
            print(metrics(f"At least {k} hits", pairs[rr], hits >= k))

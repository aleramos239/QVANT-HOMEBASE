"""Every filter group (all years, in-sample, 2 NQ / 50-pt) whose 'at least one wins' % beats no filter, per RR."""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import pair_filters as P, pair_l2_more as M, pair_l2_filters as L

pairs = P.paired(); days = list(sorted(pairs["1:1.5"].index)); wk = P.weeks(days)
f = M.book(days).join(M.tape(days))
for c in ["prints", "contracts", "avg_sz", "absdelta"]:
    f[c + "_rel"] = M.rel(f[c])
f = f.join(L.features(days)[["depth_rel", "imb", "pulled_rel"]].rename(columns={"imb": "imb10"}))
f = f.join(P.features().reindex(days)[["gap_atr", "pm_rel", "atr14", "atr_rank"]])
t = pd.read_csv("tickfeat.csv", index_col=0).reindex(days)
f["t1"] = t.delta.abs() / t.vol
f["t3"] = M.rel(t.big); f["t4"] = M.rel(t.ppm)

groups = {}  # name -> boolean mask
def quint(title, col):
    edges, labs = M.bins_of(f[col])
    cut = pd.cut(f[col], edges, labels=labs)
    for lab in labs:
        groups[f"{title}: {lab}"] = cut == lab
fixed = [("1 Gap", "gap_atr", [0, .1, .25, .5, np.inf], ["< 0.10 ATR", "0.10-0.25", "0.25-0.50", "> 0.50 ATR"]),
         ("4 Premarket volume", "pm_rel", [0, .75, 1, 1.25, 1.75, np.inf], ["< 0.75x", "0.75-1x", "1-1.25x", "1.25-1.75x", "> 1.75x"]),
         ("5a Daily ATR", "atr14", [0, 200, 300, 400, np.inf], ["< 200", "200-300", "300-400", "> 400"]),
         ("5b ATR rank", "atr_rank", [-.01, 1/3, 2/3, 1.01], ["low third", "middle", "high third"])]
for title, col, b, labs in fixed:
    cut = pd.cut(f[col], b, labels=labs)
    for lab in labs:
        groups[f"{title}: {lab}"] = cut == lab
for title, col in [("T1 Premarket delta imbalance", "t1"), ("T3 Big prints", "t3"), ("T4 Tape speed", "t4"),
                   ("L1 Book depth", "depth_rel"), ("L2 Book imbalance", "imb10"), ("L4 Pulled orders", "pulled_rel")] + \
                  [(n.split(". ")[0] + " " + n.split(". ")[1].split(" 0")[0].split(" vs")[0].split(",")[0], c) for n, c in M.FILTERS]:
    quint(title, col)
thin = (f.top3_rel <= f.top3_rel.quantile(.2)) | (f.lvl_sz_rel <= f.lvl_sz_rel.quantile(.2)) | (f.depth_rel <= f.depth_rel.quantile(.2))
groups["Combo: T1 >= 0.017"] = f.t1 >= .017
groups["Combo: skip ATR > 400"] = f.atr14 <= 400
groups["Combo: T1 + skip ATR > 400"] = (f.t1 >= .017) & (f.atr14 <= 400)
groups["Combo: skip any thin book"] = ~thin
groups["Combo: skip any thin + T1"] = ~thin & (f.t1 >= .017)

out = ["# Filters that beat no filter on 'at least one wins' (all years, in-sample, 2 NQ, 50-pt stop)",
       "Cutoffs picked after seeing the data. Avg/week = that group's net / all 202 in-sample weeks."]
for rr, p in pairs.items():
    def row(name, m):
        q = p.loc[m[m.fillna(False).astype(bool)].index]; c = q.l + q.s; y = c.groupby(c.index.str[:4]).sum()
        return (name, len(q), len(q) / wk, ((q.l > 0) | (q.s > 0)).mean() * 100, c.sum(), c.mean(), c.sum() / wk, int((y > 0).sum()), len(y))
    base = row("**No filter**", pd.Series(True, index=days))
    rows = sorted([r for n, m in groups.items() if (r := row(n, m))[1] >= 30 and r[3] > base[3]], key=lambda r: -r[3])
    out += [f"\n## {rr}  (no filter: {base[3]:.1f}%)", "| Filter group | Days | Days/wk | ≥1 wins | Both lose | Net | Avg/day | Avg/week | Green yrs |", "|---|---|---|---|---|---|---|---|---|"]
    for r in [base] + rows:
        out.append(f"| {r[0]} | {r[1]} | {r[2]:.1f} | {r[3]:.1f}% | {100 - r[3]:.1f}% | {P.money(r[4])} | {P.money(r[5])} | {P.money(r[6])} | {r[7]}/{r[8]} |")
open("filters_beating_no_filter.md", "w").write("\n".join(out) + "\n")
print("\n".join(out))

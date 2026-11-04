"""One account, 9:30 buy stop +15 / sell stop -15, OCO (first fill cancels the other), $2,000 stop, in-sample.
1:2 on 2 contracts (NQ 50/100, GC 10/20) and 1:1.5 on 4 contracts (NQ 25/37.5, GC 5/7.5). Unfilled legs die 12:55.
Days = every in-sample session (from the market-order side runs); a no-fill day counts as no TP and no win."""
import glob, json
import pandas as pd
from gc_nq_4c_cpi_adp import cpi, adp
from gc_vs_nq_hits import load
R = "/Users/ramoscapital/ramos-quant-homebase/homebase/.state/tester/runs/"
DAYS = {"NQ": load("draft_nq_930_side", "bcc2").index, "GC": load("draft_gc_930_side", "6ea8").index}
RUNS = {("1:2, 2 contracts", "NQ"): ("nq", "4e9b"), ("1:2, 2 contracts", "GC"): ("gc", "d05b"),
        ("1:1.5, 4 contracts", "NQ"): ("nq", "9e36"), ("1:1.5, 4 contracts", "GC"): ("gc", "be62")}

def day_table(mk, k):
    m = glob.glob(f"{R}20261101-*-draft_{mk}_930_straddle-{k}"); assert len(m) == 1
    t = pd.DataFrame(json.load(open(m[0] + "/trades.json"))).groupby("date").agg(net=("net", "sum"), tp=("exit_reason", lambda s: (s == "tp").any()))
    return t

def stats(t, days):
    t = t.reindex(days)
    return len(days), t.net.notna().mean() * 100, t.tp.fillna(False).astype(bool).mean() * 100, (t.net > 0).mean() * 100

T = {key: day_table(*v) for key, v in RUNS.items()}
for lab, keep in (("Every day", None), ("CPI + ADP days", cpi | adp)):
    print(f"\n### {lab}\n| Setup | Market | Days | Filled | Hits full TP | Wins |\n|---|---|---|---|---|---|")
    for (setup, mkt), t in T.items():
        d = DAYS[mkt] if keep is None else DAYS[mkt][DAYS[mkt].isin(keep)]
        n, f, tp, w = stats(t, d); print(f"| {setup} | {mkt} | {n} | {f:.1f}% | {tp:.1f}% | {w:.1f}% |")
print("\n### Every day by year: hits full TP / wins\n| Year | " + " | ".join(f"{s} {m}" for s, m in T) + " |\n|---|---|---|---|---|")
for y in sorted(set(DAYS["NQ"].str[:4])):
    print(f"| {y} | " + " | ".join("{2:.1f}% / {3:.1f}%".format(*stats(t, DAYS[m][DAYS[m].str[:4] == y])) for (s, m), t in T.items()) + " |")

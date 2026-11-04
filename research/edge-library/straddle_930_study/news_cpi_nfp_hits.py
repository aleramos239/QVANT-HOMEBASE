"""CPI + NFP days at 08:29:59, $2,000 stop, in-sample, hit rates only.
Two accounts (market, opposite sides): 4c 1:1.5 NQ b849/006b GC 9d28/d90a; 2c 1:2 NQ 8def/d6e7 GC 6056/a5ec.
One account, +-off stop orders, first fill cancels the other (no fill = no TP)."""
from news_release_cpi_adp import day
TWO = {("4 contracts, 1:1.5", "nq"): ("b849", "006b"), ("4 contracts, 1:1.5", "gc"): ("9d28", "d90a"),
       ("2 contracts, 1:2", "nq"): ("8def", "d6e7"), ("2 contracts, 1:2", "gc"): ("6056", "a5ec")}
ONE = {("4 contracts, 1:1.5", "nq"): {5: "722e", 10: "0bc9", 15: "840a"}, ("4 contracts, 1:1.5", "gc"): {5: "467c", 10: "9f4e", 15: "b935"},
       ("2 contracts, 1:2", "nq"): {5: "d1ee", 10: "594e", 15: "aa75"}, ("2 contracts, 1:2", "gc"): {5: "8d46", 10: "38a6", 15: "d713"}}
yr = {}
for s in ("4 contracts, 1:1.5", "2 contracts, 1:2"):
    print(f"\n### {s}\n| Entry | NQ hits full TP | GC hits full TP |\n|---|---|---|")
    r = {}
    for mk in ("nq", "gc"):
        L, S = (day(mk, k) for k in TWO[(s, mk)]); days = L.index
        r[("two", mk)] = L.tp | S.tp
        for o, k in ONE[(s, mk)].items():
            r[(o, mk)] = day(mk, k).reindex(days).tp.astype("boolean").fillna(False).astype(bool)
    print(f"| Two accounts, market (≥1 account) | {r[('two','nq')].mean()*100:.1f}% | {r[('two','gc')].mean()*100:.1f}% |")
    for o in (5, 10, 15):
        print(f"| One account, ±{o} stop orders | {r[(o,'nq')].mean()*100:.1f}% | {r[(o,'gc')].mean()*100:.1f}% |")
    yr[s] = r
for s, r in yr.items():
    print(f"\n#### {s} by year\n| Year | Two acc NQ | Two acc GC | " + " | ".join(f"±{o} NQ | ±{o} GC" for o in (5, 10, 15)) + " |\n|" + "---|" * 9)
    for y in sorted(set(r[("two", "nq")].index.str[:4])):
        print(f"| {y} | " + " | ".join(f"{v[v.index.str[:4] == y].mean()*100:.0f}%" for v in (r[(o, m)] for o in ("two", 5, 10, 15) for m in ("nq", "gc"))) + " |")

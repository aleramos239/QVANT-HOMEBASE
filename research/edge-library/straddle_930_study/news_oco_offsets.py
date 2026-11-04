"""One account, CPI + ADP days, at the release (CPI 08:29:59, ADP 08:14:59), buy stop +off / sell stop -off, first fill
cancels the other, $2,000 stop, in-sample. Hit full TP % of all the days (no fill = no TP). Days = market-order runs.
1:1.5 4c: NQ 25/37.5, GC 5/7.5 | 1:2 2c: NQ 50/100, GC 10/20."""
import pandas as pd
from news_release_cpi_adp import day
DAYS = {"nq": day("nq", "7528").index, "gc": day("gc", "75d2").index}
K = {("1:1.5, 4 contracts", "nq"): {5: "6ec0", 10: "21f8", 15: "462d"}, ("1:1.5, 4 contracts", "gc"): {5: "310e", 10: "9ade", 15: "d26c"},
     ("1:2, 2 contracts", "nq"): {5: "5ac7", 10: "ee64", 15: "0e8b"}, ("1:2, 2 contracts", "gc"): {5: "561f", 10: "7694", 15: "c598"}}
H = {}
for (s, mk), offs in K.items():
    for off, k in offs.items():
        t = day(mk, k).reindex(DAYS[mk])
        H[(s, mk, off)] = (t.net.notna(), t.tp.astype("boolean").fillna(False).astype(bool))
for s in ("1:1.5, 4 contracts", "1:2, 2 contracts"):
    print(f"\n### {s}\n| Offset | NQ hits full TP | GC hits full TP | NQ filled | GC filled |\n|---|---|---|---|---|")
    for off in (5, 10, 15):
        n, g = H[(s, "nq", off)], H[(s, "gc", off)]
        print(f"| ±{off} | {n[1].mean()*100:.1f}% | {g[1].mean()*100:.1f}% | {n[0].mean()*100:.0f}% | {g[0].mean()*100:.0f}% |")
    print(f"\n| Year | " + " | ".join(f"NQ ±{o} | GC ±{o}" for o in (5, 10, 15)) + " |\n|" + "---|" * 7)
    for y in sorted(set(DAYS["nq"].str[:4])):
        c = [f"{H[(s, mk, o)][1][H[(s, mk, o)][1].index.str[:4] == y].mean()*100:.0f}%" for o in (5, 10, 15) for mk in ("nq", "gc")]
        print(f"| {y} | " + " | ".join(c) + " |")

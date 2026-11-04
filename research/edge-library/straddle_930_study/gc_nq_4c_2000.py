"""GC vs NQ 9:30 two accounts, 4 contracts, $2,000 stop total, 1:1.5, in-sample, hit rates only.
NQ 25/37.5 pts (ed1f/f64c); GC 5/7.5 pts (1d07/ce3e)."""
from gc_vs_nq_hits import pair, pct
M = {"NQ": pair("draft_nq_930_side", "ed1f", "f64c"), "GC": pair("draft_gc_930_side", "1d07", "ce3e")}
print("| Market | Days | ≥1 hits full TP | ≥1 wins |\n|---|---|---|---|")
for k, q in M.items():
    t, w = pct(q); print(f"| {k} | {len(q)} | {t:.1f}% | {w:.1f}% |")
print("\n| Year | NQ ≥1 TP | NQ ≥1 wins | GC ≥1 TP | GC ≥1 wins |\n|---|---|---|---|---|")
for y in sorted(set(M["NQ"].index.str[:4])):
    print(f"| {y} | " + " | ".join(f"{v:.1f}%" for k in M for v in pct(M[k][M[k].index.str[:4] == y])) + " |")

"""GC 9:30 two accounts, 4 GC, 1:1.5, in-sample, hit rates only. A: $2,000 stop total (5/7.5 pts, 1d07/ce3e).
B: 10-pt stop ($4,000 total, 10/15 pts, 986a/053f). Prior: 2 GC 10/20 (6ea8/8c3d), NQ 1 NQ 50/100 (bcc2/4b5a)."""
from gc_vs_nq_hits import pair, pct
import contextlib, io
S = {"NQ 1 NQ, 50/100 (1:2)": ("draft_nq_930_side", "bcc2", "4b5a"),
     "GC 2 GC, 10/20 (1:2)": ("draft_gc_930_side", "6ea8", "8c3d"),
     "GC 4 GC, 5/7.5 (1:1.5, $2,000 stop)": ("draft_gc_930_side", "1d07", "ce3e"),
     "GC 4 GC, 10/15 (1:1.5, $4,000 stop)": ("draft_gc_930_side", "986a", "053f")}
M = {k: pair(*v) for k, v in S.items()}
print("| Setup | Days | ≥1 hits full TP | ≥1 wins |\n|---|---|---|---|")
for k, q in M.items():
    t, w = pct(q); print(f"| {k} | {len(q)} | {t:.1f}% | {w:.1f}% |")
print("\n| Year | " + " | ".join(f"{k.split(',')[1].strip()} TP / wins" for k in list(M)[2:]) + " |\n|---|---|---|")
for y in sorted(set(M[list(M)[2]].index.str[:4])):
    print(f"| {y} | " + " | ".join("{:.1f}% / {:.1f}%".format(*pct(q[q.index.str[:4] == y])) for q in list(M.values())[2:]) + " |")

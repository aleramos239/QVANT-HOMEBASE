"""Only the two numbers the owner cares about: ≥1 hits full TP and ≥1 wins, by year (1 NQ, $1,000 stop, 1:2, every day)."""
import contextlib, io
with contextlib.redirect_stdout(io.StringIO()):
    from everyday_1nq import ins, oos

def pct(q):
    return (q.a.astype(bool) | q.b.astype(bool)).mean() * 100, ((q.l > 0) | (q.s > 0)).mean() * 100

print("| Part | Days | ≥1 hits full TP | ≥1 wins |\n|---|---|---|---|")
for lab, q in (("In-sample", ins), ("Test months", oos)):
    t, w = pct(q); print(f"| {lab} | {len(q)} | {t:.1f}% | {w:.1f}% |")
print("\n| Year | In-sample TP | In-sample wins | Test TP | Test wins |\n|---|---|---|---|---|")
for y in sorted(set(ins.index.str[:4]) | set(oos.index.str[:4])):
    a, b = ins[ins.index.str[:4] == y], oos[oos.index.str[:4] == y]
    i = "| ".join(f"{v:.1f}% " for v in pct(a)) if len(a) else "- | - "
    o = "| ".join(f"{v:.1f}% " for v in pct(b)) if len(b) else "- | - "
    print(f"| {y} | {i}| {o}|")

"""ENGINE OWNER diagnosis: WHICH entries / non-clock exits differ between hold_to='day' and 'session' (dates, clock times and
exit reasons only; never a price or a P&L)."""
import sys, datetime as dt
from pathlib import Path
W = Path(__file__).resolve().parents[2]
for _p in (str(W), str(W / "engine")):
    sys.path.insert(0, _p)
import l2sim as S, run_menus as RM

def main():
    import families as F
    name, root, tf = sys.argv[1], sys.argv[2], sys.argv[3]
    grid = F.unit_grid(name, root, tf)
    pick = sorted({0, 3, 9, 14, 31, len(grid) - 32, len(grid) - 1})
    cells = [grid[i] for i in pick]
    days = [d for d in RM.SMOKE_DAYS if S._date(d) in set(S.sessions(*S.period("build"), root))]
    specs = [x for c in cells for x in RM.cell_specs(c)]
    new = S.run_many(specs, days=days, root=root, workers=1, features=F.features_for(name))
    old = S.run_many([(c, {**p, "hold_to": "session"}) for c, p in specs], days=days, root=root, workers=1, features=F.features_for(name))
    ent = lambda t: (t["date"], t["side"], t["entry_ms"], t["entry_price"])
    hm = lambda ms: dt.datetime.fromtimestamp(ms / 1000, S.ET).strftime("%m-%d %H:%M:%S")
    seen = set()
    for (cls, p), a, b in zip(specs, new, old):
        A, B = {ent(t): t for t in a["trades"]}, {ent(t): t for t in b["trades"]}
        for e in sorted(set(A) ^ set(B)):
            row = (p.get("sess"), e[0], hm(e[2]), "only-new" if e in A else "only-old")
            if row not in seen:
                seen.add(row); print(*row)
        for e, t in B.items():
            if e in A and t["exit_reason"] not in ("time", "eod") and A[e] != t:
                print("non-clock exit changed:", p.get("sess"), e[0], "entry", hm(e[2]), "old", hm(t["exit_ms"]), t["exit_reason"], "new", hm(A[e]["exit_ms"]), A[e]["exit_reason"])
        for sk in a["skipped"]:
            row = ("new skipped", p.get("sess"), sk["date"], sk["reason"])
            if row not in seen:
                seen.add(row); print(*row)

if __name__ == "__main__":
    main()

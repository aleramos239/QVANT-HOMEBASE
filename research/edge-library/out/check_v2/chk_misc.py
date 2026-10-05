"""CHECKER v2, loose ends (my own code; BUILD stores, json files and 2024 run.json METADATA only -- no new 2024 P&L):
 B. test (2) counts at 200 and 4000 draws; the BUILD-pass set at 4000 draws vs what the analyst opened
 C. members/<name>/surviving_set.csv vs my surviving set
 D. normal vs stress per trade on the 18:00 bracket default (BUILD), from my re-runs
 I. units failed on (2) only because a control is missing on disk
 J. 2024 menus run in v2: cells on disk that belong to no BUILD passer (by-product reads)
 K. fail-only-(3) count; exact-60 % passers"""
import csv, json, sys, collections
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import chk_lib as C
import l2sim
l2sim.wait_compute_window()
W = C.W
B = {r["uid"]: r for r in json.loads((C.OUT / "chk_build.json").read_text())}
T = {r["uid"]: r for r in json.loads((C.OUT / "chk_t2.json").read_text())}
A = {r["uid"]: r for r in json.loads((W / "out" / "v2" / "build_units.json").read_text())}
P = json.loads((C.OUT / "chk_pick.json").read_text())
U = {u["uid"]: u for u in C.units()}

# ---- B
def pass4000(uid):
    b, t = B[uid], T.get(uid)
    if b["t2"] is None or t is None:
        return None
    ok = True
    for c, v in b["det"].items():
        if c in t["det"]:
            d = t["det"][c]
            ok &= bool(d["lift"] > 0 and d["p_beat"] >= 0.95) and not v.get("short")
        else:
            ok &= bool(v.get("pass"))
    return ok
p200 = {u for u in B if B[u]["t2"]}
p4k = {u for u in B if pass4000(u)}
an = {u for u in A if A[u]["t2"]}
print("B. (2) drawn", sum(B[u]["t2"] is not None for u in B), "| pass (2): analyst", len(an), "mine K=200", len(p200), "mine K=4000", len(p4k))
bp = lambda S: {u for u in S if B[u]["t1"] and B[u]["t3"]}  # noqa: E731
print("   BUILD (1)+(2)+(3): analyst", len(bp(an)), "mine K=200", len(bp(p200)), "mine K=4000", len(bp(p4k)))
opened = set(P)
print("   opened by the analyst but failing (2) at 4000 draws:", sorted(opened - bp(p4k)))
print("   passing at 4000 draws but never opened:", sorted(bp(p4k) - opened))
by = collections.Counter(U[u]["src"] for u in bp(p4k)); print("   4000-draw passers by stage", dict(by), "by market", dict(collections.Counter(U[u]["root"] for u in bp(p4k))))
print("   members failing at 4000 draws:", [u for u in P if P[u]["admit"] and u not in bp(p4k)])

# ---- K
only3 = [u for u in A if A[u]["t1"] and A[u]["t2"] and not A[u]["t3"]]
print("K. analyst: pass (1)+(2), fail only (3):", len(only3), "| any of them opened:", [u for u in only3 if u in opened])
print("   exact-60 % share units that pass BUILD (analyst) and were opened:", [u for u in opened if abs(B[u]["share"] - 0.6) < 1e-9])
print("   members' BUILD share:", {u: round(B[u]["share"], 3) for u in P if P[u]["admit"]})

# ---- I
miss = []
for u, b in B.items():
    if b["t2"] is None:
        continue
    why = {c: v.get("why") for c, v in b["det"].items() if v.get("why") and "no " in str(v.get("why"))}
    if why:
        rest = all(v.get("pass") for c, v in b["det"].items() if c not in why)
        miss.append((u, why, b["t1"], b["t3"], rest))
print("I. units with a control missing on disk (drawn):", len(miss), "| of them pass (1)+(3) and every control that exists:", [m[0] for m in miss if m[2] and m[3] and m[4]])

# ---- C
for sp in sorted((W / "members").glob("*/spec.json")):
    if sp.parent.name.startswith("_"):
        continue
    m = json.loads(sp.read_text())
    S = list(csv.DictReader(open(sp.parent / "surviving_set.csv")))
    mine = set(P[m["uid"]]["survivors"])
    dflt = [r["cell"] for r in S if r["default"] == "True"]
    neg = [r["cell"] for r in S if min(float(r["net_build"]), float(r["net_2024"]), float(r["stress_build"]), float(r["stress_2024"])) <= 0]
    ok = {r["cell"] for r in S} == mine and dflt == [m["cell"]] and not neg
    print(f"C. {m['name']:40s} surviving_set.csv {len(S):3d} mine {len(mine):3d} default {dflt} {'OK' if ok else 'DIFF'} non-positive rows {len(neg)}")

# ---- D
RR = C.OUT / "rerun"
for nm in ("straddle_t_1800-NQ-tf30-eve", "straddle_t_0830-NQ-tf30-pre", "orb-NQ-tf15-pre"):
    n = json.loads((RR / f"{nm}-build-normal.json").read_text())["trades"]; s = json.loads((RR / f"{nm}-build-stress.json").read_text())["trades"]
    cid = next(iter(n))
    dn = {t["date"]: t for t in n[cid]}; ds = {t["date"]: t for t in s[cid]}
    both = [d for d in dn if d in ds]
    diff = np.array([ds[d]["net"] - dn[d]["net"] for d in both])
    flip = [d for d in both if dn[d]["side"] != ds[d]["side"]]
    print(f"D. {nm} {cid}: normal {sum(t['net'] for t in n[cid]):.0f} ({len(n[cid])} tr) stress {sum(t['net'] for t in s[cid]):.0f} ({len(s[cid])} tr) | same-day pairs {len(both)} "
          f"mean diff {diff.mean():.1f} median {np.median(diff):.1f} | days stress better by > $500: {int((diff > 500).sum())} sum {diff[diff > 500].sum():.0f} | worse by > $500: {int((diff < -500).sum())} sum {diff[diff < -500].sum():.0f} | side flips {len(flip)} "
          f"| double fills in stress {sum(1 for t in s[cid] if t.get('both_sides'))}")
    e = np.array([t["entry_ms"] for t in n[cid]]) // 1000 % 86400
    print("      entry second-of-day (UTC) most common:", collections.Counter((e // 60).tolist()).most_common(3), "| held < 5 s:", sum(1 for t in n[cid] if t["seconds"] < 5))

# ---- J
tot = extra = 0
rows = []
for d in sorted((W / "runs_v2").iterdir()):
    m = json.loads((d / "run.json").read_text())
    if m.get("period") != "pick" or m.get("control") != "pick":
        continue
    key = d.name
    us = [u for u in opened if key == f"{U[u]['key']}-{U[u]['sess']}-pick"]
    ids = set()
    for u in us:
        ids |= {r["id"] for r in C.build_rows(C.build_store(U[u]["key"]), U[u])}
    cells = [c["id"] for c in m["cells"]]
    ex = [c for c in cells if c not in ids]
    tot += len(cells); extra += len(ex)
    if ex or not us:
        rows.append((key, len(cells), len(ex), us))
print("J. v2 2024 menus:", tot, "cells run |", extra, "cells belong to no opened unit")
for r in rows:
    print("     ", r)

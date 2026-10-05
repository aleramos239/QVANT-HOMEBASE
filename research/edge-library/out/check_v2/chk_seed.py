"""CHECKER v2 DIAGNOSTIC (not my recomputation -- that is chk_build / chk_t2): the ANALYST'S OWN c1 function (out/v2/v2.py,
K = 200) called with 20 different seeds on every unit that passes (1) and (3) and whose c1 result sits near the 95 % line.
Question: does the test (2) verdict depend on the random seed?  Seed 0 = the analyst's own seed (must reproduce his number).
BUILD stores only.   python chk_seed.py"""
import json, sys
from pathlib import Path
import numpy as np
W = Path("/Users/ramoscapital/ramos-quant-homebase/research/edge-library")
sys.path.insert(0, str(W / "out" / "v2")); sys.path.insert(0, str(W / "engine"))
import l2sim  # noqa: E402
l2sim.wait_compute_window()
import v2 as V  # noqa: E402

A = {r["uid"]: r for r in json.loads((W / "out" / "v2" / "build_units.json").read_text())}
U = {u["uid"]: u for u in V.units()}
out = {}
for uid, a in A.items():
    if not (a["t1"] and a["t3"]) or a["t2"] is None:
        continue
    det = json.loads(a["detail"]) if isinstance(a["detail"], str) else a["detail"]
    c = det.get("c1")
    if not c or "p_beat" not in c or not (0.88 <= c["p_beat"] <= 0.995):
        continue
    others_ok = all(v.get("pass") for k, v in det.items() if k != "c1")
    u = U[uid]
    st = V.store(u["key"], period="build")
    ts = V.table_stats(V.table(st, u))
    pu = V.store(f"c1-{u['root']}-tf{u['tf']}", period="build")
    base = V.seed_of(uid, "build-c1")
    ps, draws = [], []
    for i in range(20):
        ct = V.c1_table(st, u, ts["ids"], pu, base + i)
        ps.append(float((ts["avg_net"] > ct["draws"]).mean()))
        draws.append(ct["draws"])
    d = np.concatenate(draws)
    out[uid] = {"analyst_p": c["p_beat"], "seed0_p": ps[0], "ps": ps, "seeds_pass": int(sum(p >= 0.95 for p in ps)), "p_4000": float((ts["avg_net"] > d).mean()),
                "lift_4000": float(ts["avg_net"] - d.mean()), "analyst_pass": bool(a["build_pass"]), "other_controls_pass": bool(others_ok)}
    o = out[uid]
    print(f"{uid:36s} analyst p {o['analyst_p']:.3f} (seed0 {o['seed0_p']:.3f}) | 20 seeds: min {min(ps):.3f} max {max(ps):.3f} pass {o['seeds_pass']:2d}/20 | "
          f"4000 draws p {o['p_4000']:.4f} | analyst BUILD pass {o['analyst_pass']} | other controls ok {others_ok}", flush=True)
(W / "out" / "check_v2" / "chk_seed.json").write_text(json.dumps(out, indent=1))

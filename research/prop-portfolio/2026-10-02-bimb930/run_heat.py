import sys, json, time, os, itertools, math
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930")
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2")
import numpy as np
import l2sim as S
from bimb930 import Imb930, Flow930, WImb930
from widefeat import WideFeatures
from run_full import stats
BASE = "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930/"
OUT = BASE + "out_heat/"
FIX = [10.0, 15.0, 20.0, 25.0, 30.0]; ATRM = [1.0, 1.5, 2.0, 2.5, 3.0]; RR = [1.0, 2.0, 3.0]
CELLS = [("pts", v, r) for v in FIX for r in RR] + [("atr", v, r) for v in ATRM for r in RR]
FAMS = {"book": (Imb930, ("imb", "imb_inv"), lambda c: S.L2Features(list(c))),
        "wide": (WImb930, ("wimb", "wimb_inv"), lambda c: WideFeatures(list(c))),
        "flow": (Flow930, ("flow", "flow_inv"), lambda c: S.L2Features(list(c)))}

def extra(trades):
    nets = np.array([t["net"] * 2 for t in trades], float)
    if len(nets) == 0: return {}
    eq = np.cumsum(nets); dd = float(np.min(eq - np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]))
    sd = nets.std(ddof=1) if len(nets) > 1 else float("nan")
    return {"max_dd": round(dd, 0), "sharpe": round(float(nets.mean() / sd * math.sqrt(252)), 2) if sd and sd == sd else None,
            "avg_risk": round(float(np.mean([abs(t["entry_price"] - t["sl"]) * 40.0 for t in trades])), 0)}

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True); t0 = time.time()
    for fam, (cls, sigs, loader) in FAMS.items():
        modes = sigs + ("long", "short"); feat = loader(cls.FEATURES); res = {}
        for sm, sv in (("pts", None), ("atr", None)):
            cells = [c for c in CELLS if c[0] == sm]
            specs = [(cls, {"mode": m, "stop_mode": c[0], "stop_val": c[1], "tgt_r": c[2]}) for m in modes for c in cells]
            keys = [(m, c) for m in modes for c in cells]
            runs = S.run_many(specs, features=feat)
            for (m, c), r in zip(keys, runs):
                d = stats(r); d.update(extra(r["trades"])); d["errors"] = r.get("skipped_by_error"); d["both_sides"] = r.get("both_sides_sessions")
                res[f"{m}|{c[0]}|{c[1]}|{c[2]}"] = d
            json.dump(res, open(OUT + f"heat_{fam}.json", "w")); print(fam, sm, "done", round(time.time() - t0), flush=True)
    print("ALL DONE", flush=True)

import sys, os, time, gzip, pickle
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930")
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2")
import l2sim as S
from bimb930 import Imb930, Flow930, WImb930, Combo930
from widefeat import WideFeatures
OUT = "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930/out_heat2/"
FIX = [10.0, 15.0, 20.0, 25.0, 30.0]; ATRM = [1.0, 1.5, 2.0, 2.5, 3.0]; RR = [1.0, 2.0, 3.0]
CELLS = [("pts", v, r) for v in FIX for r in RR] + [("atr", v, r) for v in ATRM for r in RR]
FAMS = {"book": (Imb930, ("imb", "imb_inv", "long", "short"), lambda c: S.L2Features(list(c))),
        "wide": (WImb930, ("wimb", "wimb_inv"), lambda c: WideFeatures(list(c))),
        "flow": (Flow930, ("flow", "flow_inv", "long", "short"), lambda c: S.L2Features(list(c))),
        "combo": (Combo930, Combo930.MODES, lambda c: WideFeatures(list(c)))}
if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True); t0 = time.time()
    for fam, (cls, modes, loader) in FAMS.items():
        feat = loader(cls.FEATURES); res = {}
        for sm in ("pts", "atr"):
            cells = [c for c in CELLS if c[0] == sm]
            keys = [(m, c) for m in modes for c in cells]
            runs = S.run_many([(cls, {"mode": m, "stop_mode": c[0], "stop_val": c[1], "tgt_r": c[2]}) for m, c in keys], features=feat)
            for (m, c), r in zip(keys, runs):
                res[f"{m}|{c[0]}|{c[1]}|{c[2]}"] = {"trades": [(t["date"], t["side"], t["gross"], abs(t["entry_price"] - t["sl"]), t["exit_reason"]) for t in r["trades"]],
                                                   "used": r["used"], "sessions": r["sessions"], "errors": r.get("skipped_by_error"), "both_sides": r.get("both_sides_sessions")}
            print(fam, sm, "done", round(time.time() - t0), flush=True)
        with gzip.open(OUT + f"trades_{fam}.pkl.gz", "wb") as f: pickle.dump(res, f)
    print("ALL DONE", flush=True)

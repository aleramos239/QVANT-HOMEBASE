import sys, gzip, pickle, time
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930")
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2")
import l2sim as S
from bimb930 import WImb930
from widefeat import WideFeatures
from run_oos import GRID, START, END, OUT, pack
if __name__ == "__main__":
    t0 = time.time()
    res = pickle.load(gzip.open(OUT + "trades_oos.pkl.gz", "rb"))
    specs = [(WImb930, {"mode": "wimb_inv", "filt": "adx", "stop_mode": sm, "stop_val": v, "tgt_r": rr}) for sm, v, rr in GRID]
    runs = S.run_many(specs, START, END, allow_holdout=True, features=WideFeatures(list(WImb930.FEATURES), allow_holdout=True))
    old = {k: res[k]["trades"] for k in res if k.startswith("wide|wimb_inv|adx|pts|30.0|")}
    for (sm, v, rr), r in zip(GRID, runs): res[f"wide|wimb_inv|adx|{sm}|{v}|{rr}"] = pack(r)
    for k, t in old.items(): assert res[k]["trades"] == t, f"re-run differs from the first OOS run for {k}"   # determinism check
    with gzip.open(OUT + "trades_oos.pkl.gz", "wb") as f: pickle.dump(res, f)
    print("errors:", [r.get("skipped_by_error") for r in runs if r.get("skipped_by_error")], "| determinism check on the 2 earlier cells: identical | done", round(time.time() - t0), "s")

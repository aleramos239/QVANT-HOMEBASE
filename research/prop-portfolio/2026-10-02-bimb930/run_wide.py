import sys, json, time, os
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930")
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2")
import l2sim as S
from bimb930 import WImb930
from widefeat import WideFeatures, WideC2
from run_full import stats, write_csv
cols = list(WImb930.FEATURES)
BASE = "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930/"
if __name__ == "__main__":
    t0 = time.time()
    for tgt, tag in ((2.0, "1to2"), (3.0, "1to3")):
        OUT = BASE + f"out_wide_{tag}/"; os.makedirs(OUT, exist_ok=True)
        modes = ("wimb", "wimb_inv", "long", "short")
        real = S.run_many([(WImb930, {"mode": m, "tgt_r": tgt}) for m in modes], features=WideFeatures(cols))
        out = {}
        for m, r in zip(modes, real):
            out[m] = stats(r); json.dump(r["trades"], open(OUT + f"trades_{m}.json", "w")); write_csv(r["trades"], OUT + f"ledger_{m}_2NQ.csv")
        json.dump(out, open(OUT + "stats_real.json", "w"), indent=1); print(tag, "real done", round(time.time() - t0), flush=True)
        for m in ("wimb", "wimb_inv"):
            nulls = []
            for k in range(1, 21):
                nulls.append(stats(S.run(WImb930, {"mode": m, "tgt_r": tgt}, features=WideC2(cols, seed=k))))
                json.dump(nulls, open(OUT + f"stats_nulls_{m}.json", "w"))
            print(tag, m, "nulls done", round(time.time() - t0), flush=True)
    print("ALL DONE", flush=True)

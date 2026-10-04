import sys, json, time, os
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930")
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2")
import l2sim as S, score as SC
from bimb930 import Imb930, Flow930
from run_full import stats, write_csv
fam, tgt, outdir = sys.argv[1], float(sys.argv[2]), sys.argv[3]
cls, sig = (Imb930, "imb") if fam == "imb" else (Flow930, "flow")
cols = list(cls.FEATURES)
OUT = "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930/" + outdir + "/"
if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True); t0 = time.time(); out = {}
    modes = (sig, "long", "short")
    real = S.run_many([(cls, {"mode": m, "tgt_r": tgt}) for m in modes], features=S.L2Features(cols))
    for m, r in zip(modes, real):
        out[m] = stats(r); json.dump(r["trades"], open(OUT + f"trades_{m}.json", "w")); write_csv(r["trades"], OUT + f"ledger_{m}_2NQ.csv")
    json.dump(out, open(OUT + "stats_real.json", "w"), indent=1); print("real done", round(time.time() - t0), flush=True)
    nulls = []
    for k in range(1, 21):
        nulls.append(stats(S.run(cls, {"mode": sig, "tgt_r": tgt}, features=SC.C2Features(cols, seed=k))))
        json.dump(nulls, open(OUT + "stats_nulls.json", "w"), indent=1); print("null", k, round(time.time() - t0), flush=True)
    print("ALL DONE", flush=True)

import sys, json, time
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930")
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2")
import l2sim as S, score as SC
from bimb930 import Flow930
from run_full import stats, write_csv
cols = list(Flow930.FEATURES)
OUT = "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930/out_flow/"
if __name__ == "__main__":
    import os; os.makedirs(OUT, exist_ok=True)
    t0 = time.time(); out = {}
    modes = ("flow", "long", "short")
    real = S.run_many([(Flow930, {"mode": m}) for m in modes], features=S.L2Features(cols))
    for m, r in zip(modes, real):
        out[m] = stats(r); json.dump(r["trades"], open(OUT + f"trades_{m}.json", "w")); write_csv(r["trades"], OUT + f"ledger_{m}_2NQ.csv")
    json.dump(out, open(OUT + "stats_real.json", "w"), indent=1)
    print("real done", round(time.time() - t0), "s", flush=True)
    nulls = []
    for k in range(1, 21):
        nulls.append(stats(S.run(Flow930, {"mode": "flow"}, features=SC.C2Features(cols, seed=k))))
        json.dump(nulls, open(OUT + "stats_nulls.json", "w"), indent=1)
        print("null", k, round(time.time() - t0), "s", flush=True)
    print("ALL DONE", flush=True)

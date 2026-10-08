"""judas (v2) on the BLUEPRINT BUILD days (2021-09-22 .. 2025-06-30) only: thrust K x stop (% of the move) x target (% of the move), engine costs, 1 NQ contract.
Round 2 of the idea (reason written first: the 50% give-back happens on most days, so only a big, fast reversal can be informative). A build-days look, not a blueprint verdict."""
import pickle, sys, time
import l2sim as S
from families import retrace as F

def main():
    OUT = sys.argv[1]
    KS = (0.2, 0.25, 0.3)
    SS = (0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0)
    TS = (0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 0.0)        # 0 = no target
    specs, keys = [], []
    for k in KS:
        for s in SS:
            for t in TS:
                specs.append((F.Judas, {"tf": "1", "sess": "nyam", "hold_to": "day", "thrust": k, "stop_m": s, "tgt_m": t}))
                keys.append((k, s, t))
    t0 = time.time()
    res = S.run_many(specs, root="NQ", period="bp_build", workers=4)
    print("done in", round(time.time() - t0), "s;", len(specs), "cells", flush=True)
    print("sessions with errors:", [(k, r["skipped_by_error"]) for k, r in zip(keys, res) if r["skipped_by_error"]], flush=True)
    pickle.dump({"keys": keys, "trades": [r["trades"] for r in res]}, open(OUT, "wb"))
    print("saved", OUT, flush=True)

if __name__ == "__main__":
    main()

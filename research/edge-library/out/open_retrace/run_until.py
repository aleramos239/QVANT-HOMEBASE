"""judas on the BLUEPRINT BUILD days: the last-entry time (until) 11:00 (today) / 12:00 / 13:30 / 15:55 for the owner's best cells. Build-days look."""
import pickle, sys, time
import l2sim as S
from families import retrace as F
def main():
    out = sys.argv[1]
    keys, specs = [], []
    for k in (0.3, 0.25):
        for u in ("11:00", "12:00", "13:30", "15:55"):
            for s, t in ((0.5, 0.5), (0.75, 0.5), (0.5, 3.0), (1.0, 0.5), (1.5, 0.5)):
                keys.append((k, u, s, t))
                specs.append((F.Judas, {"tf": "1", "sess": "nyam", "hold_to": "day", "thrust": k, "stop_m": s, "tgt_m": t, "until": u}))
    t0 = time.time()
    res = S.run_many(specs, root="NQ", period="bp_build", workers=4)
    print("done in", round(time.time() - t0), "s;", len(specs), "cells; errors", [(k, r["skipped_by_error"]) for k, r in zip(keys, res) if r["skipped_by_error"]], flush=True)
    pickle.dump({"keys": keys, "trades": [r["trades"] for r in res]}, open(out, "wb"))
    print("saved", flush=True)
if __name__ == "__main__":
    main()

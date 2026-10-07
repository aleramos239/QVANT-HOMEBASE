"""open_retrace on the BLUEPRINT BUILD days (2021-09-22 .. 2025-06-30) only: level x reward:risk heat map, engine costs, 1 NQ contract.
Not a blueprint verdict (the toolkit cannot carry a structure stop yet): a build-days look the owner asked for."""
import json, pickle, sys, time
import l2sim as S
from families import retrace as F

def main():
    OUT = sys.argv[1]
    LEVELS = (0.4, 0.5, 0.6)
    RRS = (0.5, 0.75, 1.0, 2.0, 3.0, 0.0)          # 0 = no target (runs to the stop or the 15:58 flat)
    specs, keys = [], []
    for lv in LEVELS:
        for rr in RRS:
            specs.append((F.OpenRetrace, {"tf": "1", "sess": "nyam", "hold_to": "day", "level": lv, "stop_mode": "struct", "tgt_r": rr}))
            keys.append((lv, rr))
    t0 = time.time()
    res = S.run_many(specs, root="NQ", period="bp_build", workers=4)
    print("done in", round(time.time() - t0), "s", flush=True)
    bad = [(k, r["skipped_by_error"]) for k, r in zip(keys, res) if r["skipped_by_error"]]
    print("sessions with errors:", bad, flush=True)
    pickle.dump({"keys": keys, "trades": [r["trades"] for r in res], "meta": [{k: r[k] for k in ("sessions", "used", "skipped_by_error")} for r in res]}, open(OUT, "wb"))
    print("saved", OUT, [len(r["trades"]) for r in res], flush=True)



if __name__ == "__main__":
    main()

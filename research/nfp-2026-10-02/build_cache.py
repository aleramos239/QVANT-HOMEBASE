"""Cache event-day tapes (08:20-09:56 ET) for NFP/CPI days. usage: build_cache.py IS|HO"""
import pickle, sys
from multiprocessing import Pool
from nfp_lib import *

if __name__ == "__main__":
    part = sys.argv[1]
    ev = [(d, t) for d, t in events() if (d <= IS_END) == (part == "IS")]
    jobs = [(r, d) for r in SPEC for d, _ in ev]
    with Pool(3) as p:
        res = p.map(load_event, jobs, chunksize=4)
    out = {(r, d): v for r, d, v in res if v is not None}
    miss = [(r, d) for r, d, v in res if v is None]
    pickle.dump({"events": ev, "tapes": out}, open(CACHE / f"tapes_{part}.pkl", "wb"))
    print(part, "events", len(ev), "tapes", len(out), "missing", miss[:20], len(miss))

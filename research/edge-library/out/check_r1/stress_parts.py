"""CHECKER -- what each part of the written stress (2 ticks + 250 ms) does to the admitted member (own replay)."""
import json, sys
from multiprocessing import get_context
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_member as C
S = C.S
V = [(1.0, 85, 0), (1.0, 250, 0), (2.0, 85, 0), (2.0, 250, 0), (3.0, 85, 0)]
if __name__ == "__main__":
    out = {}
    for period in ("build", "pick"):
        a, b = S.period(period)
        days = [d.isoformat() for d in S.sessions(a, b, "NQ")]
        own = {t["date"] for t in json.loads(Path(__file__).with_name(f"own_trades_{period}.json").read_text())}
        with get_context("spawn").Pool(8) as pool:
            res = dict(pool.imap_unordered(C.own_day, [(d, V) for d in days if d in own], chunksize=8))
        out[period] = {f"{v[0]:g} tick, live after {v[1]} ms": round(sum(r[v]["net"] for r in res.values() if r and r.get(v)), 2) for v in V}
        print(period, out[period])
    Path(__file__).with_name("stress_parts.json").write_text(json.dumps(out, indent=1))

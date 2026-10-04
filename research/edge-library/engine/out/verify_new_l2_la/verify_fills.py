"""D1 / D5 real trades: every entry is a recorded signal's market order filled on the FIRST print at / after T + 85 ms, at that
print's price +/- 1 tick; and no trade enters without a signal. Identity / timing only."""
import sys, json, datetime as dt
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
import verify_bc_options as V
S = V.S
def main():
    sp = V.specs()
    rec, res = V.one_pass(sp, S.L2Features(V.COLS))
    sig = {}
    for r in rec:
        if r[0] == "sig":
            p = json.loads(r[1].split("|", 1)[1])
            fam = "d1" if "k" in p else "d5"
            sig.setdefault((fam, p["tf"], p["sess"], r[2], r[4]), []).append(r[3])
    tapes, n, bad, late = {}, 0, [], 0
    for (c, p), r in zip(sp, res):
        if c.__name__ not in ("BimbFollowD1", "FlowExhaust"):
            continue
        fam = "d1" if c.__name__ == "BimbFollowD1" else "d5"
        for t in r["trades"]:
            n += 1
            iso = t["date"]
            if iso not in tapes:
                tapes[iso] = V.REAL_TAPE(dt.date.fromisoformat(iso))
            tp = tapes[iso]
            ok = False
            for T in sig.get((fam, p["tf"], p["sess"], iso, t["side"]), []):
                k = int(np.searchsorted(tp.ts, T + V.LAT, side="left"))
                if k < len(tp.ts) and int(tp.ts[k]) == t["entry_ns"]:
                    sd = 1 if t["side"] == "long" else -1
                    ok = abs(t["entry_price"] - (float(tp.px[k]) + sd * 0.25)) < 1e-9 and t["order_price"] is None
                    late += (t["entry_ns"] - T) > 5 * S.NS
                    break
            if not ok:
                bad.append([fam, p["tf"], p["sess"], iso, t["side"], t["entry_ns"]])
    print(json.dumps({"d1_d5_trades": n, "not_explained_by_a_signal_fill": len(bad), "first": bad[:5], "fills_later_than_5s_after_signal": late}))
if __name__ == "__main__":
    main()

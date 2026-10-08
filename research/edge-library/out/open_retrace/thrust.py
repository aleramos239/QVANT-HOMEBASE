"""Descriptive only (no P&L): how big is the 09:30 thrust in units of the prior daily ATR14, and how long after its extreme does half of it come back."""
import json, sys, numpy as np
import l2sim as S

def atr_before(daily, iso):
    rows = [r for r in daily if r["date"] < iso]
    if len(rows) < 15: return None
    trs = [max(rows[i]["h"]-rows[i]["l"], abs(rows[i]["h"]-rows[i-1]["c"]), abs(rows[i]["l"]-rows[i-1]["c"])) for i in range(1, len(rows))]
    a = sum(trs[:14])/14.0
    for x in trs[14:]: a = (a*13.0 + x)/14.0
    return a

def main():
    import datetime as dt
    a, b = S.BP_BUILD
    days = S.sessions(a, b, "NQ", allow_holdout=S.ALLOW_BP)
    daily = S.load_daily("NQ", S.ALLOW_BP)
    out = []
    for d in days:
        iso = d.isoformat()
        atr = atr_before(daily, iso)
        if not atr: continue
        try: tape = S.load_tape(d, "NQ", allow_holdout=S.ALLOW_BP)
        except Exception: continue
        if tape is None or len(tape.ts) == 0: continue
        base = S.et_ns(d, "00:00"); m = (tape.ts - base)//S.NS//60
        sel = (m >= 570) & (m < 660)
        if not sel.any(): continue
        bars = []
        for k in np.unique(m[sel]):
            px = tape.px[m == k]; bars.append((int(k), float(px[0]), float(px.max()), float(px.min()), float(px[-1])))
        out.append((iso, atr, bars))
    json.dump(out, open(sys.argv[1], "w"))
    print(len(out), "days", flush=True)

if __name__ == "__main__":
    main()

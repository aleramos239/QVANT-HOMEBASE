#!/usr/bin/python3
"""Part 8: tick-level audit of the trade MFE/MAE used by the take / stop / breach rules. For a random sample of trades of each best single member,
recompute MFE and MAE from the raw tick tape between entry_ms and exit_ms (read-only) and compare with trades.json (mfe_pts, mae_pts, exit price)."""
import json, random, datetime as dt
import numpy as np
from pathlib import Path
from homebase.backtest.tape import TapeStore
import evalcore as E

R = Path(__file__).resolve().parent
res = json.load(open(R / "out/portfolio_results.json"))
ts = TapeStore()
rnd = random.Random(7)
members = {}
for node in (res["firms"], res["fast_objective"]["firms"]):
    for f, F in node.items():
        pool = {c["cid"]: c for c in F["pool"]}
        for lab in ("single", "portfolio"):
            for m in F["reports"][lab]["members"]:
                members[m["name"]] = pool[m["name"]]
print(len(members), "distinct best members")
tot = bad = skipped = 0
ALLD = []
worst = []
for name, c in sorted(members.items()):
    d = E._src_dir(c["src"])
    rows = json.loads((d / "trades.json").read_text())
    rows = rows if isinstance(rows, list) else rows["trades"]
    rows = [x for x in rows if x["date"] < "2025-01-01" and E.SESS and True]
    samp = rnd.sample(rows, min(40, len(rows)))
    by = {}
    for x in samp:
        by.setdefault(x["date"], []).append(x)
    n_ok = n_bad = 0
    diffs = []
    for date, xs in by.items():
        day = dt.date.fromisoformat(date)
        if not ts.cached("NQ", day):
            skipped += len(xs)
            continue
        tp = ts.load("NQ", day)
        t = np.frombuffer(tp.ts, dtype=np.int64)
        px = np.frombuffer(tp.px, dtype=np.float64)
        for x in xs:
            a, b = int(x["entry_ms"]) * 1_000_000, int(x["exit_ms"]) * 1_000_000 + 999_999
            i0, i1 = np.searchsorted(t, a, side="left"), np.searchsorted(t, b, side="right")
            if i1 <= i0:
                skipped += 1
                continue
            seg = px[i0:i1]
            sd = 1 if x["side"] == "long" else -1
            ep = float(x["entry_price"])
            mfe = max(0.0, (seg.max() - ep) if sd == 1 else (ep - seg.min()))
            mae = max(0.0, (ep - seg.min()) if sd == 1 else (seg.max() - ep))
            dm, da = mfe - float(x["mfe_pts"]), mae - float(x["mae_pts"])
            diffs.append((dm, da)); ALLD.append((name, x['date'], x['side'], x['exit_reason'], dm, da, float(x['mfe_pts']), float(x['mae_pts'])))
            ok = abs(dm) <= 0.25 + 1e-9 and abs(da) <= 0.25 + 1e-9
            n_ok += ok
            n_bad += (not ok)
    tot += n_ok + n_bad
    bad += n_bad
    if diffs:
        dd = np.array(diffs)
        worst.append((name, n_ok, n_bad, float(np.abs(dd[:, 0]).max()), float(np.abs(dd[:, 1]).max())))
import collections
ALL = []
print("trades audited", tot, "outside 1 tick:", bad, "skipped (no cached tape / no ticks):", skipped)
for w in worst:
    if w[2]:
        print("  BAD", w)
print("max |MFE diff| pts / max |MAE diff| pts over members:", max(w[3] for w in worst), max(w[4] for w in worst))

A = np.array([[r[4], r[5]] for r in ALLD])
print("n", len(A), "MFE diff (raw ticks - tester) pts: mean %.3f  p1 %.2f p50 %.2f p99 %.2f  frac tester MFE > raw by >0.25: %.3f  by >1: %.3f ; raw > tester by >0.25: %.3f" % (A[:,0].mean(), *np.percentile(A[:,0],[1,50,99]), (A[:,0]<-0.25).mean(), (A[:,0]<-1).mean(), (A[:,0]>0.25).mean()))
print("MAE diff (raw - tester) pts: mean %.3f p1 %.2f p50 %.2f p99 %.2f frac raw MAE > tester by >0.25: %.3f by >1: %.3f ; tester > raw by >0.25: %.3f" % (A[:,1].mean(), *np.percentile(A[:,1],[1,50,99]), (A[:,1]>0.25).mean(), (A[:,1]>1).mean(), (A[:,1]<-0.25).mean()))
import collections
c = collections.Counter(r[3] for r in ALLD if abs(r[4])>0.25 or abs(r[5])>0.25); print("exit reasons of off trades", c.most_common(5), "all", collections.Counter(r[3] for r in ALLD).most_common(5))
big = sorted(ALLD, key=lambda r: -abs(r[4]))[:6]
for r in big: print("  big MFE diff", r)

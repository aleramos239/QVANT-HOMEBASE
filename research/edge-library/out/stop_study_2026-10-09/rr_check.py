"""Read-only: every stored pipeline heat map (build days), per box: win rate, average trade, drawdown, steadiness, and the
eval odds the pipeline's own prop check gives it. Grouped by target size (reward : risk) and by stop size. Runs no strategy."""
import sys, json, glob, os, time, datetime as dt
import numpy as np
W = "/Users/ramoscapital/ramos-quant-homebase/research/edge-library"
sys.path[:0] = [W, W + "/engine"]
import library as L, l2sim as S
from blueprint import pipe_prop as PP
RUNS = os.path.expanduser("~/.homebase/pipeline/runs")
out, cals = [], {}
keys = sorted(os.path.basename(os.path.dirname(p)) for p in glob.glob(f"{RUNS}/*/run.json"))
t0 = time.monotonic()
for key in keys:
    if key.startswith("c1"): continue
    try:
        u = L.load_unit(key, RUNS)
    except Exception as e:
        continue
    m = u["meta"]; root = m.get("root")
    if m.get("family") == "random" or root not in ("NQ", "ES", "GC"): continue
    if root not in cals:
        cals[root] = [d.isoformat() for d in S.sessions(*S.period(S.ALLOW_BP), root, allow_holdout=S.ALLOW_BP)]
    for c in m["cells"]:
        x = L.unit_cell(u, c["id"]); net = np.asarray(x["net"], float); n = len(net)
        if n < 200: continue
        date = np.asarray(x["date"])
        days, inv = np.unique(date, return_inverse=True); daily = np.zeros(len(days)); np.add.at(daily, inv, net)
        cum = np.cumsum(daily); dd = float((np.maximum.accumulate(np.concatenate(([0.0], cum))) - np.concatenate(([0.0], cum))).max())
        ym = np.array([d.year * 12 + d.month for d in (dt.date.fromordinal(int(v)) for v in days)])
        mu, mi = np.unique(ym, return_inverse=True); mon = np.zeros(len(mu)); np.add.at(mon, mi, daily)
        run = best = 0
        for v in daily:
            run = run + 1 if v < 0 else 0; best = max(best, run)
        e = c["exit"]
        row = dict(key=key, root=root, tf=m.get("tf"), fam=m.get("family"), stop=f'{e["stop_mode"]}{e["stop_val"]:g}', tgt=e["tgt_r"], n=n, net=float(net.sum()),
                   avg=float(net.mean()), win=float((net > 0).mean()), dd=dd, months=float((mon > 0).mean()), lose_run=best,
                   risk=float(np.nanmedian(x["risk"])))
        if row["net"] > 0 and "--odds" in sys.argv:
            o = PP.odds(x, cals[root])
            row.update(ev=o["eval"], pay=o["payout"], size=o["size"])
        out.append(row)
    print(key, len(out), round(time.monotonic() - t0), "s", flush=True)
json.dump(out, open(sys.argv[1], "w"))
print("DONE", len(out))

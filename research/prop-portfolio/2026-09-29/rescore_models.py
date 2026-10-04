#!/usr/bin/python3
"""Re-score out/shortlist_all.csv rows (same rules, same trades, same calendar as a3p2_lp.task_fast) under the 'realized'
breach model and write out/shortlist_all_models.csv = the shortlist + realized p1/p2/p3/p5/bust5/med_days, the firm's
PRIMARY model and its P5, and check columns (recomputed eod / intraday P5 vs the stored ones; must be ~0).
Run: PYTHONPATH=~/ramos-quant-homebase /usr/bin/python3 rescore_models.py   (single process; sleeps through 09:18-09:36 ET)"""
import csv
import datetime as dt
import json
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalcore as E          # noqa: E402
import screen_analyze as SA   # noqa: E402
import a3_pass2 as A2         # noqa: E402

OUT = E.D / "out"
ET = ZoneInfo("America/New_York")
CELL = ("micros", "day_lock", "day_take", "day_stop", "max_day_tr", "target_take")


def gate():
    n = dt.datetime.now(ET)
    if n.weekday() < 5 and n.replace(hour=9, minute=18, second=0) <= n < n.replace(hour=9, minute=36, second=0):
        time.sleep((n.replace(hour=9, minute=36, second=5) - n).total_seconds())


def detail(o, d):
    ps, bs = o == 1, o == 2
    x = {f"p{k}": float((ps & (d <= k)).mean()) for k in (1, 2, 3, 5)}
    x["bust5"] = float(bs.mean())
    x["med_days"] = float(np.median(d[ps])) if ps.any() else float("nan")
    return x


def main():
    rows = list(csv.DictReader((OUT / "shortlist_all.csv").open()))
    srcs = {s[3]: s for s in A2.sources()}
    out, memo = [], {}
    for i, r in enumerate(rows):
        gate()
        f, key, sess = r["firm"], r["strategy_id"].split("|")[1], r["sess"]
        src, fam, tf, _, params = srcs[key]
        if src not in memo:
            t = A2.load_src(src)
            pl = A2.resolve(E.profile_from(fam, dict(params, tf=tf)))
            memo = {src: (t, SA.cal_for(t, A2.pool_of(pl["srcs"])))}
        t, cal = memo[src]
        port = A2.port_of(t, np.flatnonzero(t.sess == E.SESS_CODE[sess]), cal)
        rid, rl, dll = SA.firm(f)
        m, dl, dtk, ds, mt, tt = (int(float(r[c])) for c in CELL)
        A = A2.make_A(port, rl, dll, *A2.norm_walk(port, m, dl, dtk, ds, mt))
        idx5 = A2.idx5_of(len(cal))
        res = {b: detail(*E.race(idx5, A, rl, b, True, bool(tt))) for b in E.MODELS}
        row = dict(r)
        for k, v in res["realized"].items():
            row[f"real_{k}"] = v
        prim = E.primary_model(f)
        row["primary_model"], row["primary_p5"] = prim, res[prim]["p5"]
        row["check_eod_p5_diff"] = abs(res["eod"]["p5"] - float(r["eod_p5"]))
        row["check_intra_p5_diff"] = abs(res["intraday"]["p5"] - float(r["intra_same_p5"]))
        row["mono_ok"] = int(res["intraday"]["p5"] <= res["realized"]["p5"] + 1e-12 <= res["eod"]["p5"] + 2e-12)
        row["real_minus_intra_p5"] = res["realized"]["p5"] - res["intraday"]["p5"]
        row["eod_minus_real_p5"] = res["eod"]["p5"] - res["realized"]["p5"]
        out.append(row)
        if i % 20 == 0:
            print(i, f, key, sess, prim, f"eod {res['eod']['p5']:.3f} real {res['realized']['p5']:.3f} intra {res['intraday']['p5']:.3f}", flush=True)
    with (OUT / "shortlist_all_models.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print("wrote", OUT / "shortlist_all_models.csv", len(out))


if __name__ == "__main__":
    main()

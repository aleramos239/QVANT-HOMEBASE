#!/usr/bin/python3
"""Screen lift vs a DAY-MATCHED random control (evalcore.daymatched_controls). Run: /usr/bin/python3 (PYTHONPATH=repo).

  screen_lift_daymatched.py [--k 20] [--workers 8] [--min-trades 300]

Reads out/screen_table.csv (config run ids, best size per firm, old lift) + ledger.csv/jobs.jsonl (control pools) and writes
out/screen_lift_daymatched.csv: fam,tf,sess,firm,micros,... p5_cfg, ctrl_p5_mean/sd (K draws), lift, fallback_share, old lift.
Same rules as the screen (target_stop ON, eod breach, 1 size = the config's best size per firm)."""
from __future__ import annotations

import argparse
import csv
import sys
from multiprocessing import get_context
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalcore as E          # noqa: E402
import screen_analyze as SA   # noqa: E402

R = E.D                                  # the pilot's data dir (NQ: the code dir)
FS = {"lucid": "lu", "apex": "ap"}
_POOLS = {}


def _pool(srcs):
    k = tuple(srcs)
    if k not in _POOLS:
        _POOLS[k] = E.concat_tr([E.load(s) for s in srcs])
    return _POOLS[k]


def _ts(c, net0=None):
    n = len(c["date"])
    z = np.zeros(n)
    return SA.TS(c["date"], c["te"], c["tx"], c["side"], c["g"], c["mae"], c["risk"], z, c["sess"], np.zeros(n, np.int16))


def task(a):
    fam, tf, rows, K = a
    ts = SA.load_ts(rows[0]["run_id"])
    prof = E.profile_from(fam, {"tf": tf})
    res = E.resolve_pool(prof)
    out = []
    if not res["srcs"]:
        return out
    pool = _pool(res["srcs"])
    for row in rows:
        sess = row["sess"]
        m = ts.sess == E.SESS_CODE[sess]
        n = int(m.sum())
        if not n:
            continue
        cal = SA.cal_for(ts, pool)
        D = len(cal)
        ctl = E.daymatched_controls(ts, pool, K=K, mask=m, carry=("side", "g", "mae", "risk", "sess"))
        cfg_days = SA.eval_days(ts.days(m, cal), D, sizes={f: (int(float(row[f"{p}_best"])),) for f, p in FS.items()})
        ctl_days = []
        for c in ctl:
            t = _ts(c)
            ctl_days.append(SA.eval_days(t.days(np.ones(t.n, bool), cal), D, sizes={f: (int(float(row[f"{p}_best"])),) for f, p in FS.items()}))
        fb = float(np.mean([c["fb_share"] for c in ctl]))
        short = float(np.mean([c["short"] / max(1, c["n_cfg"]) for c in ctl]))
        td_ctl = float(np.mean([len(set(c["date"].tolist())) for c in ctl]))
        for f, p in FS.items():
            s = int(float(row[f"{p}_best"]))
            pc = np.array([d[(f, s)]["p"] for d in ctl_days])
            bc = np.array([d[(f, s)]["b"] for d in ctl_days])
            p_cfg = cfg_days[(f, s)]["p"]
            old_lift = float(row[f"{p}_lift"]) if row.get(f"{p}_lift", "") != "" else float("nan")
            out.append({
                "fam": fam, "tf": tf, "sess": sess, "firm": f, "micros": s, "trades": n,
                "trade_days": int(row["trade_days"]), "ctrl_trade_days": round(td_ctl, 1),
                "p5_cfg": p_cfg, "p5_cfg_screen": float(row[f"{p}_p5"]),
                "ctrl_p5_mean": float(pc.mean()), "ctrl_p5_sd": float(pc.std(ddof=1)) if len(pc) > 1 else float("nan"),
                "lift": p_cfg - float(pc.mean()),
                "ctrl_bust5_mean": float(bc.mean()), "bust5_cfg": cfg_days[(f, s)]["b"],
                "fallback_share": fb, "short_share": short,
                "old_ctrl_p5": float(row[f"{p}_ctrl_p5"]) if row.get(f"{p}_ctrl_p5", "") != "" else float("nan"),
                "old_lift": old_lift, "old_ctrl_trade_days": float(row["ctrl_trade_days"]) if row.get("ctrl_trade_days", "") != "" else float("nan"),
                "pool_exact": res["exact"], "pool_seeds": len(res["srcs"]), "pool_trades": int(pool.n),
                "pool_keys": "|".join(res["keys"][:1] + (["+%d" % (len(res["keys"]) - 1)] if len(res["keys"]) > 1 else [])),
                "pool_flag": res["flag"]})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=20)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--min-trades", type=int, default=300)
    ap.add_argument("--out", default=str(R / "out" / "screen_lift_daymatched.csv"))
    a = ap.parse_args(argv)
    rows = list(csv.DictReader((R / "out" / "screen_table.csv").open()))
    groups = {}
    for r in rows:
        if r["trades"] and int(r["trades"]) > 0:
            groups.setdefault((r["fam"], r["tf"]), []).append(r)
    tasks = [(f, t, v, a.k) for (f, t), v in sorted(groups.items(), key=lambda kv: -sum(int(r["trades"]) for r in kv[1]))]
    with get_context("spawn").Pool(a.workers) as pl:
        res = [x for chunk in pl.map(task, tasks, chunksize=1) for x in chunk]
    res.sort(key=lambda x: (x["fam"], int(x["tf"]), list(E.SESS).index(x["sess"]), x["firm"]))
    cols = list(res[0])
    with open(a.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, cols)
        w.writeheader()
        for x in res:
            w.writerow({c: (round(x[c], 6) if isinstance(x[c], float) else x[c]) for c in cols})
    big = [x for x in res if x["trades"] >= a.min_trades and x["old_lift"] == x["old_lift"]]
    for f in FS:
        b = [x for x in big if x["firm"] == f]
        ol, nl = np.array([x["old_lift"] for x in b]), np.array([x["lift"] for x in b])
        print(f"{f}: n={len(b)} old lift mean {ol.mean():+.3f} med {np.median(ol):+.3f} | new mean {nl.mean():+.3f} med {np.median(nl):+.3f} | "
              f"lift>0 old {int((ol > 0).sum())} new {int((nl > 0).sum())} | lift>2sd new {int(sum(x['lift'] > 2 * x['ctrl_p5_sd'] for x in b))} "
              f"| fallback mean {np.mean([x['fallback_share'] for x in b]):.3f} max {max(x['fallback_share'] for x in b):.3f}")
    print("cfg p5 vs screen p5 max abs diff:", max(abs(x["p5_cfg"] - x["p5_cfg_screen"]) for x in res))
    print("rows", len(res), "->", a.out)


if __name__ == "__main__":
    main()

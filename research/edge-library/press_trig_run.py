#!/usr/bin/env python3
"""press_trig_run.py -- ONE BOX of engine/press_trig.py per bar size, on the 3:1 in-sample months (owner 2026-10-27; no heat map, no test months).

    PY=<repo>/.venv-research/bin/python; cd research/edge-library
    $PY press_trig_run.py 1 3 5 15 [--lvl 25] [--tgt 0.5] [--t-end 15:00] [--workers 4] [--root NQ] [--sess globex] [--out DIR]

Box: pressure at +/-lvl at a tf close -> market, stop = the signal candle's other extreme (own x 1), target = tgt x the stop, entries until
t-end, every session flat at its end (the last 15:58 ET). Prints the house numbers (library.metrics: Sharpe over the traded days only) per
bar size, per year, and the trades as bundles under engine/out/press_trig/. Only the in-sample months are opened (ALLOW_WF_IS)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

W = Path(__file__).resolve().parent
for _p in (str(W), str(W / "engine")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import l2sim as S      # noqa: E402
import library as LB   # noqa: E402
from blueprint import hmwf, wfmonths  # noqa: E402
from press_trig import PressTrig  # noqa: E402


def box(a, tf: str) -> dict:
    return {"tf": tf, "sess": a.sess, "hold_to": "session", "stop_mode": a.stop, "stop_val": a.stop_val, "tgt_r": a.tgt, "lvl": a.lvl,
            "t_end": a.t_end, "max_tr": a.max_tr}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="press_trig_run.py")
    ap.add_argument("tfs", nargs="+", choices=("1", "3", "5", "15", "30"))
    ap.add_argument("--root", default="NQ")
    ap.add_argument("--sess", default="globex")
    ap.add_argument("--lvl", type=float, default=25.0)
    ap.add_argument("--tgt", type=float, default=0.5)
    ap.add_argument("--stop", default="own", choices=("own", "atr"), help="own = the signal candle's extreme x stop-val; atr = stop-val x ATR(14) of the bar")
    ap.add_argument("--stop-val", type=float, default=1.0)
    ap.add_argument("--t-end", default="15:00")
    ap.add_argument("--max-tr", type=int, default=20)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--days", type=int, default=0, help="a smoke run on the first N in-sample days (0 = all)")
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    days = wfmonths.is_days(a.root)
    days = days[:a.days] if a.days else days
    print(f"{a.root}: {len(days)} in-sample days {days[0]} .. {days[-1]}")
    for tf in a.tfs:
        res = S.run(PressTrig, box(a, tf), root=a.root, days=days, workers=a.workers, allow_holdout=S.ALLOW_WF_IS)
        tr = res["trades"]
        print(f"\n== {a.root} {tf}m  sessions {res['sessions']} used {res['used']} dropped by error {res['skipped_by_error']}  trades {len(tr)}")
        if res["skipped_by_error"]:
            print("   NOT CLEAN:", [r for r in res["no_trade"] if "error" in str(r)][:3])
        if not tr:
            continue
        x = LB.pack(tr)
        n = hmwf.numbers(x, days)
        print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in n.items()})
        for r in LB.per_year(x, days):
            print(f"   {r['period']}: {r['trades']} trades, net {r['net']:,.0f}, win {r['win']:.1%}, PF {r['pf']}, Sharpe {r['sharpe']}")
        if a.out:
            tag = "" if a.stop == "own" and a.stop_val == 1.0 else f"-{a.stop}{a.stop_val:g}"
            S.write_bundle(res, W / "engine" / "out" / "press_trig" / f"{a.root}-tf{tf}-l{a.lvl:g}-r{a.tgt:g}{tag}", f"press_trig-{a.root}-tf{tf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

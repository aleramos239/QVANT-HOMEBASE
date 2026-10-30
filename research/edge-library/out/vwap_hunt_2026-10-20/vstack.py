"""VWAP hunt 2026-10-20: the STACK (PREREG.md section 6) -- passing versions merged one position at a time on EVERY OOS month.

    vstack.py store|cell|group [store|cell|group ...] [--json out.json]
Each version's OOS trades (every OOS month, nothing stands aside; exit = entry + dur_s). All legs by entry time; a trade whose entry
falls while a stacked trade is open is skipped (first signal wins). Judged: trades a day on the OOS sessions, P1 (win vs break-even
+ 3 points), P2 (net > 0, and at +1 tick a side), P5 (fresh months net > 0). Nothing is run or tuned (stack.py of hunt_2026-10-20,
adapted: every month traded, no pick)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import versions as V  # noqa: E402


def leg(Sx: dict, c: str, g: str) -> list:
    x = Sx["cells"][c]
    m = np.array([V.month_kind(mo) == "oos" for mo in x["month"]], bool) & (x["group"] == g)
    return [{"entry": int(e), "exit": int(e) + int(d) * 1000, "net": float(n), "month": str(mo), "leg": f"{Sx['name']}|{c}|{g}"}
            for e, d, n, mo in zip(x["entry_ms"][m], x["dur_s"][m], x["net"][m], x["month"][m])]


def judge(ts: list, days: int) -> dict:
    net = np.array([t["net"] for t in ts])
    wr = V.G.wr_rr(net)
    fresh = [t for t in ts if t["month"] in V.FRESH]
    return {"trades": len(ts), "per_day": round(len(ts) / days, 2), "net": round(float(net.sum())), "avg": round(float(net.mean()), 1) if len(net) else None,
            "win": round(float((net > 0).mean()), 4) if len(net) else None, "need": wr.get("need"), "P1": bool(wr["passed"]),
            "P2": bool(net.sum() > 0 and net.sum() - V.TICK_RT * len(net) > 0), "net_tick": round(float(net.sum() - V.TICK_RT * len(net))),
            "fresh_net": round(sum(t["net"] for t in fresh)), "fresh_trades": len(fresh), "P5": sum(t["net"] for t in fresh) > 0}


def main(argv: list) -> None:
    js = None
    if "--json" in argv:
        i = argv.index("--json")
        js, argv = argv[i + 1], argv[:i] + argv[i + 2:]
    cache, legs = {}, {}
    for k in argv:
        n, c, g = k.split("|")
        Sx = cache.setdefault(n, V.store(n))
        legs[k] = leg(Sx, c, g)
    days = V.sessions_in(next(iter(cache.values())), "oos")
    allt = sorted((t for ts in legs.values() for t in ts), key=lambda t: (t["entry"], t["leg"]))
    taken, busy = [], 0
    for t in allt:
        if t["entry"] < busy:
            continue
        taken.append(t)
        busy = t["exit"]
    res = {"oos_sessions": days, "legs": {k: judge(ts, days) for k, ts in legs.items()}, "stack": judge(taken, days),
           "skipped": len(allt) - len(taken), "taken_by_leg": {k: sum(1 for t in taken if t["leg"] == k) for k in legs},
           "by_month": {m: round(sum(t["net"] for t in taken if t["month"] == m)) for m in sorted({t["month"] for t in taken})}}
    for k, s in res["legs"].items():
        print(f"leg {k:70} {s}")
    print(f"STACK ({res['skipped']} skipped): {res['stack']}")
    print(f"by month: {res['by_month']}")
    if js:
        Path(js).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])

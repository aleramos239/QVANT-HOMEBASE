"""COUNTS-ONLY smoke of the new_l2 group on the 10 fixed BUILD smoke days (run_menus.SMOKE_DAYS), <= 2 workers.

  1. run_menus.smoke of the registered families D1 / D5 (the whole menu grid, sess all / pre / eve, C2 null, 1- vs 2-worker parity)
  2. every stage D variant (l2ideas.STAGE_D) next to its base, two menu cells per registered variant, as run_menus runs a
     cell (sess all / pre / eve): KEPT trades (l2ideas.kept), sides, sessions, days with a trade, dropped sessions, both-side
     evidence; for the entry filters the fills before the filter, what the book said at the START OF THE FILL'S MINUTE (by
     row stamp) and how many kept trades are the base's own trade; 1- vs 2-worker parity; the C2 null runs.
Never prints or stores P&L, exit reasons or win rates. Writes engine/out/new_l2_smoke.log. Nothing is counted in the ledger.

    cd engine && "~/ONYX TRADING/.venv/bin/python" out/fix_new_l2/stage_d_smoke.py
"""
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

E = Path(__file__).resolve().parents[2]
for p in (str(E), str(E.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

import families                      # noqa: E402
import l2sim as S                    # noqa: E402
import run_menus as RM               # noqa: E402
from families import l2ideas as L2   # noqa: E402

DAYS = list(RM.SMOKE_DAYS)
MENU_IDS = ("atr3-r0", "pts20-r1")
COLS = ("imb10", "bid10_rel15", "ask10_rel15", "t_utc")
KEY = ("date", "side", "qty", "entry_price", "order_price", "sl", "tp", "entry_ms")
NS, MIN = S.NS, S.MIN_NS


def specs(name: str, tf: str) -> list:
    grid = families.unit_grid(name, "NQ", tf) if name in families.LIBRARY else L2.variant_grid(name, "NQ", tf)
    cells = [c for c in grid if c["id"].endswith(MENU_IDS)]
    return [(c["id"], sp) for c in cells for sp in RM.cell_specs(c)]


def mean5(tab, now_ns):
    m = (now_ns // NS // 60 - 1) * 60
    idx = [tab["row"].get(m - 60 * k) for k in range(4, -1, -1)]
    if None in idx:
        return None
    v = tab["imb10"][idx].astype(np.float64)
    return float(np.mean(v)) if np.isfinite(v).all() else None


def thin(tab, now_ns, sd):
    i = tab["row"].get((now_ns // NS // 60 - 1) * 60)
    v = None if i is None else float(tab["ask10_rel15" if sd > 0 else "bid10_rel15"][i])
    return None if v is None or v != v else bool(1.0 + v <= 0.8 + 1e-6)


def main() -> int:
    S.wait_compute_window()
    out = [f"# new_l2 smoke, {dt.datetime.now().astimezone().isoformat(timespec='seconds')}, days {DAYS} (BUILD), <= 2 workers; "
           "COUNTS ONLY"]
    ok = True
    for name, tf in (("bimb_follow_d1", "5"), ("flow_exhaust", "1"), ("flow_exhaust", "5")):
        o = RM.smoke(name, "NQ", tf, 10, 1)
        ok &= o["ok"]
        out.append(json.dumps(o))
    loader = S.L2Features(COLS)
    tabs = {}
    for iso in DAYS:
        f = loader(S._date(iso))
        tabs[iso] = {"row": {int(t): i for i, t in enumerate(f.cols["t_utc"])}, **f.cols}
    plan = []
    for base in L2.BREAKOUT_BASES:
        tf = "30" if base.startswith("straddle_t") else "5"
        for name in (base, base + "_fbook", base + "_thin", base + "_xbook"):
            plan += [(name, tf, cid, sp) for cid, sp in specs(name, tf)]
    res = S.run_many([x[3] for x in plan], days=DAYS, workers=2, features=loader)
    one = S.run_many([x[3] for x in plan[::3]], days=DAYS, workers=1, features=loader)         # parity on every third instance
    c2 = S.run_many([x[3] for x in plan if x[0] in L2.STAGE_D], days=DAYS, workers=2, features=__import__("score").C2Features(COLS, seed=1))
    parity = all(a["trades"] == b["trades"] for a, b in zip(res[::3], one))          # the raw rows, verdict tags included
    raw_n = Counter()
    for (name, *_), r in zip(plan, res):
        raw_n[name] += len(r["trades"])
    for r in res + c2:
        r["trades"] = L2.kept(r["trades"])             # stage D reports the kept trades (a refused fill is a skipped trade)
    by, base_tr = {}, {}
    for (name, tf, cid, (cls, p)), r in zip(plan, res):
        by.setdefault(name, []).append((tf, cid, p, r))
        if name in families.LIBRARY:
            base_tr.setdefault((name, cid, p.get("sess")), set()).update(tuple(t[k] for k in KEY) for t in r["trades"])
    c2n = Counter()
    for (name, *_), r in zip([x for x in plan if x[0] in L2.STAGE_D], c2):
        c2n[name] += len(r["trades"])
        ok &= r["skipped_by_error"] == 0
    for name, rows in by.items():
        tr = [t for *_, r in rows for t in r["trades"]]
        o = {"name": name, "tf": rows[0][0], "cells": len({c for _, c, _, _ in rows}), "trades": len(tr),
             "skipped_by_error": sum(r["skipped_by_error"] for *_, r in rows),
             "long": sum(t["side"] == "long" for t in tr), "short": sum(t["side"] == "short" for t in tr),
             "by_session": dict(Counter(S.session_of(t["entry_ms"]) or "none" for t in tr)),
             "days_with_trades": len({t["date"] for t in tr}), "sessions": rows[0][3]["sessions"], "used": rows[0][3]["used"],
             "entry_kind": {"market": sum(t["order_price"] is None for t in tr), "resting": sum(t["order_price"] is not None for t in tr)},
             "oco_fills": sum(bool(t["oco"]) for t in tr), "both_sides_sessions": max(r["both_sides_sessions"] for *_, r in rows)}
        ok &= o["skipped_by_error"] == 0
        if name in L2.STAGE_D:
            v = L2.variant(name)
            o.update(stage_d=v["spec"], strategy=rows[0][3]["meta"]["strategy"], c2_seed1_trades=c2n[name],
                     fills_before_the_filter=raw_n[name])
            if v["suffix"] in ("fbook", "thin"):
                bad = none = same = 0
                for tf, cid, p, r in rows:
                    for t in r["trades"]:
                        sd = 1 if t["side"] == "long" else -1
                        tab = tabs[t["date"]]
                        e = t["entry_ms"] * 1_000_000
                        if v["suffix"] == "fbook":
                            m = mean5(tab, e)
                            none, bad = none + (m is None), bad + bool(m is not None and m * sd < 0)
                        else:
                            th = thin(tab, e, sd)
                            none, bad = none + (th is None), bad + (th is False)
                        same += tuple(t[k] for k in KEY) in base_tr[(v["base"], cid, p.get("sess"))]
                o.update(against_the_filter_at_the_fill_minute=bad, no_signal_at_the_fill_minute=none, trades_that_are_the_bases_trade=same)
        out.append(json.dumps(o))
    out.append(json.dumps({"worker_parity_1_vs_2": parity, "specs": len(plan), "parity_specs": len(one), "ok": bool(ok and parity)}))
    (E / "out" / "new_l2_smoke.log").write_text("\n".join(out) + "\n")
    print(out[-1])
    return 0 if ok and parity else 1


if __name__ == "__main__":
    sys.exit(main())

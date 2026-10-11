"""Manual-lane read of the TEST DAYS (2025-07-01 .. the last complete session on disk) for ONE manual spec, once, on the owner's word.

    <venv-python> manual_lane/test_read.py SPEC.json OUT_DIR --name IDEA --confirm [--box CELL_ID --size MICROS] [--workers N]

The spec is run_idea's format (the files of manual_lane/specs, time stops included). This is the blueprint's own read (runner.run_test: the
engine's test switch, the locked-variant table, the same with worse fills, a 10-seed random-entry pool), minus the card, the lock and the nine
lines 4.1-4.9 -- a manual-lane spec has none of them. It is claimed in the app's one-read log BEFORE a day is opened (a second read of the same
name is refused), judged after, and labelled MANUAL-LANE READ: it cannot prove an idea. Without --confirm it only shows what would be read.
After the read: per cell trades / net / profit factor at --size micros, the average of all cells, and the prop sim (the pipeline's account,
plain row, open losses counted) of --box at every size. Writes OUT_DIR/<name>_test_read.json and prints a short text.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parent / "engine")]

import library as LB  # noqa: E402
from blueprint import api  # noqa: E402
from blueprint import pipe_rules as PR  # noqa: E402
from blueprint import propodds as PO  # noqa: E402
from blueprint import runner as RUN  # noqa: E402

RI = RUN.RI
S = RUN.S


def odds(x: dict, size: int, r: dict, cal: list, idx, N: int) -> dict:
    """The plain row and the stress row of a trade list at `size` micros: pass within 5 / 10 / N days, bust, median pass day."""
    de = min(N, int(r.get("max_days") or N))
    net, traded, opn, _ = PO.days(PO.ledger(x, size, r), r, cal)
    out = {}
    wnet, wopn = PO.worse(net, traded, opn)
    for tag, (a, t, o) in (("plain", (net, traded, opn)), ("stress", (wnet, traded, wopn))):
        e = PO.eval_walk(a[idx][:, :de], t[idx][:, :de], o[idx][:, :de], r)
        win, day = e["outcome"] == PO.PASS, e["day"]
        n = idx.shape[0]
        out[tag] = {"p5": float((win & (day <= 5)).sum()) / n, "p10": float((win & (day <= 10)).sum()) / n, f"p{N}": float((win & (day <= N)).sum()) / n,
                    "bust": float(((e["outcome"] == PO.BUST) & (day <= N)).sum()) / n,
                    "median_day": float(np.median(day[win & (day <= N)])) if (win & (day <= N)).any() else None}
    return out


def report(store: Path, cal: list, box: str, size: int, account: str, N: int) -> dict:
    u = LB.load_unit(store.name, store.parent)
    PS = PO.app()
    r = PS.load_rules(account)
    idx = PO.draws(len(cal), int(PS.N_PATHS), max(N, PO.horizon(r)), int(PS.SEED))[:, :N]
    cells, rows = u["meta"]["cells"], []
    for i, c in enumerate(cells):
        x = LB.unit_cell(u, i)
        n = len(x["net"])
        if not n:
            rows.append({"id": c["id"], "trades": 0})
            continue
        z = PO.sized(x, size)
        net = np.asarray(z["net"], np.float64)
        gp, gl = float(net[net > 0].sum()), float(-net[net < 0].sum())
        one = np.asarray(x["net"], np.float64)
        rows.append({"id": c["id"], "variant": c["variant"], "exit": c["exit"], "trades": int(n), "net_one": float(one.sum()), "avg_one": float(one.mean()),
                     "win": float((net > 0).mean()), "net": float(net.sum()), "avg": float(net.mean()), "pf": gp / gl if gl else None})
    out = {"cells": rows, "size": size, "box": box, "days": len(cal), "account": account, "N": N}
    live = [x for x in rows if x["trades"]]
    out["average"] = {"cells": len(live), "profitable_share": float(np.mean([x["net"] > 0 for x in live])) if live else None,
                      "avg_net_at_size": float(np.mean([x["net"] for x in live])) if live else None,
                      "avg_trade_one_contract": float(np.mean([x["avg_one"] for x in live])) if live else None}
    for body in sorted({x["variant"]["body_r"] for x in live}):
        sub = [x for x in live if x["variant"]["body_r"] == body]
        out["average"][f"body_{body}"] = {"cells": len(sub), "profitable_share": float(np.mean([x["net"] > 0 for x in sub])),
                                          "avg_net_at_size": float(np.mean([x["net"] for x in sub]))}
    bi = next((i for i, c in enumerate(cells) if c["id"] == box), None)
    if bi is not None and len(LB.unit_cell(u, bi)["net"]):
        x = LB.unit_cell(u, bi)
        cap = int(r.get("cap_micros") or 40)
        out["box_sizes"] = {str(s): odds(x, s, r, cal, idx, N) for s in range(1, cap + 1) if s in (5, 8, 10, 12, 15, 16, 17, 18, 20, 25, 30, 40)}
        out["box_at_size"] = out["box_sizes"].get(str(size)) or odds(x, size, r, cal, idx, N)
        d = np.asarray(x["date"], np.int64)
        z = PO.sized(x, size)
        byq = {}
        for k, v in zip(d, np.asarray(z["net"], np.float64)):
            import datetime as dt
            dd = dt.date.fromordinal(int(k))
            byq[f"{dd.year}-Q{(dd.month - 1) // 3 + 1}"] = byq.get(f"{dd.year}-Q{(dd.month - 1) // 3 + 1}", 0.0) + float(v)
        out["box_by_quarter"] = byq
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("spec")
    ap.add_argument("out")
    ap.add_argument("--name", required=True, help="the idea's name in the one-read log")
    ap.add_argument("--confirm", action="store_true", help="the owner has said to read the test days: it cannot be taken back")
    ap.add_argument("--box", default=None, help="the cell id the owner's box is (prop sim at every size)")
    ap.add_argument("--size", type=int, default=17)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--root", default="NQ")
    ap.add_argument("--report-only", action="store_true", help="re-read the stores of a read that is already judged (no days opened)")
    a = ap.parse_args(argv)
    spec_json = json.loads(Path(a.spec).read_text())
    sp = RUN.checked(a.spec)
    u = next((x for x in RI.spec_units(sp) if x["root"] == a.root and not x["filter"]), None)
    sess = sp["sessions"][0]
    rng = RUN.test_range(a.root)
    variants = [c["id"] for c in u["grid"]]
    lock = hashlib.sha256(json.dumps(spec_json, sort_keys=True).encode()).hexdigest()[:16]
    read = {"version": 1, "lock": lock}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    ledger = out / "ledger.csv"
    IS = api.ideastore()
    window = {"start": rng["start"], "end": rng["end"]}
    store = u["key"]
    print(f"{a.name}: {len(variants)} cells, test days {rng['start']} .. {rng['end']} ({rng['sessions']} sessions), lock {lock}")
    if not a.report_only:
        if not a.confirm:
            RUN.run_test(a.name, read, sp, u["key"], sess, variants, store, rng["end"], a.workers, out, ledger=ledger, dry=True)
            print("dry run only: pass --confirm to read the test days (ONE read, logged before the days are opened)")
            return 0
        IS.claim_read(a.name, version=1, lock=lock, rng=window)
        try:
            got = RUN.run_test(a.name, read, sp, u["key"], sess, variants, store, rng["end"], a.workers, out, ledger=ledger)
        except BaseException as e:                       # the read stays on file, claimed: never run again
            print(f"READ DID NOT FINISH ({type(e).__name__}: {e}); the claim stays on file")
            raise
        IS.log_read(a.name, version=1, lock=lock, rng=window, state="judged",
                    verdict="MANUAL-LANE READ: no card, no lock, no lines 4.1-4.9; cannot prove the idea")
        cal = got["calendar"]
    else:
        cal = [d.isoformat() for d in S.sessions(S._date(rng["start"]), S._date(rng["end"]), a.root, allow_holdout=S.ALLOW_BT)]
    need = PR.need("prop")
    res = report(out / f"{u['key']}-{sess}-test", cal, a.box or "", a.size, need["account"], int(need["days"]))
    res["range"] = window
    (out / f"{a.name}_test_read.json").write_text(json.dumps(res, indent=1, default=float))
    print(f"ok -> {out / (a.name + '_test_read.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

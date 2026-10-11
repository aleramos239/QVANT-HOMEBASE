"""Eval scan: the prop sim of EVERY cell of one or more manual-lane stores, on the whole build days and on a 75 / 25 split of them.

    <venv-python> manual_lane/eval_scan.py OUT.json LABEL=STORE_DIR [LABEL=STORE_DIR ...] [--risk-cap USD] [--workers N] [--account RULE_FILE] [--days N]

Per cell and per period (`all` = the build days; `first` = the first 75 % of the session days; `last` = the last 25 %): trades, net, average trade, win
rate, and the plain-row eval odds of the account (blueprint.propodds' walks, open losses counted, whole micros 1 .. the account's maximum, only sizes whose
stop risks no more than --risk-cap dollars a trade): the share of paths that PASS on or before day 5 / 10 / 20 / N, the bust share within N days, the
median day of a pass, at the size with the highest odds within N days (equal odds = the smaller size). A cell's stop risk is its 90th-percentile stop
distance x the micro's point value. The page that reads it ranks cells by their AVERAGE with their neighbours (the plateau), never by one cell.
Account / N default to pipeline.json prop.account / prop.days. Build days only: it never reads the test days.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parent / "engine")]

import library as LB  # noqa: E402
from blueprint import pipe_rules as PR  # noqa: E402
from blueprint import propodds as PO  # noqa: E402

KS = (5, 10, 20)
_G: dict = {}


def _slice(x: dict, lo: int, hi: int) -> dict:
    """The trades of a cell whose date ordinal is in [lo, hi] (every packed array of the cell is one entry a trade)."""
    d = np.asarray(x["date"], np.int64)
    m = (d >= lo) & (d <= hi)
    return {k: (np.asarray(v)[m] if hasattr(v, "__len__") and len(v) == len(d) else v) for k, v in x.items()}


def scan_cell(job) -> dict:
    """job = (label, store dir, cell index) -> the cell's record. Runs in a worker: the unit and the rules are loaded once a process."""
    label, store, i = job
    g = _G
    u = g["units"].get(store)
    if u is None:
        p = Path(store)
        u = g["units"][store] = LB.load_unit(p.name, p.parent)
    c = u["meta"]["cells"][i]
    x = LB.unit_cell(u, i)
    r, PS, N, cap_usd = g["r"], g["PS"], g["N"], g["risk_cap"]
    out = {"label": label, "id": c["id"], "variant": c["variant"], "exit": c["exit"]}
    if not len(x["net"]):
        return {**out, "periods": {}}
    risk_micro = float(np.percentile(np.asarray(x["risk"], np.float64), 90)) * g["pv"]
    out["risk_micro"] = risk_micro
    cap_micros = int(r.get("cap_micros") or 40)
    sizes = [s for s in range(1, cap_micros + 1) if s * risk_micro <= cap_usd or s == 1]
    de = min(N, int(r.get("max_days") or N))
    res = {}
    for name, (lo, hi, cal) in g["periods"].items():
        xs = _slice(x, lo, hi)
        n = len(xs["net"])
        if not n:
            res[name] = {"trades": 0}
            continue
        net1 = np.asarray(xs["net"], np.float64)
        rec = {"trades": int(n), "net": float(net1.sum()), "avg": float(net1.mean()), "win": float((net1 > 0).mean()), "size": None}
        idx = PO.draws(len(cal), int(PS.N_PATHS), max(N, PO.horizon(r)), int(PS.SEED))[:, :N]
        best = None
        for size in sizes:
            net, traded, opn, _ = PO.days(PO.ledger(xs, size, r), r, cal)
            e = PO.eval_walk(net[idx][:, :de], traded[idx][:, :de], opn[idx][:, :de], r)
            win = e["outcome"] == PO.PASS
            day = e["day"]
            p_n = float((win & (day <= N)).sum()) / idx.shape[0]
            if best is None or p_n > best[0]:
                nn = int((win & (day <= N)).sum())
                best = (p_n, size, {"p": {str(k): float((win & (day <= k)).sum()) / idx.shape[0] for k in KS + (N,)},
                                    "bust": float(((e["outcome"] == PO.BUST) & (day <= N)).sum()) / idx.shape[0],
                                    "median_day": float(np.median(day[win & (day <= N)])) if nn else None})
        rec.update(size=best[1], risk=best[1] * risk_micro, **best[2])
        res[name] = rec
    return {**out, "periods": res}


def _init(account: str, days: int, risk_cap: float, root: str, split_frac: float) -> None:
    import l2sim
    PS = PO.app()
    r = PS.load_rules(account)
    cal = [d.isoformat() for d in l2sim.sessions(*l2sim.period("bp_build"), root, allow_holdout=l2sim.ALLOW_BP)]
    k = int(round(len(cal) * split_frac))
    import datetime as dt
    ordn = [dt.date.fromisoformat(d).toordinal() for d in cal]
    _G.update(units={}, r=r, PS=PS, N=days, risk_cap=risk_cap, pv=l2sim.SPECS[root][0] / LB.MICRO_DIV,
              periods={"all": (ordn[0], ordn[-1], cal), "first": (ordn[0], ordn[k - 1], cal[:k]), "last": (ordn[k], ordn[-1], cal[k:])},
              split={"first_end": cal[k - 1], "last_start": cal[k], "days": [k, len(cal) - k]})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out")
    ap.add_argument("stores", nargs="+", help="LABEL=STORE_DIR")
    ap.add_argument("--risk-cap", type=float, default=1000.0)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--account", default=None)
    ap.add_argument("--days", type=int, default=None)
    ap.add_argument("--root", default="NQ")
    ap.add_argument("--split", type=float, default=0.75)
    a = ap.parse_args(argv)
    need = PR.need("prop")
    account, days = a.account or need["account"], int(a.days or need["days"])
    jobs = []
    for s in a.stores:
        label, _, path = s.partition("=")
        u = LB.load_unit(Path(path).name, Path(path).parent)
        jobs += [(label, path, i) for i in range(len(u["meta"]["cells"]))]
    args = (account, days, a.risk_cap, a.root, a.split)
    with ProcessPoolExecutor(max_workers=a.workers, initializer=_init, initargs=args) as ex:
        cells = list(ex.map(scan_cell, jobs, chunksize=8))
    _init(*args)
    meta = {"account": account, "days": days, "risk_cap": a.risk_cap, "split": _G["split"], "stores": a.stores}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"meta": meta, "cells": cells}, default=float))
    print(f"ok: {len(cells)} cells -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

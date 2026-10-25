"""plan_scan -- WHICH STORED RULES FIT JJ SIMON'S $1,000 PLAN (the owner, 2026-10-19: "find me the strategy/algos that fits the $1000 plan").

Every stored build-day run (research/edge-library/runs_bp/*, ~/.homebase/taught/*/runs/*; the random controls skipped) is read cell by
cell; a cell with enough trades and a profit factor near break-even or better (the pre-filter: a plan cannot pay out of a ledger that
loses hard) goes through jj_fifty_accounts.fifty(): 50 accounts on 50 spread start days, real days in order, eval -> funded -> every
payout, the rule file's own rules (Lucid Flex 25K with the daily loss limit, UNCONFIRMED numbers), at k micros, payouts x 0.9 minus
50 fees. The output is a ranked table: the cells whose payouts beat the fees, with their trades a day, win rate and net per trade.

In-sample (the build days): a cell that fits here is a candidate for `taught run` + the 3:1 walk-forward, nothing more.
Run: .venv-research/bin/python research/edge-library/taught/plan_scan.py [--min-trades 300] [--min-pf 0.95] [--micros 5,10]
     [--fee 50,70] [--workers 3] [--out FILE.json] [--limit N]"""
from __future__ import annotations

import argparse
import csv
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[3]))

import jj_fifty_accounts as F                                  # noqa: E402
from homebase.backtest import propsim as P                     # noqa: E402

ROOTS = [HERE.parents[1] / "runs_bp", Path.home() / ".homebase" / "taught"]
SKIP = ("c1-", "__ctl", "random")


def stores() -> list[Path]:
    out = []
    for root in ROOTS:
        if root.name == "taught":
            out += [p for p in root.glob("*/runs/*/cells.npz")]
        else:
            out += [p for p in root.glob("*/cells.npz")]
    out = [p.parent for p in out if not any(s in p.parent.name for s in SKIP)]
    return sorted(out)


def _cells(store: Path, min_trades: int, min_pf: float) -> list[dict]:
    rows = [r for r in csv.DictReader(open(store / "table.csv")) if r["sess"] == "all"]
    keep = []
    for r in rows:
        try:
            n, pf = int(r["trades"]), float(r["pf"])
        except ValueError:
            continue
        if n >= min_trades and pf >= min_pf:
            keep.append(r)
    return keep


def _run(args):
    store, min_trades, min_pf, micros, fees, rule_id = args
    store = Path(store)
    r = P.load_rules(rule_id)
    out = []
    try:
        rows = _cells(store, min_trades, min_pf)
    except FileNotFoundError:
        return out
    for row in rows:
        try:
            base = F.ledger(store, row["cell"])
        except (ValueError, KeyError, IndexError):
            continue
        if not base:
            continue
        days = len({t["date"] for t in base})
        span = max(1, (F.dt.date.fromisoformat(base[-1]["date"]) - F.dt.date.fromisoformat(base[0]["date"])).days * 5 / 7)
        wins = sum(1 for t in base if t["net"] > 0)
        rec = {"store": store.name, "where": store.parents[1].name if store.parents[0].name == "runs" else "runs_bp", "cell": row["cell"],
               "trades": len(base), "per_day": len(base) / span, "win": wins / len(base), "avg": sum(t["net"] for t in base) / len(base),
               "first": base[0]["date"], "last": base[-1]["date"], "sizes": {}}
        for m in micros:
            res = F.fifty(F.resize(base, m, 1.0), r, 50, 120, 5)
            take = res["gross_payouts"] * 0.9
            rec["sizes"][m] = {"passed": res["passed"], "paid": res["paid"], "payouts": res["payouts"], "take": take,
                               "net": {f: take - f * 50 for f in fees}}
        best = max(rec["sizes"].items(), key=lambda kv: kv[1]["net"][fees[0]])
        rec["best_micros"], rec["best_net"] = best[0], best[1]["net"][fees[0]]
        out.append(rec)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--min-trades", type=int, default=300)
    ap.add_argument("--min-pf", type=float, default=0.95)
    ap.add_argument("--micros", default="5,10")
    ap.add_argument("--fee", default="50,70")
    ap.add_argument("--rules", default="lucid-flex-25k-dll@2026-10-19")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    micros = [int(x) for x in a.micros.split(",")]
    fees = [float(x) for x in a.fee.split(",")]
    st = stores()
    if a.limit:
        st = st[: a.limit]
    print(f"{len(st)} stores; rule {a.rules}; cells with >= {a.min_trades} trades and PF >= {a.min_pf}; micros {micros}; fees {fees}", flush=True)
    t0, recs = time.time(), []
    with mp.get_context("fork").Pool(a.workers) as pool:
        for i, out in enumerate(pool.imap_unordered(_run, [(str(s), a.min_trades, a.min_pf, micros, fees, a.rules) for s in st]), 1):
            recs += out
            if i % 50 == 0:
                print(f"  {i} of {len(st)} stores, {len(recs)} cells tested, {time.time() - t0:.0f} s", file=sys.stderr, flush=True)
    recs.sort(key=lambda x: -x["best_net"])
    fits = [x for x in recs if x["best_net"] > 0]
    print(f"{len(recs)} cells tested, {len(fits)} with payouts above the fees at ${fees[0]:.0f} (best size of {micros})")
    print(f"{'store':44} {'cell':22} {'tr':>5} {'/day':>5} {'win':>6} {'avg':>6} {'mic':>3} {'pass':>4} {'paid':>4} {'pay':>4} "
          + " ".join(f"net@{f:.0f}" for f in fees))
    for x in recs[:60]:
        s = x["sizes"][x["best_micros"]]
        print(f"{x['store'][:44]:44} {x['cell'][:22]:22} {x['trades']:>5} {x['per_day']:>5.1f} {100 * x['win']:>5.1f}% {x['avg']:>6.0f} "
              f"{x['best_micros']:>3} {s['passed']:>4} {s['paid']:>4} {s['payouts']:>4} " + " ".join(f"{s['net'][f]:>7,.0f}" for f in fees))
    if a.out:
        Path(a.out).write_text(json.dumps({"rules": a.rules, "micros": micros, "fees": fees, "cells": recs}, indent=0, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

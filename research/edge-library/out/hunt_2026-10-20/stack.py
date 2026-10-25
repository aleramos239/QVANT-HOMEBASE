"""Hunt 2026-10-20, Gate 3: stack the legs' OWN 3:1 walk-forward test-month trades, one position open at a time (PREREG.md).

Run: .venv-research/bin/python research/edge-library/out/hunt_2026-10-20/stack.py leg1 leg2 ... [--json out.json]
Each leg = a taught sheet name with wf/result.json on file. A leg's walk-forward trades: every test month = the trades of that month's
picked cell (build-day months from the build store's cells.npz, months from 2025-07 from wf/test_cells.npz), as
taught/jj_fifty_accounts.wf_ledger, plus exit = entry + dur_s. Merge: all legs' trades by entry time; a trade whose entry falls
while another stacked trade is still open is skipped (first signal wins). Nothing is re-run; nothing is tuned."""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
import zoneinfo
from pathlib import Path

import numpy as np

ROOT = Path.home() / ".homebase" / "taught"
NY = zoneinfo.ZoneInfo("America/New_York")
BLIND = "2025-07"
CUSHION = 0.03


def _store_rows(store: Path, cell: str) -> list[dict]:
    z = np.load(store / "cells.npz", allow_pickle=True)
    cells = [r["cell"] for r in csv.DictReader(open(store / "table.csv")) if r["sess"] == "all"]
    i = cells.index(cell)
    a, b = int(z["off"][i]), int(z["off"][i + 1])
    e, d, n, mae = z["entry_ms"], z["dur_s"], z["net"], z["mae"]
    rk = z["risk"] if "risk" in z.files else None
    return [{"entry_ms": int(e[j]), "exit_ms": int(e[j]) + int(d[j]) * 1000, "net": float(n[j]), "mae": abs(float(mae[j])),
             "risk_pts": float(rk[j]) if rk is not None else None} for j in range(a, b)]


def leg_trades(name: str) -> list[dict]:
    base = ROOT / name
    wf = json.loads((base / "wf" / "result.json").read_text())
    stores = [p for p in sorted((base / "runs").glob(f"{name}-*")) if p.is_dir() and "__ctl" not in p.name]
    if len(stores) != 1:
        raise SystemExit(f"{name}: {len(stores)} build stores (one bar size per leg, please)")
    store = stores[0]
    tz = np.load(base / "wf" / "test_cells.npz", allow_pickle=True)
    out = []
    for m in wf["months"]:
        c = m["cell"]
        if not c:
            continue
        if m["month"] >= BLIND and f"{c}|date" in tz.files:
            e, d, n, mae = tz[f"{c}|entry_ms"], tz[f"{c}|dur_s"], tz[f"{c}|net"], tz[f"{c}|mae"]
            rows = [{"entry_ms": int(e[j]), "exit_ms": int(e[j]) + int(d[j]) * 1000, "net": float(n[j]), "mae": abs(float(mae[j])),
                     "risk_pts": None} for j in range(len(e))]
        else:
            rows = _store_rows(store, c)
        got = []
        for t in rows:
            t["date"] = dt.datetime.fromtimestamp(t["entry_ms"] / 1000, NY).date().isoformat()
            if t["date"][:7] == m["month"]:
                got.append({**t, "leg": name})
        if len(got) != m["trades"] or abs(sum(t["net"] for t in got) - m["net"]) > 1.0:
            raise SystemExit(f"{name} {m['month']}: {len(got)} trades ${sum(t['net'] for t in got):,.0f} vs wf {m['trades']} ${m['net']:,.0f}")
        out += got
    return out


def weekdays_of(months: set[str], last: str | None = None) -> int:
    n = 0
    for mo in months:
        d = dt.date.fromisoformat(mo + "-01")
        while d.strftime("%Y-%m") == mo and (last is None or d.isoformat() <= last):
            n += d.weekday() < 5
            d += dt.timedelta(1)
    return n


def stats(ts: list[dict], days: int) -> dict:
    net = np.array([t["net"] for t in ts]) if ts else np.zeros(0)
    win = net > 0
    aw = float(net[win].mean()) if win.any() else 0.0
    al = float(net[~win].mean()) if (~win).any() else 0.0
    be = 1 / (1 + aw / abs(al)) if al < 0 and aw > 0 else None
    blind = [t for t in ts if t["date"][:7] >= BLIND]
    return {"trades": len(ts), "per_day": round(len(ts) / days, 2) if days else None, "net": round(float(net.sum()), 0),
            "avg": round(float(net.mean()), 1) if len(net) else None, "win": round(float(win.mean()), 4) if len(net) else None,
            "rr": round(aw / abs(al), 3) if al < 0 else None, "breakeven": round(be, 4) if be else None,
            "p315": bool(be is not None and win.mean() >= be + CUSHION),
            "blind_trades": len(blind), "blind_net": round(sum(t["net"] for t in blind), 0)}


def stack(names: list[str]) -> dict:
    legs = {n: leg_trades(n) for n in names}
    allt = sorted((t for ts in legs.values() for t in ts), key=lambda t: (t["entry_ms"], t["leg"]))
    taken, busy_until = [], 0
    for t in allt:
        if t["entry_ms"] < busy_until:
            continue
        taken.append(t)
        busy_until = t["exit_ms"]
    # every test month of the walk-forward, stand-aside months included (audit 2026-10-20), counted in weekdays to the read's last day
    months = set()
    last = None
    for n in names:
        wf = json.loads((ROOT / n / "wf" / "result.json").read_text())
        months |= {m["month"] for m in wf["months"]}
        last = max(last or wf["days"][1], wf["days"][1])
    days = weekdays_of(months, last)
    by_month = {}
    for t in taken:
        m = by_month.setdefault(t["date"][:7], {"trades": 0, "net": 0.0})
        m["trades"] += 1
        m["net"] += t["net"]
    return {"legs": {n: stats(ts, days) for n, ts in legs.items()}, "stack": stats(taken, days),
            "skipped": len(allt) - len(taken), "test_months": sorted(months), "weekdays": days,
            "by_month": {k: {"trades": v["trades"], "net": round(v["net"])} for k, v in sorted(by_month.items())},
            "taken_by_leg": {n: sum(1 for t in taken if t["leg"] == n) for n in names}, "taken": taken}


def main(argv: list[str]) -> None:
    js = None
    if "--json" in argv:
        i = argv.index("--json")
        js = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    res = stack(argv)
    for n, s in res["legs"].items():
        print(f"leg  {n:44} {s}")
    print(f"STACK one-at-a-time ({res['skipped']} skipped): {res['stack']}")
    print(f"taken by leg: {res['taken_by_leg']}")
    print(f"months: {res['by_month']}")
    res = {**res, "taken": res["taken"]}
    if js:
        Path(js).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])

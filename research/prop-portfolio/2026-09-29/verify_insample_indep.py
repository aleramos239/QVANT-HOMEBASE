#!/usr/bin/python3
"""Adversarial verification of the in-sample Stage B results (any pilot: PP_PILOT=es / --pilot es): re-derive every eval number of
out/portfolio_results.json from the RAW tester trades.json files with the independent walk of verify_indep.py, and audit the raw trades
against the instrument's point value / commission.

Independent of the scorer: its OWN trades.json reader (no E.load), calendar rebuilt from the tick-archive file names, session assigned from
the entry minute, walk + race of verify_indep.py. Shared: the rule JSON (E.firm_rules) and the manifest of WHAT was scored
(portfolio_results.json). Compares P1/P2/P3/P5/bust5 under eod / realized / intraday for every report (single / best2 / portfolio / extras,
plus the fast-objective reports), executed trades / net of the walk, and the multi-account mixes.

Run:  PYTHONPATH=~/ramos-quant-homebase PP_PILOT=es /usr/bin/python3 verify_insample_indep.py [--audit-only]
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent
sys.path.insert(0, str(R))
import evalcore as E            # noqa: E402
import verify_indep as V        # noqa: E402

PV, TICK, ROOT = E.PL.PV, E.PL.TICK, E.PL.ROOT
OUT = E.D / "out"
res = json.loads((OUT / "portfolio_results.json").read_text())
H0, H1 = "2021-01-01", "2024-12-31"

# ------------------------------------------------------------------ calendar from archive file names
from homebase.backtest.tape import TapeStore  # noqa: E402
arch = TapeStore().archive / ROOT
cal_set = set()
for y in range(2021, 2025):
    for f in (arch / str(y)).glob("*.json"):
        try:
            d = dt.date.fromisoformat(f.name[:10])
        except ValueError:
            continue
        if H0 <= d.isoformat() <= H1 and d.weekday() < 5:
            cal_set.add(d.toordinal())
scorer_cal = {dt.date.fromisoformat(d).toordinal() for d in E.tape_sessions(H0, H1)}
print(f"[{ROOT}] archive weekday sessions {len(cal_set)} vs scorer calendar {len(scorer_cal)}; only-archive "
      f"{[dt.date.fromordinal(x).isoformat() for x in sorted(cal_set - scorer_cal)[:6]]} only-scorer {[dt.date.fromordinal(x).isoformat() for x in sorted(scorer_cal - cal_set)[:6]]}")

# ------------------------------------------------------------------ own trade reader + instrument audit
RUNS, GRIDS = E.RUNS, E.GRIDS
_RAW: dict = {}
AUD = dict(n=0, gross_bad=0, comm_bad=0, mae_bad=0, mfe_bad=0, qty_not1=0, pts_zero=0, files=0)


def trade_file(src: str) -> Path:
    if "#" in src:
        g, c = src.split("#")
        for p in (GRIDS / g / "cells").iterdir():
            if p.name.isdigit() and int(p.name) == int(c):
                return p / "trades.json"
        raise FileNotFoundError(src)
    return RUNS / src / "trades.json"


def raw_trades(src: str):
    """-> list of (date_ord, te, tx, side, g, mae, mfe) per ONE full contract, research window only; audits $ against ROOT's point value."""
    if src in _RAW:
        return _RAW[src]
    rows = json.loads(trade_file(src).read_text())
    rows = rows if isinstance(rows, list) else rows.get("trades", [])
    AUD["files"] += 1
    out = []
    for x in rows:
        if x["date"] >= "2025-01-01":
            continue
        q = float(x.get("qty") or 1)
        sd = 1 if x["side"] == "long" else -1
        pts = (x["exit_price"] - x["entry_price"]) * sd
        AUD["n"] += 1
        AUD["qty_not1"] += q != 1
        AUD["gross_bad"] += abs(pts * PV * q - x["gross"]) > 0.011 * max(1.0, q)
        AUD["comm_bad"] += abs(x["commission"] - 4.0 * q) > 1e-9
        if x.get("mae_pts") is not None and x.get("mae_usd") is not None:
            AUD["mae_bad"] += abs(x["mae_pts"] * PV * q - abs(x["mae_usd"])) > 0.011 * max(1.0, q)
        if x.get("mfe_pts") is not None and x.get("mfe_usd") is not None:
            AUD["mfe_bad"] += abs(x["mfe_pts"] * PV * q - abs(x["mfe_usd"])) > 0.011 * max(1.0, q)
        g = x["gross"] / q
        mae = abs(x["mae_usd"]) / q if x.get("mae_usd") is not None else max(0.0, -g)
        mfe = max(abs(x["mfe_usd"]) / q if x.get("mfe_usd") is not None else 0.0, g, 0.0)
        out.append((dt.date.fromisoformat(x["date"]).toordinal(), int(x["entry_ms"]), int(x.get("exit_ms", x["entry_ms"] + 1)), sd, g, mae, mfe))
    _RAW[src] = out
    return out


def member_list(src: str, sess: str):
    return [t for t in raw_trades(src) if sess == "all" or V.sess_of(t[1]) == sess]


def _specs(rep):
    return rep.get("extras", {}).get("specs") or rep.get("specs")


def all_reports():
    for tag, root in (("main", res["firms"]), ("fast", res.get("fast_objective", {}).get("firms", {}))):
        for fm, f in root.items():
            for rk, rep in f["reports"].items():
                if rep.get("members") and _specs(rep):
                    yield tag, fm, rk, rep


reps = list(all_reports())
for _, _, _, rep in reps:
    for s in _specs(rep):
        raw_trades(s["trade_source"])
print(f"audit: {AUD['files']} trade files, {AUD['n']} trades; gross != pts*{PV:g}: {AUD['gross_bad']}; commission != $4/ES: {AUD['comm_bad']}; "
      f"mae$ != mae_pts*{PV:g}: {AUD['mae_bad']}; mfe$ mismatch {AUD['mfe_bad']}; qty != 1: {AUD['qty_not1']}")
SP: dict = {}


def run_all():
    global bad

    jobs = {}
    for ln in (E.D / "jobs.jsonl").read_text().splitlines():
        if ln.strip():
            j = json.loads(ln)
            jobs[j["key"]] = j

    bad = []


    def cmp(tag, a, b, tol=1e-9):
        ok = (a is None and b is None) or (a is not None and b is not None and abs(a - b) <= tol * max(1.0, abs(b)))
        if not ok:
            bad.append((tag, a, b))
        return ok


    # source <-> candidate-name consistency (name 'KEY#cell|sess' -> jobs.jsonl[KEY] id must equal the trade_source)
    for tag, fm, rk, rep in reps:
        for m, s in zip(rep["members"], _specs(rep)):
            key_cell = m["name"].split("|")[0]
            key, cell = key_cell.rsplit("#", 1)
            j = jobs.get(key)
            ok = j is not None and s["trade_source"] == f"{j['id']}#{cell}" and s["sess"] == m["name"].split("|")[1] and int(s["micros"]) == int(m["micros"])
            if not ok:
                bad.append(("source-name", tag, fm, rk, m["name"], s["trade_source"], j and j.get("id")))

    # trade dates off the archive calendar
    tdates = {t[0] for _, _, _, rep in reps for s in _specs(rep) for t in raw_trades(s["trade_source"])}
    CAL = sorted(cal_set | tdates)
    print(f"off-archive trade dates {sorted(tdates - cal_set)[:5]}; calendar {len(CAL)} (scorer {res['firms']['lucid'].get('calendar_sessions', '?')})")

    # ------------------------------------------------------------------ every report
    SP.clear()
    worst = 0.0
    rows = []
    for tag, fm, rk, rep in reps:
        cell = rep["cell"]
        rules = dict(day_lock=cell["day_lock"], day_take=cell["day_take"], day_stop=cell["day_stop"], max_day_tr=cell["max_day_tr"], target_take=bool(cell["target_take"]))
        mem = [(member_list(s["trade_source"], s["sess"]), s["sess"], int(s["micros"])) for s in _specs(rep)]
        sp = V.Spec(fm, mem, rules, cal=CAL)
        arr = sp.arrays()
        SP[(tag, fm, rk)] = (sp, arr)
        line = []
        for m in V.MODELS:
            o, d = arr[m]
            mt = V.metrics(o, d)
            for k in (("p1", "p2", "p3", "p5", "bust5") if "eod" in rep else ()):
                if not cmp(f"{tag}/{fm}/{rk}/{m}/{k}", mt[k], rep[m][k], 1e-9):
                    pass
                worst = max(worst, abs(mt[k] - rep[m][k]))
            line.append(f"{m[:3]} {mt['p5']:.4f}")
        nets = [sp.day(i).tot for i in range(sp.D)]
        ex = sum(len(sp.day(i).execd) for i in range(sp.D))
        if "walk" in rep:
            cmp(f"{tag}/{fm}/{rk}/exec", ex, rep["walk"]["executed"])
        # per-member executed trades + net (independent attribution)
        mex = {}
        for i in range(sp.D):
            for (te, tx, sd, n, p, mi) in sp.day(i).execd:
                a = mex.setdefault(mi, [0, 0.0])
                a[0] += 1
                a[1] += p
        if "exec" in rep:
            for mi, em in enumerate(rep["exec"]["members"]):
                a = mex.get(mi, [0, 0.0])
                cmp(f"{tag}/{fm}/{rk}/exec_m{mi}_n", a[0], em["executed"])
                cmp(f"{tag}/{fm}/{rk}/exec_m{mi}_net", a[1], em["net"], 1e-6)
        sc = (f"  scorer(e/r/i) {rep['eod']['p5']:.4f}/{rep['realized']['p5']:.4f}/{rep['intraday']['p5']:.4f}" if "eod" in rep else "  (no scorer metrics)")
        print(f"{tag:4s} {fm:15s} {rk[:34]:34s} S={sp.S} exec={ex} net={sum(nets):9.0f} " + " | ".join(line) + sc, flush=True)
    print("eval max abs diff vs scorer:", worst)

    # ------------------------------------------------------------------ headline criterion recompute (main, singles/best2/portfolio), primary model
    print()
    for fm in res["firms"]:
        for rk in ("single", "best2", "portfolio"):
            sp, arr = SP[("main", fm, rk)]
            pm = E.primary_model(fm)
            p5 = V.metrics(*arr[pm])["p5"]
            sc = res["firms"][fm]["reports"][rk]["headline"]["p5"]
            cmp(f"headline/{fm}/{rk}", p5, sc)
            print(f"headline {fm:15s} {rk:10s} primary({pm}) P5 {p5:.4f} scorer {sc:.4f}  >=0.60? {p5 >= 0.60}")

    # ------------------------------------------------------------------ multi-account mixes (main reports)
    print()
    NAMES = {"pf": "portfolio", "single": "single", "best2": "best2", "portfolio": "portfolio"}
    for root_tag, root in (("main", res["multi_account"]), ("fast", res.get("fast_objective", {}).get("multi_account", {}))):
        for n, mix in (root.get("mixes") or {}).items():
            if not mix:
                continue
            accts = mix["primary"]["accounts"] if "primary" in mix else mix["accounts"]
            S0 = None
            row = {}
            for model in ("primary",) + V.MODELS:
                anyp = None
                for a in accts:
                    fm, nm = a.split(":", 1)
                    key = (root_tag, fm, NAMES.get(nm, nm))
                    if key not in SP and nm.startswith("single:"):
                        key = (root_tag, fm, nm)
                    if key not in SP:
                        raise SystemExit(f"mix account {a} has no report {key}")
                    o, d = SP[key][1][E.primary_model(fm) if model == "primary" else model]
                    p = (o == 1) & (d <= 5)
                    anyp = p if anyp is None else (anyp | p)
                row[model] = float(anyp.mean())
                cmp(f"mix/{root_tag}/{n}/{model}", row[model], mix[model]["p_any5"])
            print(f"mix {root_tag} N={n} {accts}: " + " ".join(f"{k} {v:.4f}" for k, v in row.items()) + f" | scorer primary {mix['primary']['p_any5']:.4f} eod {mix['eod']['p_any5']:.4f} intraday {mix['intraday']['p_any5']:.4f}")

    print("\nMISMATCHES:", len(bad))
    for b in bad[:60]:
        print("  ", b)



if __name__ == "__main__" and "--audit-only" not in sys.argv:
    run_all()

#!/usr/bin/python3
"""Adversarial verification of the in-sample FUNDED search (any pilot: PP_PILOT=es): re-derive the headline funded pick of every variant (and the next
ones) from the RAW tester trades.json with the independent lifecycle + day walk of verify_funded_indep.py (RefWalk / ref_life, tick = pilot's $/tick on
one micro), plus the same-config EVAL P5 with verify_indep.py, and recompute net per eval purchase = P5 x E$60 - fee - P5 x activation.

Independent of the scorer: own trades.json reader (also audits gross vs the instrument's point value), calendar rebuilt from the tick-archive file
names, session from the entry minute. Shared: rule JSON (E.firm_rules), fees.json, the manifest (funded_candidates.csv: WHAT was scored).
Run:  PYTHONPATH=~/ramos-quant-homebase PP_PILOT=es /usr/bin/python3 verify_funded_insample.py [--n 3] [--variants flex,...]
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent
sys.path.insert(0, str(R))
import evalcore as E            # noqa: E402
import verify_indep as V        # noqa: E402
import verify_funded_indep as VF  # noqa: E402
from homebase.backtest.tape import TapeStore  # noqa: E402

OUT = E.D / "out"
PV = E.PL.PV
TICK = E.PL.TICK_USD
N = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 3
VARS = (sys.argv[sys.argv.index("--variants") + 1].split(",") if "--variants" in sys.argv else ["flex", "flex_dll", "pro_dll", "pro_nodll", "apex"])

arch = TapeStore().archive / E.ROOT
cal = set()
for y in range(2021, 2025):
    for f in (arch / str(y)).glob("*.json"):
        try:
            d = dt.date.fromisoformat(f.name[:10])
        except ValueError:
            continue
        if d.weekday() < 5 and "2021-01-01" <= d.isoformat() <= "2024-12-31":
            cal.add(d.toordinal())
CAL = sorted(cal)

jobs = {}
for ln in (E.D / "jobs.jsonl").read_text().splitlines():
    if ln.strip():
        j = json.loads(ln)
        jobs[j["key"]] = j


def trade_src(key: str) -> str:
    if "#" in key:
        k, c = key.rsplit("#", 1)
        return f"{jobs[k]['id']}#{c}"
    return jobs[key]["id"]


def trade_file(src: str) -> Path:
    if "#" in src:
        g, c = src.split("#")
        for p in (E.GRIDS / g / "cells").iterdir():
            if p.name.isdigit() and int(p.name) == int(c):
                return p / "trades.json"
    return E.RUNS / src / "trades.json"


_RAW = {}
AUD = dict(n=0, gross_bad=0)


def raw(src):
    if src not in _RAW:
        rows = json.loads(trade_file(src).read_text())
        rows = rows if isinstance(rows, list) else rows.get("trades", [])
        out = []
        for x in rows:
            if x["date"] >= "2025-01-01":
                continue
            q = float(x.get("qty") or 1)
            sd = 1 if x["side"] == "long" else -1
            AUD["n"] += 1
            AUD["gross_bad"] += abs((x["exit_price"] - x["entry_price"]) * sd * PV * q - x["gross"]) > 0.011
            g = x["gross"] / q
            out.append((dt.date.fromisoformat(x["date"]).toordinal(), int(x["entry_ms"]), int(x.get("exit_ms", x["entry_ms"] + 1)), sd, g,
                        abs(x["mae_usd"]) / q if x.get("mae_usd") is not None else max(0.0, -g),
                        max(abs(x["mfe_usd"]) / q if x.get("mfe_usd") is not None else 0.0, g, 0.0)))
        _RAW[src] = out
    return _RAW[src]


def day_dicts(key, sess, cal_ords):
    pos = {o: i for i, o in enumerate(cal_ords)}
    days = [[] for _ in cal_ords]
    for (d, te, tx, sd, g, mae, mfe) in raw(trade_src(key)):
        if sess != "all" and V.sess_of(te) != sess:
            continue
        days[pos[d]].append(dict(te=te, tx=tx, side=sd, g=g, mae=mae, mfe=mfe, m=10, mem=0))
    for d in days:
        d.sort(key=lambda x: x["te"])
    return days


def parse_rules(s):                                    # "m40 L1000 K- S- T- TT" -> dict
    toks = s.split()
    d = {t[0]: t[1:] for t in toks if t != "TT"}
    f = lambda x: 0.0 if x in ("-", "") else float(x)
    return dict(micros=int(d["m"]), day_lock=f(d.get("L", "-")), day_take=f(d.get("K", "-")), day_stop=f(d.get("S", "-")),
                max_day_tr=int(f(d.get("T", "-"))), target_take=("TT" in s.split()))


KIND = {"flex": ("flex", 0.0), "flex_dll": ("flex", 1200.0), "pro_dll": ("pro", 1200.0), "pro_nodll": ("pro", 0.0), "apex": ("apex", 0.0)}
EVAL_OF = {"flex": "lucid", "flex_dll": "lucid", "pro_dll": "lucidpro", "pro_nodll": "lucidpro_nodll", "apex": "apex"}
FEES = json.loads((E.PL.shared("fees.json")).read_text())
FKEYS = ("p_pay_20", "p_pay_40", "p_pay_60", "med_days_first", "e_first_gross", "e_net_40", "e_net_60", "p_bust_pre_first", "e_npay_60")
fl = lambda x: float(x) if x not in ("", None, "nan") else float("nan")

rows = [r for r in csv.DictReader((OUT / "funded_candidates.csv").open()) if r["stage"] == "full" and r["status"] == "ok"]
ev = {(r["key"], r["sess"], r["firm"]): r for r in csv.DictReader((OUT / "candidates.csv").open())}


def top(v, k):
    """Headline order of funded_headline.py: net per purchase desc (same-config eval P5 x E$60 - fee - P5 x act); Apex rows with cfg flags dropped."""
    fee, act = [(FEES[rid]["eval_fee"], FEES[rid].get("activation", 0.0)) for rid in [E.firm_rules(EVAL_OF[v])[0]]][0]
    out = []
    for r in rows:
        if r["variant"] != v or (v == "apex" and r["apex_cfg_flags"]):
            continue
        if (r["key"], r["sess"], EVAL_OF[v]) not in ev:
            continue
        out.append((fl(r["eval_p5"]) * fl(r["e_net_60"]) - fee - fl(r["eval_p5"]) * act, r))
    out.sort(key=lambda x: -x[0])
    return out[:k]


bad, worst = [], 0.0
print(f"[{E.ROOT}] tick ${TICK}/micro, point value ${PV}/ES-pt, calendar {len(CAL)} sessions")
for v in VARS:
    kind, dll = KIND[v]
    fee_rid = E.firm_rules(EVAL_OF[v])[0]
    fee, act = FEES[fee_rid]["eval_fee"], FEES[fee_rid].get("activation", 0.0)
    for net_csv, r in top(v, N):
        cell = VF.parse_cell(r["e40_stable_cell"])
        days = day_dicts(r["key"], r["sess"], CAL)
        W = VF.RefWalk(days, cell["micros"], {k: cell[k] for k in ("day_take", "day_lock", "day_stop", "max_day_tr")}, TICK)
        models = {"flex": ("realized", "eod", "intraday"), "pro": ("realized", "eod", "intraday"), "apex": ("pess", "nat", "opt")}[kind]
        m = {mod: VF.ref_metrics(kind, W, cell["policy"], mod, dll=dll) for mod in models}
        p = m[models[0]]
        diffs = {k: (p[k], fl(r[k])) for k in FKEYS}
        for k, (a, b) in diffs.items():
            if (a is None) != (b != b) or (a is not None and b == b and abs(a - b) > 1e-6 * max(1.0, abs(b))):
                bad.append((v, r["cid"], k, a, b))
            elif a is not None and b == b:
                worst = max(worst, abs(a - b))
        for tag in ("alt1", "alt2"):
            mod = r[f"{tag}_model"]
            a, b = m[mod]["e_net_40"], fl(r[f"{tag}_e40"])
            if abs(a - b) > 1e-6 * max(1.0, abs(b)):
                bad.append((v, r["cid"], f"{tag}({mod}) e40", a, b))
            worst = max(worst, abs(a - b))
        # same-config eval P5 under the eval firm's rules
        er = parse_rules(r["eval_rules"])
        mem = [([(d, te, tx, sd, g, mae, mfe) for (d, te, tx, sd, g, mae, mfe) in raw(trade_src(r["key"])) if r["sess"] == "all" or V.sess_of(te) == r["sess"]],
                r["sess"], er["micros"])]
        sp = V.Spec(EVAL_OF[v], mem, {k: er[k] for k in ("day_lock", "day_take", "day_stop", "max_day_tr", "target_take")}, cal=sorted(set(CAL) | {t[0] for t in mem[0][0]}))
        prim = E.primary_model(EVAL_OF[v])
        o, d = sp.arrays((prim,))[prim]
        p5 = V.pk(o, d, 5)
        if abs(p5 - fl(r["eval_p5"])) > 1.5e-4:           # csv stores 4 decimals
            bad.append((v, r["cid"], "eval_p5", p5, fl(r["eval_p5"])))
        net = p5 * p["e_net_60"] - fee - p5 * act
        if abs(net - net_csv) > 0.5:
            bad.append((v, r["cid"], "net_per_purchase", net, net_csv))
        # intraday-breach bound exactly as funded_headline.py: ip5 x (alt2_e40 x E$60/E$40) - fee - ip5 x act
        e = ev[(r["key"], r["sess"], EVAL_OF[v])]
        print(f"[{v:9s}] {r['cid']:30s} {r['e40_stable_cell']:26s} n={p['n']} E$40 ref={p['e_net_40']:9.3f} csv={fl(r['e_net_40']):9.3f} E$60 {p['e_net_60']:8.1f}/{fl(r['e_net_60']):8.1f} "
              f"P20 {p['p_pay_20']:.4f}/{fl(r['p_pay_20']):.4f} med {p['med_days_first']}/{fl(r['med_days_first'])} bustpre {p['p_bust_pre_first']:.4f}/{fl(r['p_bust_pre_first']):.4f} "
              f"| alt E$40 {m[models[1]]['e_net_40']:.0f}/{m[models[2]]['e_net_40']:.0f} | evalP5 {p5:.4f} (csv {fl(r['eval_p5']):.4f}) net/purchase {net:+.1f} (csv {net_csv:+.1f}) cuts {p['cuts']}", flush=True)
print(f"audit: {AUD['n']} trades, gross != pts*{PV:g}: {AUD['gross_bad']}")
print("max abs diff", worst, "| MISMATCHES", len(bad))
for b in bad:
    print("  ", b)

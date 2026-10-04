"""STAGE 3, step 1 (BUILD only): the 15 units E1 / E2 / E3 x NQ, ES, GC = day filters on the stored BUILD trades, judged by
tests (a)-(e) of EDGE_SPEC "STAGE 3". Reads runs/ (BUILD stores; every store's period is asserted). Reads no 2024 / 2025+ P&L
(2024 enters only as a COUNT of calendar days in test (a)).
  (a) the central variant's BUILD trades + the group's 2024 session days >= 100 (one trade a day at most: "reachable")
  (b) heat map on the group's days: >= 60 % of variants positive and median > 0 (library.plateau; dead flags of the whole table)
  (c) central variant: mean net per trade on the group's days minus its mean on NON-event days (ev.py) > 0
  (d) central variant's t on the group's days >= the bar (ev.BAR)
  (e) central net on the group's days beats 99.67 % of 4,000 random same-size subsets of the days it traded
Also printed (information): the random-minute control on the same days, per-year tables, the per-type table.
  python out/events/judge_build.py  -> out/events/build_units.csv / .json, per_type.csv"""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ev as E  # noqa: E402
import library as LB  # noqa: E402

TF = "30"


def load(key: str, runs_dir=None):
    u = LB.load_unit(key, runs_dir)
    return u


def masked(x: dict, m) -> dict:
    return {k: np.asarray(v)[m] for k, v in x.items() if k in LB.FIELDS}


def side_table(u: dict, sess: str, base_rows: list, group: str | None) -> list:
    idx = {c["id"]: i for i, c in enumerate(u["meta"]["cells"])}
    code = LB.SESS_CODE[sess]
    out = []
    for r in base_rows:
        if r["id"] not in idx:
            continue
        x = LB.unit_cell(u, idx[r["id"]])
        m = x["sess"] == code
        if group is not None:
            m = m & E.mask(group, x["date"])
        st = LB.stats(x["net"][m])
        out.append({"id": r["id"], "vi": r["vi"], "xi": r["xi"], "stop_mode": r.get("stop_mode"), "tgt_r": r.get("tgt_r"),
                    "dead": r.get("dead", False), "net": st["net"], "trades": st["trades"], "t": st["t"], "sig": LB.trade_sig(x, m)})
    return out


def cell(u: dict, cid: str, sess: str, group: str | None = None, invert: bool = False) -> dict:
    x = LB.unit_cell(u, cid)
    m = x["sess"] == LB.SESS_CODE[sess]
    if group is not None:
        g = E.mask(group, x["date"])
        m = m & (~g if invert else g)
    return masked(x, m)


def subset_test(xu: dict, group: str, seed: int) -> dict:
    """(e): the group's net against DRAWS random same-size subsets of the days the central variant traded."""
    days, inv = np.unique(np.asarray(xu["date"]), return_inverse=True)
    daily = np.zeros(len(days))
    np.add.at(daily, inv, np.asarray(xu["net"], np.float64))
    ins = np.isin(days, E.ords(group))
    k, n = int(ins.sum()), int(len(days))
    obs = float(daily[ins].sum())
    if k == 0 or k >= n:
        return {"p": 0.0, "days_in": k, "days_all": n, "net": round(obs, 2)}
    rng = np.random.default_rng(int(seed))
    nets = np.zeros(E.DRAWS)
    for a in range(0, E.DRAWS, 500):
        pick = np.argsort(rng.random((500, n)), axis=1)[:, :k]
        nets[a:a + 500] = daily[pick].sum(axis=1)
    return {"p": float((obs > nets).mean()), "days_in": k, "days_all": n, "net": round(obs, 2), "null_mean": round(float(nets.mean()), 2),
            "null_cut": round(float(np.percentile(nets, 100 * E.ALPHA)), 2)}


def shift_control(fam: str, root: str, cid: str, group: str, period: str = "build", runs_dir=None, key: str | None = None) -> dict:
    """The same bracket fired at a random minute (2 seeds), on the group's days: {'nets', 'mean', 'trades'}."""
    su = load(key or f"{fam}-{root}-tf{TF}-shift", runs_dir)
    assert su["meta"].get("period") == period
    nets, n = [], 0
    for sd in (1, 2):
        x = LB.unit_cell(su, f"s{sd}_{cid}")
        m = E.mask(group, x["date"])
        nets.append(float(x["net"][m].sum()))
        n += int(m.sum())
    return {"nets": nets, "mean": float(np.mean(nets)), "trades": n}


def yearly(x: dict, root: str, cal: list) -> dict:
    z = LB.sized(x, root)
    keep = ("period", "trades", "net", "win", "pf", "max_dd", "sharpe", "avg_trade", "worst_open_loss", "t")
    mic = z["micros"][z["micros"] > 0]
    return {"c1": [{k: r[k] for k in keep} for r in LB.per_year(x, cal)],
            "r1000": [{k: r[k] for k in keep} for r in LB.per_year(z, cal, z["cost"])],
            "micros_median": int(np.median(mic)) if len(mic) else 0}


def judge_unit(code: str, fam: str, sess: str, group: str, root: str) -> dict:
    key = f"{fam}-{root}-tf{TF}"
    u = load(key)
    assert u["meta"].get("period") == "build", key
    base = LB.plateau_units(u, sess)[""]
    table = side_table(u, sess, base, group)
    pl = LB.plateau(table)
    pl_all = LB.plateau(side_table(u, sess, base, None))
    cal_b, cal_p = LB.calendar("build", root), LB.calendar("pick", root)
    gd = E.days(group)
    days_b, days_p = sum(d in gd for d in cal_b), sum(d in gd for d in cal_p)
    uid = f"{code}-{group}-{root}"
    row = {"uid": uid, "unit": code, "family": fam, "group": group, "root": root, "sess": sess, "key": key, "cells": pl["cells"],
           "positive": pl["positive"], "share_pos": pl["share_pos"], "median_net": pl["median_net"], "v60": pl["verdicts"]["60"],
           "v70": pl["verdicts"]["70"], "v80": pl["verdicts"]["80"], "central": pl["member"], "best_net": pl["best_net"],
           "worst_net": pl["worst_net"], "bar": round(E.BAR[root], 4), "bar_stage1_file": round(E.BAR_S1[root], 4),
           "event_days_build": days_b, "event_days_2024": days_p, "all_days_share_pos": pl_all["share_pos"],
           "all_days_central": pl_all["member"], "b": bool(pl["pass"]), "second_look": E.SECOND_LOOK.get((fam, root), "")}
    if pl["member"] is None:
        row.update(trades=0, net=0.0, t=None, a=False, c=False, d=False, e=False)
        row["pass"] = False
        row["plateau"] = pl
        return row
    cm = pl["member"]
    xu = cell(u, cm, sess)
    xs = cell(u, cm, sess, group)
    clock = "A" if E.GROUP_TIME[group] == "08:30" else "C"
    xn = cell(u, cm, sess, clock, invert=True)                       # NON-event days: no calendar row at this clock time
    xo = cell(u, cm, sess, group, invert=True)                       # information: every day outside the group
    st, sn, so = LB.stats(xs["net"]), LB.stats(xn["net"]), LB.stats(xo["net"])
    t = st["t"] if st["t"] is not None else 0.0
    mean_e = st["net"] / st["trades"] if st["trades"] else 0.0
    mean_n = sn["net"] / sn["trades"] if sn["trades"] else 0.0
    mean_o = so["net"] / so["trades"] if so["trades"] else 0.0
    e = subset_test(xu, group, LB.default_seed(uid, "e"))
    sc = shift_control(fam, root, cm, group)
    row.update(trades=st["trades"], net=st["net"], t=t, win=st["win"], pf=st["pf"], mean_event=round(mean_e, 2),
               nonevent_trades=sn["trades"], nonevent_net=sn["net"], mean_nonevent=round(mean_n, 2), lift_mean=round(mean_e - mean_n, 2),
               outside_trades=so["trades"], outside_net=so["net"], lift_mean_outside=round(mean_e - mean_o, 2),
               e_p=e["p"], days_in=e["days_in"], days_all=e["days_all"], e_null_mean=e.get("null_mean"), e_null_cut=e.get("null_cut"),
               shift_mean=round(sc["mean"], 2), shift_lift=round(st["net"] - sc["mean"], 2), shift_trades=sc["trades"],
               a=bool(st["trades"] + days_p >= LB.MIN_TRADES), c=bool(mean_e - mean_n > 0), d=bool(t >= E.BAR[root]),
               d_stage1_file=bool(t >= E.BAR_S1[root]), e=bool(e["p"] >= E.ALPHA))
    row["pass"] = bool(row["a"] and row["b"] and row["c"] and row["d"] and row["e"])
    row["years"] = yearly(xs, root, cal_b)
    row["plateau"] = pl
    types = E.T1000 if clock == "C" else E.T0830
    pt = []
    for typ in types:
        m = E.mask(typ, xu["date"])
        s1 = LB.stats(xu["net"][m])
        so_ = np.isin(xu["date"], np.array(sorted(dt.date.fromisoformat(d).toordinal() for d in E.solo(typ)), np.int64))
        s2 = LB.stats(xu["net"][so_])
        pt.append({"uid": uid, "central": cm, "type": typ, "trades": s1["trades"], "net": s1["net"], "t": s1["t"], "win": s1["win"],
                   "solo_trades": s2["trades"], "solo_net": s2["net"]})
    pt.append({"uid": uid, "central": cm, "type": "no release at this time", "trades": sn["trades"], "net": sn["net"], "t": sn["t"],
               "win": sn["win"], "solo_trades": "", "solo_net": ""})
    row["per_type"] = pt
    return row


FLAT = ("uid", "unit", "family", "group", "root", "sess", "cells", "positive", "share_pos", "median_net", "v60", "v70", "v80", "central",
        "trades", "net", "t", "win", "pf", "bar", "bar_stage1_file", "mean_event", "nonevent_trades", "mean_nonevent", "lift_mean",
        "lift_mean_outside", "e_p", "days_in", "days_all", "shift_lift", "event_days_build", "event_days_2024", "all_days_share_pos",
        "a", "b", "c", "d", "d_stage1_file", "e", "pass", "second_look", "best_net", "worst_net")


def main():
    rows = []
    for code, fam, sess, groups in E.UNITS:
        for g in groups:
            for root in E.ROOTS:
                rows.append(judge_unit(code, fam, sess, g, root))
    assert len(rows) == 15
    with (HERE / "build_units.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, FLAT, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    (HERE / "build_units.json").write_text(json.dumps(rows, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
    with (HERE / "per_type.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, ["uid", "central", "type", "trades", "net", "t", "win", "solo_trades", "solo_net"])
        w.writeheader()
        for r in rows:
            w.writerows(r.get("per_type") or [])
    for r in rows:
        tt = "n/a" if r["t"] is None else f"{r['t']:.2f}"
        print(f"{r['uid']:10s} {str(r['central']):24s} cells {r['cells']:3d} pos {r['share_pos']} med {r['median_net']} | trades {r['trades']} "
              f"net {r['net']} t {tt} bar {r['bar']} | lift/trade {r.get('lift_mean')} (outside {r.get('lift_mean_outside')}) | e_p {r.get('e_p')} | "
              f"shift lift {r.get('shift_lift')} | a{int(r['a'])} b{int(r['b'])} c{int(r['c'])} d{int(r['d'])} e{int(r['e'])} "
              f"{'PASS' if r['pass'] else 'fail'} | days B/24 {r['event_days_build']}/{r['event_days_2024']}"
              f"{' | d differs under stage-1 file bar' if r.get('d') != r.get('d_stage1_file') and r['t'] is not None else ''}")


if __name__ == "__main__":
    main()

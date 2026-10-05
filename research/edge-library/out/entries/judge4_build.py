"""STAGE 4, step 1 (BUILD only): the 18 units {W straddle_wide, D event_dir} x day groups {A, B at 08:30; C at 10:00} x NQ, ES, GC
= day filters on the stored BUILD trades (runs/<family>-<root>-tf30, every store's period asserted). No 2024 / 2025+ P&L is read
(2024 enters only as a COUNT of calendar days in test (a)). Helpers and the calendar are the STAGE 3 ones (out/events/ev.py,
out/events/judge_build.py), unchanged. FIXED BEFORE ANY STAGE-4 NUMBER WAS READ (2026-10-04):
  (a) the central variant's BUILD trades + the group's 2024 session days >= 100 ("reachable", as STAGE 3)
  (b) heat map on the group's days: >= 60 % of variants positive and median > 0 (library.plateau; dead flags of the whole table).
      For D the unit is all 7 waits x 32 exits = 224 cells; the central variant is library.plateau's, never the best cell.
  (c) central variant: mean net per trade on the group's days minus its mean on days with NO calendar release at that clock time > 0
  (d) central variant's t on the group's days >= the unchanged stage-1 bar (ev.BAR: NQ 2.56 / ES 2.00 / GC 1.63)
  (e) central net on the group's days beats 99.72 % (1 - 0.05/18) of 4,000 random same-size subsets of the days it traded
  (5s) USER DIRECTION 2026-10-04 5-SECOND GATE: central net with the WINNERS held under 5 s removed (losses kept) > 0.
       "held under 5 s" = stored dur_s < 5 (dur_s = whole seconds of exit - entry, so exactly: exit - entry < 5,000 ms).
       net_fast = net of ALL trades held under 5 s; net_wo_fast_winners = net - (sum of the winners held under 5 s).
       fast_profit_share (information) = winners held under 5 s / all winners (gross).
Per-X table (D, information): for each wait X its 32 exit cells on the group's days: judged cells (library.judged_rows), share
positive, median net, median over those cells of net_wo_fast_winners, median over cells of the per-trade mean on release days
and on non-release days; plus that X's own central cell (library.plateau of the 32) with its net and net_wo_fast_winners.
Also printed (information): the null of the run (D: the same entry with a random direction; W: the same bracket at a random
minute; 2 seeds) on the same days, per-year tables, per-release-type table, median holding time (whole seconds).
  python out/entries/judge4_build.py -> out/entries/build_units.csv / .json, per_x.csv, per_type.csv"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
W = HERE.parents[1]
sys.path.insert(0, str(W / "out" / "events"))
import ev as E  # noqa: E402
import judge_build as JB  # noqa: E402  (STAGE 3 helpers: side_table, cell, subset_test, shift_control, yearly)
import library as LB  # noqa: E402

ALPHA = 1.0 - 0.05 / 18.0                         # 99.72 %: test (e) pays for 18 units
FAST_S = 5
UNITS = [("W", "straddle_wide_0830", "pre", ("A", "B")), ("W", "straddle_wide_1000", "nyam", ("C",)),
         ("D", "event_dir_0830", "pre", ("A", "B")), ("D", "event_dir_1000", "nyam", ("C",))]
# STAGE 4: "W at 08:30 on NQ / GC is close kin of units already read, so flag SECOND LOOK"; 10:00 and D are a first look
SECOND_LOOK = {("straddle_wide_0830", "NQ"): "close kin of straddle_tight_0830 NQ, whose 2024 was already read (stages 2b / 3)",
               ("straddle_wide_0830", "GC"): "close kin of straddle_tight_0830 GC, whose 2024 was already read (stages 2b / 3)"}


def fast(x: dict) -> dict:
    net, dur = np.asarray(x["net"], np.float64), np.asarray(x["dur_s"])
    f = dur < FAST_S
    fw = float(net[f & (net > 0)].sum())
    gw = float(net[net > 0].sum())
    tot = float(net.sum())
    return {"net": round(tot, 2), "net_fast": round(float(net[f].sum()), 2), "fast_trades": int(f.sum()), "fast_winners": int((f & (net > 0)).sum()),
            "fast_winner_usd": round(fw, 2), "net_wo_fast_winners": round(tot - fw, 2), "fast_profit_share": round(fw / gw, 4) if gw > 0 else None,
            "median_hold_s": float(np.median(dur)) if len(dur) else None}


def per_x(u: dict, sess: str, table: list, group: str, clock: str, uid: str, su: dict) -> list:
    """su = the run's null store (the same entry with a RANDOM DIRECTION, 2 seeds). null_median_net / beats_null_share were
    ADDED AFTER the first print-out of this script (information only; no verdict uses them)."""
    out = []
    variants = {c["vi"]: c["variant"] for c in u["meta"]["cells"]}
    for vi in sorted({r["vi"] for r in table}):
        rows = [r for r in table if r["vi"] == vi]
        pl = LB.plateau(rows)
        judged, _, _ = LB.judged_rows(rows)
        nfw, me, mn, hold, nul, real = [], [], [], [], [], []
        for r in judged:
            nul.append(float(np.mean([LB.unit_cell(su, f"s{sd}_{r['id']}")["net"][E.mask(group, LB.unit_cell(su, f"s{sd}_{r['id']}")["date"])].sum()
                                      for sd in (1, 2)])))
            real.append(float(r["net"]))
            xs = JB.cell(u, r["id"], sess, group)
            xn = JB.cell(u, r["id"], sess, clock, invert=True)
            f = fast(xs)
            nfw.append(f["net_wo_fast_winners"])
            hold.append(f["median_hold_s"] if f["median_hold_s"] is not None else np.nan)
            me.append(float(np.mean(xs["net"])) if len(xs["net"]) else 0.0)
            mn.append(float(np.mean(xn["net"])) if len(xn["net"]) else 0.0)
        cm = pl["member"]
        cf = fast(JB.cell(u, cm, sess, group)) if cm else {}
        out.append({"uid": uid, "x": variants[vi].get("x"), "cells": pl["cells"], "positive": pl["positive"], "share_pos": pl["share_pos"],
                    "median_net": pl["median_net"], "median_net_wo_fast_winners": round(float(np.median(nfw)), 2) if nfw else None,
                    "share_pos_wo_fast_winners": round(float(np.mean(np.array(nfw) > 0)), 4) if nfw else None,
                    "median_mean_release": round(float(np.median(me)), 2) if me else None,
                    "median_mean_nonrelease": round(float(np.median(mn)), 2) if mn else None,
                    "median_hold_s": float(np.nanmedian(hold)) if hold else None,
                    "null_median_net": round(float(np.median(nul)), 2) if nul else None,
                    "beats_null_share": round(float(np.mean(np.array(real) > np.array(nul))), 4) if nul else None,
                    "trades": max((r["trades"] for r in rows), default=0), "x_central": cm, "x_central_net": cf.get("net"),
                    "x_central_net_wo_fast_winners": cf.get("net_wo_fast_winners"), "v60": pl["verdicts"]["60"]})
    return out


def judge_unit(code: str, fam: str, sess: str, group: str, root: str) -> dict:
    key = f"{fam}-{root}-tf{JB.TF}"
    u = JB.load(key)
    assert u["meta"].get("period") == "build" and u["meta"]["range"]["end"] <= "2023-12-31", key
    base = LB.plateau_units(u, sess)[""]
    table = JB.side_table(u, sess, base, group)
    pl = LB.plateau(table)
    cal_b, cal_p = LB.calendar("build", root), LB.calendar("pick", root)
    gd = E.days(group)
    days_b, days_p = sum(d in gd for d in cal_b), sum(d in gd for d in cal_p)
    uid = f"{code}-{group}-{root}"
    clock = "A" if E.GROUP_TIME[group] == "08:30" else "C"
    row = {"uid": uid, "unit": code, "family": fam, "group": group, "root": root, "sess": sess, "key": key, "cells": pl["cells"],
           "positive": pl["positive"], "share_pos": pl["share_pos"], "median_net": pl["median_net"], "v60": pl["verdicts"]["60"],
           "v70": pl["verdicts"]["70"], "v80": pl["verdicts"]["80"], "central": pl["member"], "best_net": pl["best_net"],
           "worst_net": pl["worst_net"], "bar": round(E.BAR[root], 4), "event_days_build": days_b, "event_days_2024": days_p,
           "b": bool(pl["pass"]), "second_look": SECOND_LOOK.get((fam, root), ""), "sessions_in_store": LB.unit_sessions(u)}
    row["per_x"] = per_x(u, sess, table, group, clock, uid, JB.load(key + "-shift")) if code == "D" else []
    if pl["member"] is None:
        row.update(trades=0, net=0.0, t=None, a=False, c=False, d=False, e=False, g5=False)
        row["pass_ae"] = row["pass"] = False
        row["plateau"] = pl
        return row
    cm = pl["member"]
    xu = JB.cell(u, cm, sess)
    xs = JB.cell(u, cm, sess, group)
    xn = JB.cell(u, cm, sess, clock, invert=True)
    st, sn = LB.stats(xs["net"]), LB.stats(xn["net"])
    t = st["t"] if st["t"] is not None else 0.0
    mean_e = st["net"] / st["trades"] if st["trades"] else 0.0
    mean_n = sn["net"] / sn["trades"] if sn["trades"] else 0.0
    e = JB.subset_test(xu, group, LB.default_seed(uid, "e"))
    sc = JB.shift_control(fam, root, cm, group)
    f = fast(xs)
    row.update(trades=st["trades"], net=st["net"], t=t, win=st["win"], pf=st["pf"], mean_event=round(mean_e, 2),
               nonevent_trades=sn["trades"], nonevent_net=sn["net"], mean_nonevent=round(mean_n, 2), lift_mean=round(mean_e - mean_n, 2),
               e_p=e["p"], days_in=e["days_in"], days_all=e["days_all"], null_mean=round(sc["mean"], 2),
               null_lift=round(st["net"] - sc["mean"], 2), null_trades=sc["trades"],
               net_fast=f["net_fast"], fast_trades=f["fast_trades"], fast_winners=f["fast_winners"], fast_winner_usd=f["fast_winner_usd"],
               net_wo_fast_winners=f["net_wo_fast_winners"], fast_profit_share=f["fast_profit_share"], median_hold_s=f["median_hold_s"],
               a=bool(st["trades"] + days_p >= LB.MIN_TRADES), c=bool(mean_e - mean_n > 0), d=bool(t >= E.BAR[root]),
               e=bool(e["p"] >= ALPHA), g5=bool(f["net_wo_fast_winners"] > 0))
    row["pass_ae"] = bool(row["a"] and row["b"] and row["c"] and row["d"] and row["e"])
    row["pass"] = bool(row["pass_ae"] and row["g5"])
    row["failed"] = ", ".join(n for n, k in (("a", "a"), ("b", "b"), ("c", "c"), ("d", "d"), ("e", "e"), ("5s", "g5")) if not row[k])
    row["years"] = JB.yearly(xs, root, cal_b)
    row["plateau"] = pl
    types = E.T1000 if clock == "C" else E.T0830
    pt = []
    for typ in types:
        m = E.mask(typ, xu["date"])
        s1 = LB.stats(xu["net"][m])
        pt.append({"uid": uid, "central": cm, "type": typ, "trades": s1["trades"], "net": s1["net"], "t": s1["t"], "win": s1["win"]})
    pt.append({"uid": uid, "central": cm, "type": "no release at this time", "trades": sn["trades"], "net": sn["net"], "t": sn["t"], "win": sn["win"]})
    row["per_type"] = pt
    return row


FLAT = ("uid", "unit", "family", "group", "root", "sess", "cells", "positive", "share_pos", "median_net", "v60", "v70", "v80", "central",
        "trades", "net", "t", "win", "pf", "bar", "mean_event", "nonevent_trades", "mean_nonevent", "lift_mean", "e_p", "days_in", "days_all",
        "null_mean", "null_lift", "net_fast", "fast_trades", "fast_winners", "fast_winner_usd", "net_wo_fast_winners", "fast_profit_share",
        "median_hold_s", "event_days_build", "event_days_2024", "a", "b", "c", "d", "e", "g5", "pass_ae", "pass", "failed", "second_look",
        "best_net", "worst_net")
XCOLS = ("uid", "x", "cells", "positive", "share_pos", "median_net", "median_net_wo_fast_winners", "share_pos_wo_fast_winners",
         "median_mean_release", "median_mean_nonrelease", "median_hold_s", "null_median_net", "beats_null_share", "trades", "x_central", "x_central_net",
         "x_central_net_wo_fast_winners", "v60")


def main():
    rows = []
    for code, fam, sess, groups in UNITS:
        for g in groups:
            for root in E.ROOTS:
                rows.append(judge_unit(code, fam, sess, g, root))
    assert len(rows) == 18
    with (HERE / "build_units.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, FLAT, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    dump = lambda o: o.tolist() if hasattr(o, "tolist") else str(o)  # noqa: E731
    (HERE / "build_units.json").write_text(json.dumps(rows, indent=1, default=dump))
    with (HERE / "per_x.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, XCOLS)
        w.writeheader()
        for r in rows:
            w.writerows(r["per_x"])
    with (HERE / "per_type.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, ["uid", "central", "type", "trades", "net", "t", "win"])
        w.writeheader()
        for r in rows:
            w.writerows(r.get("per_type") or [])
    print("alpha", round(ALPHA, 5), "bars", {k: round(v, 4) for k, v in E.BAR.items()})
    for r in rows:
        tt = "n/a" if r["t"] is None else f"{r['t']:.2f}"
        print(f"{r['uid']:7s} {str(r['central']):18s} cells {r['cells']:3d} pos {r['share_pos']} ({int(r['v60'])}{int(r['v70'])}{int(r['v80'])}) med {r['median_net']} | "
              f"tr {r['trades']} net {r['net']} t {tt}/{r['bar']} | lift {r.get('lift_mean')} | e_p {r.get('e_p')} | null lift {r.get('null_lift')} | "
              f"fast {r.get('net_fast')} wo-fw {r.get('net_wo_fast_winners')} share {r.get('fast_profit_share')} hold {r.get('median_hold_s')} | "
              f"a{int(r['a'])} b{int(r['b'])} c{int(r['c'])} d{int(r['d'])} e{int(r['e'])} 5s{int(r['g5'])} "
              f"{'PASS' if r['pass'] else 'fail ' + r.get('failed', '')} | days B/24 {r['event_days_build']}/{r['event_days_2024']} | sess {r['sessions_in_store']}")
    for r in rows:
        for x in r["per_x"]:
            print(f"  X {x['uid']:7s} x={x['x']:<5} cells {x['cells']:2d} pos {x['share_pos']} med {x['median_net']} med-wo-fw {x['median_net_wo_fast_winners']} "
                  f"per-trade rel/non {x['median_mean_release']}/{x['median_mean_nonrelease']} null-med {x['null_median_net']} beats-null {x['beats_null_share']} hold {x['median_hold_s']} tr {x['trades']}")


if __name__ == "__main__":
    main()

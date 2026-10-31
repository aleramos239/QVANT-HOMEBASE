"""VWAP / portfolio hunt on hm60: every version's IN-SAMPLE record off the 3:1 stores (PREREG_HM40.md sections 4, Amendments A-B).
Reads the in-sample stores only (runs_wf/<spec>-<ROOT>-tf<tf>/is/ and its random pool); there is no test month in them.

    hmread.py                 every finished store of hm40/specs/ -> is_hm.json, is_hm.csv, SELECTION_HM.md (the chosen versions, the picks)
A version = store x box x session group (NY = nyam mid pm, LDN = london, ON = asia eve, PRE = pre)."""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
EL = HERE.parents[2]
sys.path.insert(0, str(EL))
sys.path.insert(0, str(EL / "engine"))

import library as LB  # noqa: E402
from blueprint import pipe_gates as G  # noqa: E402
from blueprint import runner as RUN  # noqa: E402

RUNS = RUN.RUNS_WF
GROUPS = {"NY": ("nyam", "mid", "pm"), "LDN": ("london",), "ON": ("asia", "eve"), "PRE": ("pre",)}
TICK2 = {"NQ": 10.0, "ES": 25.0, "GC": 20.0}            # one extra tick a side, a round turn
LATE = "2025-07"
RECENT = "2024-10"
os.environ.setdefault("HOMEBASE_WF_LAST", "2026-05")      # the hunt's pinned 14 blocks (Amendment D)
BLOCK_POS, BLOCK_T = 9, 2.0
CAL_POS = 8                                               # C9 (Amendment G): positive in >= 8 of the 9 in-sample calendar months                               # C8 (Amendment F): positive in >= 9 of the 14 in-sample blocks, block t >= 2                                        # C7 (Amendment E, 2026-10-21): the in-sample blocks Oct-Dec 2024 .. Feb-Apr 2026
MIN_DAY = 0.35                                            # C4 (Amendment B): 100 trades on ~290 test sessions
SEEN = {1: "seen: owner_vwap_pullback_* test months read 2026-10-20 (the owner kept idea 1 in)",
        27: "seen (proxy, NQ store): its 10:00 twin was read on 2025-07..2026-10 (Amendment I); the ES twin is not"}


def groups_of(sessions: list) -> list:
    """The session groups a store trades: every group one of its passes belongs to (a one-instance family listed as nyam trades mid and pm
    too: its whole group counts, review 2026-10-21)."""
    return [g for g, ss in GROUPS.items() if any(s in sessions for s in ss)]


def _months(x) -> np.ndarray:
    return np.array([dt.date.fromordinal(int(d)).strftime("%Y-%m") for d in x["date"]], dtype="<U7")


def _beats(net: np.ndarray, cell: dict, pool, sess_codes, side=None):
    """The lane's random line (hmwf._beats), on the group's sessions, optionally on random entries of one side only: the share of the
    pool's seeds whose average trade is below the version's. An own-stop box is held against the ATR cell of its multiplier, a fixed-point
    box against the same fixed-point cell."""
    if pool is None or not len(net):
        return None
    mode = cell["exit"]["stop_mode"]
    ex = {"stop_mode": "pts" if mode == "pts" else "atr", "stop_val": cell["exit"]["stop_val"], "tgt_r": cell["exit"]["tgt_r"]}
    mine, avg = float(net.mean()), []
    for i, c in enumerate(pool["meta"]["cells"]):
        if c["exit"] == ex:
            y = LB.unit_cell(pool, i)
            k = np.isin(y["sess"], sess_codes)
            if side is not None:
                k &= y["side"] == side
            if k.any():
                avg.append(float(y["net"][k].mean()))
    return sum(a < mine for a in avg) / len(avg) if avg else None


def read_store(spec: dict) -> list:
    home = RUNS / f"{spec['name']}-{spec['markets'][0]}-tf{spec['bar_sizes'][0]}"
    if not (home / "is" / "cells.npz").exists():
        return []
    u = LB.load_unit("is", home)
    m = u["meta"]
    root, days = m["root"], m["days"]
    pd = RUNS / RUN.pool_key(root, m["tf"], m.get("exits") or RUN.HM40) / f"is-{days[-1][:7]}"
    pool = LB.load_unit(pd.name, pd.parent) if (pd / "cells.npz").exists() else None
    if pool is None:
        return []                                         # the random pool is still being written: the store is not finished
    worse = {}
    for s in m["sessions"]:
        d = home / f"is-{s}-worse"
        if (d / "cells.npz").exists():
            w = LB.load_unit(d.name, home)
            for i, c in enumerate(w["meta"]["cells"]):
                worse[c["id"]] = worse.get(c["id"], 0.0) + float(LB.unit_cell(w, i)["net"].sum())
    side = {"long": 1, "short": -1}.get((spec.get("limits") or {}).get("dir"))
    groups = groups_of(m["sessions"])
    rows, n_days = [], len(days)
    from blueprint import wfmonths as WM
    blk = [b["is"] for b in WM.blocks(root)]              # the 14 in-sample blocks (3 months each)
    idea = int(spec["name"].split("_")[1][1:])
    for i, c in enumerate(m["cells"]):
        x = LB.unit_cell(u, i)
        sess = np.asarray(x["sess"])
        mo = _months(x)
        for g in groups:
            codes = [LB.SESS_CODE[s] for s in GROUPS[g]]          # the whole group (disjoint groups: no trade counted twice)
            k = np.isin(sess, codes)
            net = np.asarray(x["net"], np.float64)[k]
            r = {"store": home.name, "spec": spec["name"], "idea": idea, "market": root, "tf": m["tf"], "box": c["id"], "group": g,
                 "settings": {**c["variant"], **c["exit"]}, "trades": int(len(net)), "seen": SEEN.get(idea), "rate": len(net) / n_days}
            if len(net):
                wr = G.wr_rr(net)
                late = net[mo[k] >= LATE]
                rec = net[mo[k] >= RECENT]                # C7 (Amendment E): the recent in-sample blocks alone
                wr7 = G.wr_rr(rec) if len(rec) else {"passed": False}
                bn = np.array([float(net[np.isin(mo[k], b)].sum()) for b in blk])          # the version's net in each block
                bt = float(bn.mean() / (bn.std(ddof=1) / np.sqrt(len(bn)))) if len(bn) > 1 and bn.std(ddof=1) > 0 else 0.0
                cm = np.array([s_[5:7] for s_ in mo[k]])
                calpos = sum(1 for c_ in sorted(set(cm)) if float(net[cm == c_].sum()) > 0)      # calendar months pooled over the years
                r.update(per_day=round(len(net) / n_days, 3), net=round(float(net.sum()), 1), avg=round(float(net.mean()), 2),
                         win=round(float((net > 0).mean()), 4), need=wr.get("need"), rr=wr.get("rr"), c1=bool(wr["passed"]),
                         net_tick=round(float(net.sum()) - TICK2[root] * len(net), 1), late_net=round(float(late.sum()), 1),
                         late_trades=int(len(late)), recent_trades=int(len(rec)), recent_avg=round(float(rec.mean()), 2) if len(rec) else None,
                         recent_win=round(float((rec > 0).mean()), 4) if len(rec) else None, recent_need=wr7.get("need"), c7=bool(wr7["passed"]),
                         blocks_pos=int((bn > 0).sum()), blocks_n=len(bn), block_t=round(bt, 2), cal_pos=int(calpos),
                         rand=_beats(net, c, pool, codes),
                         rand_side=_beats(net, c, pool, codes, side) if side else None,
                         worse_net=round(worse[c["id"]], 1) if c["id"] in worse and len(groups) == 1 else None)
            rows.append(r)
    return rows


def chosen(r: dict, idea_avg: dict) -> tuple:
    if not r.get("trades"):
        return False, "no trade"
    checks = {"C1": r["c1"], "C2": r["net"] > 0 and r["net_tick"] > 0, "C3": r["rand"] == 1.0 and (r["rand_side"] is None or r["rand_side"] == 1.0),
              "C4": r["rate"] >= MIN_DAY, "C5": r["late_trades"] > 0 and r["late_net"] > 0, "C6": idea_avg[r["idea"]] > 0,
              "C7": r.get("c7", False) and (r.get("recent_avg") or 0) > 0,
              "C8": r.get("blocks_pos", 0) >= BLOCK_POS and r.get("block_t", 0) >= BLOCK_T,
              "C9": r.get("cal_pos", 0) >= CAL_POS}
    first = next((k for k, v in checks.items() if not v), None)
    return first is None, first


def main() -> None:
    specs = [json.loads(p.read_text()) for p in sorted((HERE / "specs").glob("*.json"))]
    rows = [r for sp in specs for r in read_store(sp)]
    by_idea = defaultdict(list)
    for r in rows:
        if r.get("trades"):
            by_idea[r["idea"]].append(r["avg"])
    idea_avg = {i: float(np.mean(v)) for i, v in by_idea.items()}
    for r in rows:
        r["chosen"], r["first_fail"] = chosen(r, idea_avg)
    (HERE / "is_hm.json").write_text(json.dumps(rows, indent=1, default=str))
    cols = ["idea", "spec", "market", "tf", "box", "group", "trades", "per_day", "net", "avg", "win", "need", "net_tick", "late_net", "late_trades",
            "rand", "rand_side", "worse_net", "chosen", "first_fail"]
    with open(HERE / "is_hm.csv", "w", newline="") as f:
        w = csv.DictWriter(f, cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    stores = sorted({r["store"] for r in rows})
    picks = []
    for s in stores:
        ch = sorted([r for r in rows if r["store"] == s and r["chosen"]], key=lambda r: (r["avg"], r["box"], r["group"]))
        if ch:
            picks.append({**ch[(len(ch) - 1) // 2], "n_chosen": len(ch)})
    fails = defaultdict(lambda: defaultdict(int))
    for r in rows:
        fails[r["idea"]][r["first_fail"] or "chosen"] += 1
    L = ["# Portfolio hunt on hm60: in-sample selection (PREREG_HM40.md sections 4, Amendments A-B)", "",
         f"{len(stores)} stores read, {sum(1 for r in rows if r.get('trades'))} versions with in-sample trades. No test month was run for any of them.", "",
         "| Idea | Versions | Idea average (avg trade) | Chosen | First failed (count) |", "|---|---|---|---|---|"]
    for i in sorted(by_idea):
        f = ", ".join(f"{k} {v}" for k, v in sorted(fails[i].items()) if k != "chosen")
        L.append(f"| {i} | {len(by_idea[i])} | ${idea_avg[i]:,.1f} | {fails[i].get('chosen', 0)} | {f} |")
    L += ["", "## The pick of each store with a chosen version (the middle by average trade; worse fills still to add)", "",
          "| Store | Box | Group | Chosen in store | Trades/day | Avg $ | Win | Need | +1 tick net | 2025-07+ IS net | Random |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for p in picks:
        L.append(f"| {p['store']} | {p['box']} | {p['group']} | {p['n_chosen']} | {p['per_day']:.2f} | {p['avg']:,.1f} | {p['win'] * 100:.1f} % | "
                 f"{p['need'] * 100:.1f} % | ${p['net_tick']:,.0f} | ${p['late_net']:,.0f} ({p['late_trades']}) | {p['rand']:.1f} |")
    (HERE / "SELECTION_HM.md").write_text("\n".join(L) + "\n")
    (HERE / "picks_hm.json").write_text(json.dumps(picks, indent=1, default=str))
    print("\n".join(L))


if __name__ == "__main__":
    main()

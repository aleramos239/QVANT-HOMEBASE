"""STAGE 2b ADMIT, step 1: BUILD plateau of every ROUND 1 judged unit + its nulls. A copy of out/admit/judge_build.py with the
stage-D / Level-2 branches removed. Reads runs/ (BUILD stores only; every store's period is asserted). No PICK / EXAM data.
RULES WRITTEN BEFORE ANY ROUND 1 NUMBER WAS OPENED (2026-10-04 08:20 ET, admission analyst):
  unit     family x tf x session x root (x dir for orb_confirm: MIRROR). Sessions = library.unit_sessions, except
           straddle_tight_0930 = 'all' (ENGINE.md 13: fills in the last second before 09:30 are tagged 'pre').
  heat map library.plateau: >= 60 % of the judged cells > 0 and median > 0; identical trade lists once; dead cells and the
           author ('info') cells out.
  control  bar families (N1 N2 N3 N5 N6): library.c1_draws on the pool c1-<ROOT>-tf<tf>, same exit cell, K = 200, seed =
           default_seed(uid, 'build'); pass = lift > 0 and no unmatched trade. Time-fired (N4 late_mom, N7 straddle_tight_*):
           lift = central net - mean of the same cell in the two seeds of the family's own '-shift' store; pass = lift > 0.
  bar      the central cell's per-trade t must be > library.best_of_nulls (95th percentile of each null replicate's best cell):
           bar families: group c1-<ROOT> (the four C1 pools x 7 sessions x 2 seeds, the stores stage 1 used);
           time-fired:   group shift-<ROOT> = the ROUND 1 shift stores of that market (late_mom + 3 straddle_tight, 2 seeds each
           = 8 replicates: THIN, flagged). Sensitivity only (not binding): the same group pooled with stage 1's straddle_t shift
           stores (shift_all-<ROOT>); a unit that passes one and fails the other is flagged.
Writes out/admit_r1/{build_units.csv, build_plateaus.json, null_bars.json, null_passrate.json, null_replicates.json, author_cells.csv}."""
import csv
import json
import sys
from functools import lru_cache
from multiprocessing import Pool
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(W))
sys.path.insert(0, str(W / "engine"))
import library as LB  # noqa: E402

OUT = W / "out" / "admit_r1"
SESS7 = LB.SESS7
R1 = ("vwap_trend_pull", "va_reclaim", "orb_confirm", "late_mom", "open_fade", "vol_spike_break",
      "straddle_tight_0830", "straddle_tight_0930", "straddle_tight_1000")
TIMED = ("late_mom", "straddle_tight_0830", "straddle_tight_0930", "straddle_tight_1000")


def exit_id(cid: str) -> str:
    return cid.rsplit("_", 1)[-1]


@lru_cache(maxsize=16)
def load(key: str):
    u = LB.load_unit(key)
    assert u["meta"].get("period") == "build", key
    assert u["meta"]["range"]["end"] <= "2023-12-31" and not u["meta"]["range"].get("holdout"), key
    return u


def cell_sess(u, cid, sess):
    x = LB.unit_cell(u, cid)
    if sess == "all":
        return x
    m = x["sess"] == LB.SESS_CODE[sess]
    return {k: v[m] for k, v in x.items()}


def share(g):
    return None if not g else g.get("share_pos")


def unit_sessions(u) -> list:
    return ["all"] if u["meta"]["family"] == "straddle_tight_0930" else LB.unit_sessions(u)


def judge_store(key: str) -> dict:
    u = load(key)
    m = u["meta"]
    fam, root, tf = m["family"], m["root"], str(m["tf"])
    timed = fam in TIMED
    rows, pls, auth = [], {}, []
    for sess in unit_sessions(u):
        for label, table in LB.plateau_units(u, sess).items():
            pl = LB.plateau(table)
            uid = f"{key}|{sess}|{label}"
            pls[uid] = pl
            sh = pl["shares"]
            live = [t for t in table if not t.get("dead") and not t.get("info")]
            r = {"uid": uid, "key": key, "family": fam, "root": root, "tf": tf, "sess": sess, "label": label, "timed": timed,
                 "weak": bool(m.get("weak")), "cells": pl["cells"], "cells_all": pl["cells_all"], "info": pl["info"], "dead": pl["dead"],
                 "dup": pl["duplicates"], "positive": pl["positive"], "share_pos": pl["share_pos"], "median_net": pl["median_net"],
                 "plateau": pl["pass"], "v60": pl["verdicts"]["60"], "v70": pl["verdicts"]["70"], "v80": pl["verdicts"]["80"],
                 "share_fixed": share(sh["by_stop"].get("fixed")), "share_atr": share(sh["by_stop"].get("ATR")),
                 "share_pct": share(sh["by_stop"].get("percent")),
                 **{f"share_r{k}": share(sh["by_target"].get(f"r{k}")) for k in (0, 1, 2, 3)},
                 "member": pl["member"], "member_net": pl["member_net"], "best_net": pl["best_net"], "worst_net": pl["worst_net"],
                 "trades_med": int(np.median([t["trades"] for t in live])) if live else 0}
            if pl["member"] is not None:
                x = cell_sess(u, pl["member"], sess)
                st = LB.stats(x["net"])
                r.update(m_trades=st["trades"], m_t=st["t"], m_win=st["win"], m_pf=st["pf"])
            if pl["pass"]:
                xid = exit_id(pl["member"])
                if timed:
                    su = load(f"{fam}-{root}-tf{tf}-shift")
                    nets = [float(LB.unit_cell(su, f"s{sd}_{pl['member']}")["net"].sum()) for sd in (1, 2)]
                    r.update(ctrl="shift", ctrl_lift=round(pl["member_net"] - float(np.mean(nets)), 2), ctrl_short=0,
                             ctrl_nets=json.dumps([round(v, 2) for v in nets]))
                else:
                    pu = load(f"c1-{root}-tf{tf}")
                    parts = [LB.unit_cell(pu, f"s{sd}_{xid}") for sd in (1, 2)]
                    pool = {k: np.concatenate([p[k] for p in parts]) for k in ("date", "sess", "net")}
                    c1 = LB.c1_draws(x, pool, K=200, seed=LB.default_seed(uid, "build"))
                    r.update(ctrl="c1", ctrl_lift=c1["lift"], ctrl_short=c1["short"], ctrl_p_beat=c1["p_beat"],
                             ctrl_fallback=round(c1["fallback_share"], 4), ctrl_mean=c1["mean"])
            rows.append(r)
            for t in table:                                  # author cells: information only
                if t.get("info"):
                    auth.append({"uid": uid, "cell": t["id"], "trades": t["trades"], "net": t["net"], "t": t["t"],
                                 "unit_share_pos": pl["share_pos"], "unit_median": pl["median_net"]})
    return {"rows": rows, "pls": pls, "auth": auth}


def null_store(key: str) -> list:
    u = load(key)
    m = u["meta"]
    ctl, root = m.get("control"), m["root"]
    out = []
    if ctl == "c1":
        for sess in SESS7:
            tab = LB.session_table(u, sess)
            for sd in (1, 2):
                rows = [t for t in tab if t["id"].startswith(f"s{sd}_")]
                pl = LB.plateau(rows)
                mt = next((t["t"] for t in rows if t["id"] == pl["member"]), None)
                out.append({"type": "c1", "root": root, "key": key, "seed": sd, "sess": sess, "group": f"c1-{root}",
                            "best_t": max((t["t"] or 0.0) for t in rows), "plateau": pl["pass"], "share_pos": pl["share_pos"], "m_t": mt})
    elif ctl == "shift":
        r1 = m["family"] in TIMED
        tab = LB.session_table(u, "all")
        for sd in (1, 2):
            rows = [t for t in tab if t["id"].startswith(f"s{sd}_")]
            pl = LB.plateau(rows)
            mt = next((t["t"] for t in rows if t["id"] == pl["member"]), None)
            out.append({"type": "shift", "root": root, "key": key, "seed": sd, "sess": "all", "group": f"shift-{root}" if r1 else f"shift_s1-{root}",
                        "best_t": max((t["t"] or 0.0) for t in rows), "plateau": pl["pass"], "share_pos": pl["share_pos"], "m_t": mt})
    return out


def main():
    keys = sorted(p.parent.name for p in LB.RUNS.glob("*/run.json"))
    metas = {k: json.loads((LB.RUNS / k / "run.json").read_text()) for k in keys}
    assert all(metas[k].get("period") == "build" for k in keys)
    build = [k for k in keys if metas[k].get("stage") == "build" and metas[k]["family"] in R1]
    nulls = [k for k in keys if metas[k].get("stage") == "null" and metas[k].get("control") in ("c1", "shift")]
    print("round1 build stores", len(build), "null stores read", len(nulls), flush=True)
    with Pool(8) as pool:
        reps = [r for part in pool.imap_unordered(null_store, nulls, chunksize=1) for r in part]
        res = list(pool.imap_unordered(judge_store, build, chunksize=1))
    bars, rate = {}, {}
    groups = sorted({r["group"] for r in reps})
    for g in groups:
        b = LB.best_of_nulls([[r["best_t"]] for r in reps if r["group"] == g])
        bars[g] = {k: b[k] for k in ("bar", "nulls", "thin")}
    for root in ("NQ", "ES", "GC"):                          # sensitivity: round 1 shift + stage 1 straddle_t shift
        b = LB.best_of_nulls([[r["best_t"]] for r in reps if r["group"] in (f"shift-{root}", f"shift_s1-{root}")])
        bars[f"shift_all-{root}"] = {k: b[k] for k in ("bar", "nulls", "thin")}
    for g in groups:
        n = [r for r in reps if r["group"] == g]
        both = sum(bool(r["plateau"] and (r["m_t"] or 0.0) > bars[g]["bar"]) for r in n)
        rate[g] = {"null_units": len(n), "plateau_pass": sum(r["plateau"] for r in n), "both_gates": both}
    (OUT / "null_bars.json").write_text(json.dumps(bars, indent=1))
    (OUT / "null_passrate.json").write_text(json.dumps(rate, indent=1))
    (OUT / "null_replicates.json").write_text(json.dumps(reps))
    rows = sorted((r for x in res for r in x["rows"]), key=lambda r: r["uid"])
    pls = {k: v for x in res for k, v in x["pls"].items()}
    auth = sorted((r for x in res for r in x["auth"]), key=lambda r: (r["uid"], r["cell"]))
    for r in rows:
        why = []
        if not r["plateau"]:
            r.update(build_pass=False, fail="plateau")
            continue
        g = f"{'shift' if r['timed'] else 'c1'}-{r['root']}"
        r["bar"] = round(bars[g]["bar"], 4)
        t = r.get("m_t") or 0.0
        if not (r.get("ctrl_lift") is not None and r["ctrl_lift"] > 0 and not r.get("ctrl_short")):
            why.append(r["ctrl"])
        if not t > r["bar"]:
            why.append("bar")
        if r["weak"] and not t >= LB.WEAK_T:
            why.append("weak_t3")
        if r["timed"]:
            r["bar_all"] = round(bars[f"shift_all-{r['root']}"]["bar"], 4)
            r["bar_flag"] = bool((t > r["bar"]) != (t > r["bar_all"]))
        r["exact60"] = abs((r["share_pos"] or 0) - 0.6) < 1e-9
        r.update(build_pass=not why, fail=",".join(why))
    for name, data in (("build_units.csv", rows), ("author_cells.csv", auth)):
        cols = []
        for r in data:
            cols += [c for c in r if c not in cols]
        with (OUT / name).open("w", newline="") as fh:
            w = csv.DictWriter(fh, cols)
            w.writeheader()
            w.writerows(data)
    (OUT / "build_plateaus.json").write_text(json.dumps(pls))
    print("judged units", len(rows), "heat map pass 60/70/80", sum(r["v60"] for r in rows), sum(r["v70"] for r in rows), sum(r["v80"] for r in rows),
          "| + control", sum(r["plateau"] and "c1" not in r["fail"] and "shift" not in r["fail"] for r in rows),
          "| BUILD passers", sum(r["build_pass"] for r in rows))
    print("bars", json.dumps(bars))
    print("null pass rate", json.dumps(rate))


if __name__ == "__main__":
    main()

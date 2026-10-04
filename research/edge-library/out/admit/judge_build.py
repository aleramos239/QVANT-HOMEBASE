"""ADMIT stage, step 1: BUILD plateau of every judged unit + its nulls (plan: progress.md 2026-10-04 04:33 ET, A / B / G / I).
Reads runs/ (BUILD stores only: every store's period is asserted). Writes out/admit/{build_units.csv, build_plateaus.json,
null_bars.json, null_passrate.json, stage_d_paired.csv}. Reads no PICK / EXAM data."""
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

OUT = W / "out" / "admit"
SESS7 = LB.SESS7


def exit_id(cid: str) -> str:
    return cid.rsplit("_", 1)[-1]


@lru_cache(maxsize=16)
def load(key: str):
    u = LB.load_unit(key)
    assert u["meta"].get("period") == "build", key
    return u


def has(key: str) -> bool:
    return (LB.RUNS / key / "run.json").exists()


def cell_sess(u, cid, sess):
    x = LB.unit_cell(u, cid)
    if sess == "all":
        return x
    m = x["sess"] == LB.SESS_CODE[sess]
    return {k: v[m] for k, v in x.items()}


def share(g):
    return None if not g else g.get("share_pos")


def judge_store(key: str) -> dict:
    """Every judged unit of one BUILD store -> rows (+ the plateau dicts) and, for a stage D store, the paired table."""
    import families as F
    u = load(key)
    m = u["meta"]
    fam, root, tf = m["family"], m["root"], str(m["tf"])
    base = m.get("base")
    timed = (base or fam).startswith("straddle_t_")
    l2 = bool(base) or has(f"{key}-c2s1")
    sessions = m.get("base_pass_sessions") if base else LB.unit_sessions(u)
    rows, pls = [], {}
    for sess in sessions:
        for label, table in LB.plateau_units(u, sess).items():
            pl = LB.plateau(table)
            uid = f"{key}|{sess}|{label}"
            pls[uid] = pl
            sh = pl["shares"]
            r = {"uid": uid, "key": key, "kind": "stage_d" if base else "base", "family": fam, "base": base or "", "root": root, "tf": tf,
                 "sess": sess, "label": label, "timed": timed, "l2": l2, "weak": bool(m.get("weak")),
                 "penalty": bool(F.penalty_for(base or fam, sess)),
                 "cells": pl["cells"], "cells_all": pl["cells_all"], "dead": pl["dead"], "dup": pl["duplicates"],
                 "positive": pl["positive"], "share_pos": pl["share_pos"], "median_net": pl["median_net"],
                 "plateau": pl["pass"], "v60": pl["verdicts"]["60"], "v70": pl["verdicts"]["70"], "v80": pl["verdicts"]["80"],
                 "share_fixed": share(sh["by_stop"].get("fixed")), "share_atr": share(sh["by_stop"].get("ATR")),
                 "share_pct": share(sh["by_stop"].get("percent")),
                 **{f"share_r{k}": share(sh["by_target"].get(f"r{k}")) for k in (0, 1, 2, 3)},
                 "member": pl["member"], "member_net": pl["member_net"], "best_net": pl["best_net"], "worst_net": pl["worst_net"],
                 "trades_med": int(np.median([t["trades"] for t in table if not t.get("dead")])) if any(not t.get("dead") for t in table) else 0}
            if pl["member"] is not None:
                x = cell_sess(u, pl["member"], sess)
                st = LB.stats(x["net"])
                r.update(m_trades=st["trades"], m_t=st["t"], m_win=st["win"], m_pf=st["pf"])
            if pl["pass"]:
                xid = exit_id(pl["member"])
                if timed:
                    sk = f"{base or fam}-{root}-tf{tf}-shift"
                    su = load(sk)
                    bid = pl["member"]
                    nets = [float(LB.unit_cell(su, f"s{sd}_{bid}")["net"].sum()) for sd in (1, 2)]
                    r.update(ctrl="shift", ctrl_lift=round(pl["member_net"] - float(np.mean(nets)), 2), ctrl_short=0,
                             ctrl_nets=json.dumps([round(v, 2) for v in nets]))
                else:
                    pu = load(f"c1-{root}-tf{tf}")
                    parts = [LB.unit_cell(pu, f"s{sd}_{xid}") for sd in (1, 2)]
                    pool = {k: np.concatenate([p[k] for p in parts]) for k in ("date", "sess", "net")}
                    c1 = LB.c1_draws(x, pool, K=200, seed=LB.default_seed(uid, "build"))
                    r.update(ctrl="c1", ctrl_lift=c1["lift"], ctrl_short=c1["short"], ctrl_p_beat=c1["p_beat"],
                             ctrl_fallback=round(c1["fallback_share"], 4), ctrl_mean=c1["mean"])
                if l2:
                    if has(f"{key}-c2s1") and has(f"{key}-c2s2"):
                        nets = [float(cell_sess(load(f"{key}-c2s{sd}"), pl["member"], sess)["net"].sum()) for sd in (1, 2)]
                        r.update(c2_lift=round(pl["member_net"] - float(np.mean(nets)), 2), c2_nets=json.dumps([round(v, 2) for v in nets]))
                    else:
                        r.update(c2_lift=None, c2_nets="no C2 store")
            rows.append(r)
    paired = []
    if base:
        cal = LB._ordinals(LB.calendar("build", root))
        bu = load(f"{base}-{root}-tf{tf}")
        nulls = [load(f"{key}-c2s{sd}") for sd in (1, 2)] if has(f"{key}-c2s1") and has(f"{key}-c2s2") else []
        ids = [c["id"] for c in m["cells"]]
        assert ids == [c["id"] for c in bu["meta"]["cells"]], key

        def daily(x):
            d = np.zeros(len(cal))
            if len(x["net"]):
                np.add.at(d, np.searchsorted(cal, x["date"]), x["net"])
            return d

        def pt(a, b):
            d = a - b
            sd = d.std(ddof=1)
            return float(d.mean() / (sd / np.sqrt(len(d)))) if sd > 0 else None

        for sess in sessions:
            bt = {t["id"]: t for t in LB.session_table(bu, sess)}
            live = [i for i in ids if not bt[i]["dead"]]
            nb = np.array([bt[i]["net"] for i in live])
            nv = np.array([float(cell_sess(u, i, sess)["net"].sum()) for i in live])
            tv = np.array([len(cell_sess(u, i, sess)["net"]) for i in live])
            tb = np.array([bt[i]["trades"] for i in live])
            d = nv - nb
            row = {"key": key, "base": base, "tf": tf, "sess": sess, "cells": len(live), "median_base": round(float(np.median(nb)), 2),
                   "median_variant": round(float(np.median(nv)), 2), "median_d": round(float(np.median(d)), 2),
                   "share_d_pos": round(float((d > 0).mean()), 4), "trades_kept_share": round(float(tv.sum() / max(1, tb.sum())), 4)}
            cm = LB.plateau(list(bt.values()))["member"]
            db = daily(cell_sess(bu, cm, sess)) if cm else None
            if cm:
                row.update(central=cm, central_d=round(float(cell_sess(u, cm, sess)["net"].sum() - bt[cm]["net"]), 2),
                           central_paired_t=pt(daily(cell_sess(u, cm, sess)), db))
            if nulls:
                nn = np.array([[float(cell_sess(n, i, sess)["net"].sum()) for i in live] for n in nulls])
                dn = nn.mean(axis=0) - nb
                row.update(median_d_null=round(float(np.median(dn)), 2), share_d_above_null=round(float((d > dn).mean()), 4),
                           median_d_minus_null=round(float(np.median(d - dn)), 2))
                if cm:
                    row.update(central_null_paired_t=json.dumps([pt(daily(cell_sess(n, cm, sess)), db) for n in nulls]))
                row["added"] = bool(np.median(d) > 0 and (d > 0).mean() >= 0.6 and (d > dn).mean() >= 0.6)
            else:
                row["added"] = None
            paired.append(row)
    return {"rows": rows, "pls": pls, "paired": paired}


def null_store(key: str) -> list:
    """The null replicates of one null store: [{type, root, key, seed, sess, best_t, plateau, share_pos, group}]."""
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
                out.append({"type": "c1", "root": root, "key": key, "seed": sd, "sess": sess, "group": f"c1-{root}",
                            "best_t": max((t["t"] or 0.0) for t in rows), "plateau": pl["pass"], "share_pos": pl["share_pos"]})
    elif ctl == "shift":
        tab = LB.session_table(u, "all")
        for sd in (1, 2):
            rows = [t for t in tab if t["id"].startswith(f"s{sd}_")]
            pl = LB.plateau(rows)
            out.append({"type": "shift", "root": root, "key": key, "seed": sd, "sess": "all", "group": f"shift-{root}",
                        "best_t": max((t["t"] or 0.0) for t in rows), "plateau": pl["pass"], "share_pos": pl["share_pos"]})
    elif ctl == "c2":
        base = m.get("base")
        for sess in (m.get("base_pass_sessions") if base else LB.unit_sessions(u)):
            for label, rows in LB.plateau_units(u, sess).items():
                pl = LB.plateau(rows)
                out.append({"type": "c2", "root": root, "key": key, "seed": m.get("seed"), "sess": sess,
                            "group": "c2-stage_d" if base else "c2-l2",
                            "best_t": max((t["t"] or 0.0) for t in rows), "plateau": pl["pass"], "share_pos": pl["share_pos"]})
    return out


def main():
    keys = sorted(p.parent.name for p in LB.RUNS.glob("*/run.json"))
    metas = {k: json.loads((LB.RUNS / k / "run.json").read_text()) for k in keys}
    build = [k for k in keys if metas[k].get("stage") == "build"]
    nulls = [k for k in keys if metas[k].get("stage") == "null"]
    assert all(metas[k].get("period") == "build" for k in keys)
    print("stores", len(keys), "build", len(build), "null", len(nulls), flush=True)
    with Pool(8) as pool:
        reps = [r for part in pool.imap_unordered(null_store, nulls, chunksize=1) for r in part]
        res = list(pool.imap_unordered(judge_store, build, chunksize=1))
    bars, rate = {}, {}
    for g in sorted({r["group"] for r in reps}):
        best = [[r["best_t"]] for r in reps if r["group"] == g]
        b = LB.best_of_nulls(best)
        bars[g] = {k: b[k] for k in ("bar", "nulls", "thin")}
        n = [r for r in reps if r["group"] == g]
        rate[g] = {"null_units": len(n), "plateau_pass": sum(r["plateau"] for r in n), "rate": round(sum(r["plateau"] for r in n) / len(n), 4)}
    (OUT / "null_bars.json").write_text(json.dumps(bars, indent=1))
    (OUT / "null_passrate.json").write_text(json.dumps(rate, indent=1))
    (OUT / "null_replicates.json").write_text(json.dumps(reps))
    rows = sorted((r for x in res for r in x["rows"]), key=lambda r: r["uid"])
    pls = {k: v for x in res for k, v in x["pls"].items()}
    paired = sorted((r for x in res for r in x["paired"]), key=lambda r: (r["key"], r["sess"]))
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
        if r["l2"]:
            g2 = "c2-stage_d" if r["kind"] == "stage_d" else "c2-l2"
            r["bar_c2"] = round(bars[g2]["bar"], 4) if g2 in bars else None
            if not (r.get("c2_lift") is not None and r["c2_lift"] > 0):
                why.append("c2")
            if r["bar_c2"] is None or not t > r["bar_c2"]:
                why.append("bar_c2")
        if not t > r["bar"]:
            why.append("bar")
        if r["weak"] and not t >= LB.WEAK_T:
            why.append("weak_t3")
        r["exact60"] = abs((r["share_pos"] or 0) - 0.6) < 1e-9
        r.update(build_pass=not why, fail=",".join(why))
    cols = []
    for r in rows:
        cols += [c for c in r if c not in cols]
    with (OUT / "build_units.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, cols)
        w.writeheader()
        w.writerows(rows)
    (OUT / "build_plateaus.json").write_text(json.dumps(pls))
    if paired:
        cols = []
        for r in paired:
            cols += [c for c in r if c not in cols]
        with (OUT / "stage_d_paired.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, cols)
            w.writeheader()
            w.writerows(paired)
    n_pl = sum(r["plateau"] for r in rows)
    print("judged units", len(rows), "plateau pass", n_pl, "BUILD passers", sum(r["build_pass"] for r in rows))
    print("bars", json.dumps(bars))
    print("null plateau pass rate", json.dumps(rate))


if __name__ == "__main__":
    main()

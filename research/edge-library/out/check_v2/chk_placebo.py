"""CHECKER v2 PLACEBO, my own code (chk_lib only). A placebo unit = the random-entry table of ONE seed of runs/c1-<root>-tf<tf> in
ONE session; its control = the OTHER seed's pool. 3 markets x 4 bar sizes x 7 sessions x 2 seeds = 168 units.
BUILD: tests (1)-(3), (2) with K = 200 (my seed) and K = 4000. 2024 / stress: only for the three tables the analyst opened.
  python chk_placebo.py"""
import csv, datetime as dt, json, sys, zlib
from multiprocessing import Pool
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import chk_lib as C

SESS7 = ("eve", "asia", "london", "pre", "nyam", "mid", "pm")
OPENED = {("NQ", "1", "eve"), ("NQ", "15", "pre"), ("NQ", "30", "pre")}      # the analyst's jobs_placebo_pick.json
RV = C.W / "runs_v2"


def prow(st, sess, sa, dead_from=None):
    cells = [c for c in st["meta"]["cells"] if c["id"].startswith(f"s{sa}_")]
    rows = []
    for c in cells:
        x = C.cell(st, c["id"], sess)
        rows.append({"id": c["id"], "vi": c.get("vi", 0), "xi": c.get("xi", 0), "info": bool(c.get("info")), "net": float(x["net"].sum()),
                     "trades": int(len(x["net"])), "sig": C.sig(x)})
    alive = {r["vi"] for r in rows if r["trades"]}
    for r in rows:
        r["dead"] = (r["vi"] not in alive) if dead_from is None else dead_from.get(r["id"], False)
    return rows


def one(job):
    import l2sim
    l2sim.wait_compute_window()
    root, tf = job
    st = C.build_store(f"c1-{root}-tf{tf}")
    out = []
    nb, npk = len(C.cal("build", root)), len(C.cal("pick", root))
    for sess in SESS7:
        for sa in (1, 2):
            sb = 3 - sa
            uid = f"placebo-c1-{root}-tf{tf}|{sess}|seed{sa}"
            u = {"uid": uid, "root": root, "tf": tf, "sess": sess, "label": "", "group": None, "side": None}
            rows = prow(st, sess, sa)
            ts = C.tstats(rows)
            r = {"uid": uid, "root": root, "tf": tf, "sess": sess, "seed": sa, "cells": ts["cells"]}
            if not ts["cells"]:
                r.update(t1=False, t2=False, t3=False, build_pass=False)
                out.append(r)
                continue
            t1 = bool(ts["share"] >= 0.6 - 1e-12 and ts["avg"] > 0)
            t3 = bool(ts["avg_trades"] * (1 + npk / nb) >= 100)
            r.update(share=ts["share"], avg=ts["avg"], avg_trades=ts["avg_trades"], t1=t1, t3=t3, t2=False)
            if ts["avg"] > 0 and ts["share"] >= 0.5:
                s = zlib.crc32(f"checker|{uid}|c1".encode())
                v = C.verdict(ts["avg"], C.c1_table(st, u, ts["ids"], st, s, seeds=(sb,)), True)
                big = np.concatenate([C.c1_table(st, u, ts["ids"], st, s + 1 + b, seeds=(sb,))["draws"] for b in range(20)])
                r.update(t2=bool(v["pass"]), lift=v.get("lift"), p_beat=v.get("p_beat"), ctl_sd=v.get("ctl_sd"), slots=v.get("slots_per_day"),
                         short=v.get("short"), fallback=v.get("fallback_share"), p_4000=float((ts["avg"] > big).mean()), lift_4000=float(ts["avg"] - big.mean()))
            r["build_pass"] = bool(t1 and r["t2"] and t3)
            # 2024 and stress: only the tables the analyst opened
            if (root, tf, sess) in OPENED:
                dead = {x["id"]: x["dead"] for x in rows}
                pst = C.pick_store(f"c1-{root}-tf{tf}-{sess}-pick", [RV])
                pts = C.tstats(prow(pst, sess, sa, dead))
                t4 = bool(pts["cells"] and pts["avg"] > 0 and pts["median"] > 0)
                t5 = False
                if pts["cells"] and pts["avg"] > 0:
                    v5 = C.verdict(pts["avg"], C.c1_table(pst, u, pts["ids"], pst, zlib.crc32(f"checker|{uid}|pick-c1".encode()), seeds=(sb,)), False)
                    t5 = bool(v5["pass"])
                    r["lift_2024"] = v5.get("lift")
                r.update(avg_2024=pts.get("avg"), median_2024=pts.get("median"), share_2024=pts.get("share"), avg_trades_2024=pts.get("avg_trades"), t4=t4, t5=t5)
                if (RV / f"c1-{root}-tf{tf}-{sess}-pick-stress" / "run.json").exists():
                    ps = C.pick_store(f"c1-{root}-tf{tf}-{sess}-pick-stress", [RV])
                    bs = C.load(f"c1-{root}-tf{tf}-{sess}-build-stress", RV)
                    assert bs["meta"]["period"] == "build"
                    sts = C.tstats(prow(ps, sess, sa, dead))
                    net = lambda s_, cid: float(C.cell(s_, cid, sess)["net"].sum())  # noqa: E731
                    ids = [x["id"] for x in rows if not x["dead"]]
                    surv = sum(1 for c in ids if net(st, c) > 0 and net(pst, c) > 0 and net(bs, c) > 0 and net(ps, c) > 0)
                    r.update(stress_avg_2024=sts.get("avg"), t6=bool(sts["cells"] and sts["avg"] > 0), survivors=surv,
                             stress_meta={k: ps["meta"].get(k) for k in ("stress", "oco_cancel_ms")})
            out.append(r)
    return out, list(C.READS)


if __name__ == "__main__":
    jobs = [(r, tf) for r in ("NQ", "ES", "GC") for tf in ("1", "5", "15", "30")]
    rows, reads = [], []
    with Pool(6) as pool:
        for part, rd in pool.imap_unordered(one, jobs, chunksize=1):
            rows += part
            reads += rd
    (C.OUT / "chk_placebo.json").write_text(json.dumps(rows, indent=1))
    A = {r["uid"]: r for r in csv.DictReader(open(C.W / "out" / "v2" / "placebo.csv"))}
    assert set(A) == {r["uid"] for r in rows}
    b = lambda s: s == "True"  # noqa: E731
    d13 = [r["uid"] for r in rows if r["t1"] != b(A[r["uid"]]["t1"]) or r["t3"] != b(A[r["uid"]]["t3"]) or r["cells"] != int(A[r["uid"]]["cells"])]
    dn = [r["uid"] for r in rows if r["cells"] and (abs(r["avg"] - float(A[r["uid"]]["avg_net"])) > 0.01 or abs(r["share"] - float(A[r["uid"]]["share_pos"])) > 1e-9)]
    d2 = [(r["uid"], r.get("p_beat"), A[r["uid"]]["p_beat"], r.get("p_4000")) for r in rows if r["t2"] != b(A[r["uid"]]["t2"])]
    print("units", len(rows), "| (1)", sum(r["t1"] for r in rows), "| (1)+(3)", sum(r["t1"] and r["t3"] for r in rows), "| BUILD pass K=200", sum(r["build_pass"] for r in rows),
          "| BUILD pass K=4000", sum(bool(r["t1"] and r["t3"] and r.get("p_4000", 0) >= 0.95 and r.get("lift_4000", 0) > 0 and not r.get("short")) for r in rows))
    print("(1)/(3)/cells differ from analyst:", d13, "| avg/share differ:", dn, "| (2) differ:", d2)
    for r in rows:
        if r["t1"] or r.get("p_beat") is not None and r["p_beat"] >= 0.9:
            print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items() if k not in ("root", "tf", "sess", "seed")}, "| analyst",
                  {k: A[r["uid"]][k] for k in ("t1", "t2", "t3", "p_beat", "build_pass", "t4", "t5", "t6", "survivors", "passed")})
    with (C.OUT / "checker_pick_reads.csv").open("a", newline="") as fh:
        w = csv.writer(fh)
        for d, k in sorted(set(reads)):
            w.writerow([dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), d, k, "chk_placebo.py: placebo tests (4)-(6) re-judged from the store (already read by the analyst)"])

"""STAGE 2a, step 1 (BUILD only): the 8 sides of every unit, judged by tests (a)-(e) of EDGE_SPEC "STAGE 2a".
Reads runs/ (BUILD stores; every store's period is asserted). Reads no PICK / EXAM data.
  python out/deepen/judge_sides.py units      the 58 units (near_misses.csv: fail == 'bar', not WEAK, no penalty)
  python out/deepen/judge_sides.py placebo    the same procedure on the matched random-entry stores (seed A vs seed B)
  python out/deepen/judge_sides.py member     orb_NQ_tf1_pre: the same splits, information only
Restartable: one JSON per unit under out/deepen/cache/; a finished unit is skipped."""
from __future__ import annotations

import csv
import json
import sys
from functools import lru_cache
from multiprocessing import Pool
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
W = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(W))
sys.path.insert(0, str(W / "engine"))
import labels as L  # noqa: E402
import library as LB  # noqa: E402

OUT = HERE
CACHE = OUT / "cache"
ADMIT = W / "out" / "admit"
ALPHA = 1.0 - 0.05 / 8.0                        # 99.4 %: the last test pays for trying 8 sides
DRAWS = 4000
BARS = json.loads((ADMIT / "null_bars.json").read_text())


@lru_cache(maxsize=6)
def load(key: str):
    u = LB.load_unit(key)
    assert u["meta"].get("period") == "build", key
    return u


def exit_id(cid: str) -> str:
    return cid.rsplit("_", 1)[-1]


def masked(x: dict, m) -> dict:
    return {k: np.asarray(v)[m] for k, v in x.items() if k in LB.FIELDS}


def side_table(u: dict, sess: str, base_rows: list, side: str | None, root: str) -> list:
    """The plateau table of one unit-session restricted to a side (None = every trade): net / trades / t / sig are recomputed
    on the kept trades; the dead flags stay those of the unfiltered BUILD table (as judge_pick does for a PICK table)."""
    idx = {c["id"]: i for i, c in enumerate(u["meta"]["cells"])}
    code = LB.SESS_CODE[sess]
    out = []
    for r in base_rows:
        x = LB.unit_cell(u, idx[r["id"]])
        m = x["sess"] == code
        if side is not None:
            m = m & L.side_mask(side, root, x["date"], x["side"])
        st = LB.stats(x["net"][m])
        out.append({"id": r["id"], "vi": r["vi"], "xi": r["xi"], "stop_mode": r.get("stop_mode"), "tgt_r": r.get("tgt_r"),
                    "dead": r.get("dead", False), "net": st["net"], "trades": st["trades"], "t": st["t"], "sig": LB.trade_sig(x, m)})
    return out


def c1_fast(member: dict, pool: dict, K: int, seed: int) -> dict:
    """library.c1_draws with the SAME matching plan (date + session; shortfall from the nearest dates of the session), the K
    draws vectorised. -> {'nets', 'mean', 'lift', 'p_beat', 'short', 'fallback_share'}."""
    rng = np.random.default_rng(int(seed))
    md, ms, mnet = np.asarray(member["date"]), np.asarray(member["sess"]), float(np.asarray(member["net"], np.float64).sum())
    pd_, ps, pn = np.asarray(pool["date"]), np.asarray(pool["sess"]), np.asarray(pool["net"], np.float64)
    by: dict = {}
    for i, (d, s) in enumerate(zip(pd_.tolist(), ps.tolist())):
        by.setdefault((d, s), []).append(i)
    by_sess = {s: np.flatnonzero(ps == s) for s in set(ps.tolist())}
    groups: dict = {}
    for d, s in zip(md.tolist(), ms.tolist()):
        groups[(d, s)] = groups.get((d, s), 0) + 1
    nets, fb, short = np.zeros(K), 0, 0
    for (d, s), k in sorted(groups.items()):
        own = np.array(by.get((d, s), []), np.int64)
        need = k - len(own)
        extra = np.zeros(0, np.int64)
        if need > 0:
            cand = by_sess.get(s, np.zeros(0, np.int64))
            cand = cand[pd_[cand] != d]
            if len(cand):
                dist = np.abs(pd_[cand] - d)
                cut = np.sort(dist)[min(need, len(dist)) - 1]
                extra = cand[dist <= cut]
            got = min(need, len(extra))
            fb += got
            short += need - got
        for arr, kk in ((own, min(k, len(own))), (extra, max(0, min(need, len(extra))))):
            if not kk:
                continue
            if kk >= len(arr):
                nets += pn[arr].sum()
            else:
                pick = np.argsort(rng.random((K, len(arr))), axis=1)[:, :kk]
                nets += pn[arr][pick].sum(axis=1)
    n = int(len(md))
    return {"nets": nets, "mean": round(float(nets.mean()), 2), "lift": round(mnet - float(nets.mean()), 2),
            "p_beat": float((mnet > nets).mean()), "short": int(short), "fallback_share": (fb / n) if n else 0.0, "K": K}


def day_subset_test(xu: dict, side: str, root: str, seed: int) -> dict:
    """(e) for T1-T3: the side's net against DRAWS random same-size subsets of the central variant's own trading days
    (the days of the tool's universe on which it traded). -> {'p', 'days_side', 'days_universe', 'net'}"""
    lab = L.root_labels(root)
    days, inv = np.unique(np.asarray(xu["date"]), return_inverse=True)
    daily = np.zeros(len(days))
    np.add.at(daily, inv, np.asarray(xu["net"], np.float64))
    uni = np.array([L.day_labelled(side, lab.get(int(o))) for o in days], bool)
    ins = np.array([L.day_in_side(side, lab.get(int(o))) for o in days], bool)
    d_u, k, n = daily[uni], int(ins.sum()), int(uni.sum())
    obs = float(daily[ins].sum())
    if k == 0 or k >= n:
        return {"p": 0.0, "days_side": k, "days_universe": n, "net": round(obs, 2)}
    rng = np.random.default_rng(int(seed))
    nets = np.zeros(DRAWS)
    for a in range(0, DRAWS, 500):
        pick = np.argsort(rng.random((500, n)), axis=1)[:, :k]
        nets[a:a + 500] = d_u[pick].sum(axis=1)
    return {"p": float((obs > nets).mean()), "days_side": k, "days_universe": n, "net": round(obs, 2),
            "null_mean": round(float(nets.mean()), 2), "null_p994": round(float(np.percentile(nets, 100 * ALPHA)), 2)}


def yearly(x: dict, root: str, cal: list) -> dict:
    z = LB.sized(x, root)
    keep = ("period", "trades", "net", "win", "pf", "max_dd", "sharpe", "avg_trade", "worst_open_loss", "t")
    return {"c1": [{k: r[k] for k in keep} for r in LB.per_year(x, cal)],
            "r1000": [{k: r[k] for k in keep} for r in LB.per_year(z, cal, z["cost"])],
            "micros_median": int(np.median(z["micros"][z["micros"] > 0])) if (z["micros"] > 0).any() else 0}


def judge_side(uid: str, side, table: list, cell_of, control, root: str, bar: float, cal: list, timed: bool) -> dict:
    """Tests (a)-(e) of one side. cell_of(id) -> the cell's packed arrays in the unit-session (unfiltered);
    control(cid, side, xs, K, fast) -> the matched control restricted the same way."""
    pl = LB.plateau(table)
    row = {"uid": uid, "side": side or "all", "tool": L.TOOL.get(side, "-"), "cells": pl["cells"], "positive": pl["positive"],
           "share_pos": pl["share_pos"], "median_net": pl["median_net"], "v60": pl["verdicts"]["60"], "v70": pl["verdicts"]["70"],
           "v80": pl["verdicts"]["80"], "central": pl["member"], "bar": round(bar, 4), "b": bool(pl["pass"]),
           "best_net": pl["best_net"], "worst_net": pl["worst_net"]}
    if pl["member"] is None:
        row.update(trades=0, net=0.0, t=None, a=False, c=False, d=False, e=False)
        row["pass"] = False
        return row
    xu = cell_of(pl["member"])
    m = np.ones(len(xu["net"]), bool) if side is None else L.side_mask(side, root, xu["date"], xu["side"])
    xs = masked(xu, m)
    st = LB.stats(xs["net"])
    t = st["t"] if st["t"] is not None else 0.0
    row.update(trades=st["trades"], net=st["net"], t=t, win=st["win"], pf=st["pf"], a=bool(st["trades"] >= LB.MIN_TRADES),
               d=bool(t >= bar))
    c = control(pl["member"], side, xs, 200, False)
    row.update(ctrl_lift=c["lift"], ctrl_p_beat=c.get("p_beat"), ctrl_short=c.get("short", 0), ctrl_mean=c.get("mean"),
               ctrl_fallback=round(c.get("fallback_share", 0.0), 4), c=bool(c["lift"] > 0 and not c.get("short", 0)))
    if side is None:
        row["e"] = None
        row["pass"] = None
    elif L.TOOL[side] == "T4":
        e = control(pl["member"], side, xs, DRAWS, True)
        row.update(e_p=e["p_beat"], e=bool(e["p_beat"] >= ALPHA and not e.get("short", 0)), e_kind="same-side random-entry draws",
                   e_lift=e["lift"])
    else:
        e = day_subset_test(xu, side, root, LB.default_seed(f"{uid}|{side}", "e"))
        row.update(e_p=e["p"], e=bool(e["p"] >= ALPHA), e_kind="random same-size day subsets", days_side=e["days_side"],
                   days_universe=e["days_universe"], e_null_mean=e.get("null_mean"), e_null_p994=e.get("null_p994"))
    if side is not None:
        row["pass"] = bool(row["a"] and row["b"] and row["c"] and row["d"] and row["e"])
    row["years"] = yearly(xs, root, cal)
    return row


def unit_job(r: dict) -> dict:
    """All sides of ONE real unit (a near_misses.csv row)."""
    uid, key, sess, root, tf, fam = r["uid"], r["key"], r["sess"], r["root"], str(r["tf"]), r["family"]
    out = CACHE / (uid.replace("|", "__").replace("=", "-") + ".json")
    if out.exists():
        return json.loads(out.read_text())
    u = load(key)
    timed = fam.startswith("straddle_t_")
    label = r.get("label") or ""
    base = LB.plateau_units(u, sess)[label]
    idx = {c["id"]: i for i, c in enumerate(u["meta"]["cells"])}
    code = LB.SESS_CODE[sess]
    cal = LB.calendar("build", root)
    bar = BARS[f"{'shift' if timed else 'c1'}-{root}"]["bar"]

    def cell_of(cid):
        x = LB.unit_cell(u, idx[cid])
        return masked(x, x["sess"] == code)

    def control(cid, side, xs, K, fast):
        seed = LB.default_seed(f"{uid}|{side}", "build" if not fast else "build-e")
        if timed:
            su = load(f"{fam}-{root}-tf{tf}-shift")
            parts = []
            for sd in (1, 2):
                x = LB.unit_cell(su, f"s{sd}_{cid}")
                parts.append(x if side is None else masked(x, L.side_mask(side, root, x["date"], x["side"])))
            if not fast:
                nets = [float(p["net"].sum()) for p in parts]
                return {"lift": round(float(xs["net"].sum()) - float(np.mean(nets)), 2), "mean": round(float(np.mean(nets)), 2), "short": 0}
            pool = {k: np.concatenate([p[k] for p in parts]) for k in ("date", "sess", "net")}
            pool["sess"] = np.zeros(len(pool["net"]), np.int8)                    # a random minute: matched by date only
            return c1_fast({"date": xs["date"], "sess": np.zeros(len(xs["net"]), np.int8), "net": xs["net"]}, pool, K, seed)
        pu = load(f"c1-{root}-tf{tf}")
        parts = [LB.unit_cell(pu, f"s{sd}_{exit_id(cid)}") for sd in (1, 2)]
        pool = {k: np.concatenate([p[k] for p in parts]) for k in ("date", "sess", "net", "side")}
        if side is not None:
            pm = L.side_mask(side, root, pool["date"], pool["side"])
            pool = {k: v[pm] for k, v in pool.items()}
        return c1_fast(xs, pool, K, seed) if fast else LB.c1_draws(xs, pool, K=K, seed=seed)

    rows = []
    for side in (None,) + L.SIDES:
        row = judge_side(uid, side, side_table(u, sess, base, side, root), cell_of, control, root, bar, cal, timed)
        row.update(key=key, family=fam, root=root, tf=tf, sess=sess, label=label, timed=timed,
                   split_exact=(side is None or L.TOOL[side] != "T4"))
        rows.append(row)
    res = {"uid": uid, "rows": rows}
    CACHE.mkdir(exist_ok=True)
    out.write_text(json.dumps(res, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
    return res


def placebo_job(a: tuple) -> dict:
    """All sides of ONE placebo unit: the random-entry store of (root, tf) in a session, seed A as the 'strategy', seed B
    (same exit cell) as its matched control. Nothing here is a strategy: every pass is luck."""
    root, tf, sess, sa = a
    uid = f"placebo-c1-{root}-tf{tf}|{sess}|seed{sa}"
    out = CACHE / (uid.replace("|", "__") + ".json")
    if out.exists():
        return json.loads(out.read_text())
    pu = load(f"c1-{root}-tf{tf}")
    sb = 2 if sa == 1 else 1
    base = [t for t in LB.session_table(pu, sess) if t["id"].startswith(f"s{sa}_")]
    idx = {c["id"]: i for i, c in enumerate(pu["meta"]["cells"])}
    code = LB.SESS_CODE[sess]
    cal = LB.calendar("build", root)
    bar = BARS[f"c1-{root}"]["bar"]

    def cell_of(cid):
        x = LB.unit_cell(pu, idx[cid])
        return masked(x, x["sess"] == code)

    def control(cid, side, xs, K, fast):
        seed = LB.default_seed(f"{uid}|{side}", "build" if not fast else "build-e")
        x = LB.unit_cell(pu, f"s{sb}_{exit_id(cid)}")
        pool = {k: x[k] for k in ("date", "sess", "net", "side")}
        if side is not None:
            pm = L.side_mask(side, root, pool["date"], pool["side"])
            pool = {k: v[pm] for k, v in pool.items()}
        return c1_fast(xs, pool, K, seed) if fast else LB.c1_draws(xs, pool, K=K, seed=seed)

    rows = []
    for side in (None,) + L.SIDES:
        row = judge_side(uid, side, side_table(pu, sess, base, side, root), cell_of, control, root, bar, cal, False)
        row.update(key=f"c1-{root}-tf{tf}", family="random", root=root, tf=tf, sess=sess, label=f"seed{sa}", timed=False, split_exact=True)
        row.pop("years", None)
        rows.append(row)
    res = {"uid": uid, "rows": rows}
    CACHE.mkdir(exist_ok=True)
    out.write_text(json.dumps(res, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
    return res


def units() -> list:
    rows = list(csv.DictReader((ADMIT / "near_misses.csv").open()))
    return [r for r in rows if r["fail"] == "bar" and r["weak"] == "False" and r["penalty"] == "False"]


FLAT = ("uid", "family", "root", "tf", "sess", "label", "side", "tool", "cells", "positive", "share_pos", "median_net", "v60", "v70",
        "v80", "central", "trades", "net", "t", "win", "pf", "bar", "ctrl_lift", "ctrl_p_beat", "ctrl_short", "ctrl_fallback", "e_kind",
        "e_p", "days_side", "days_universe", "a", "b", "c", "d", "e", "pass", "split_exact", "best_net", "worst_net")


def write_csv(path: Path, results: list) -> list:
    rows = [r for x in results for r in x["rows"]]
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, FLAT, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return rows


def counts(rows: list) -> dict:
    s = [r for r in rows if r["side"] != "all"]
    return {"sides": len(s), **{k: sum(bool(r[k]) for r in s) for k in ("a", "b", "c", "d", "e", "pass")},
            "by_side": {sd: {k: sum(bool(r[k]) for r in s if r["side"] == sd) for k in ("a", "b", "c", "d", "e", "pass")} for sd in L.SIDES}}


def main(mode: str) -> None:
    CACHE.mkdir(exist_ok=True)
    if mode == "units":
        us = sorted(units(), key=lambda r: r["key"])
        with Pool(8) as pool:
            res = list(pool.imap(unit_job, us, chunksize=1))
        rows = write_csv(OUT / "sides.csv", res)
        (OUT / "sides.json").write_text(json.dumps(res))
        c = counts(rows)
        (OUT / "sides_counts.json").write_text(json.dumps({"units": len(us), **c}, indent=1))
        print("units", len(us), json.dumps(c))
        for r in rows:
            if r["side"] != "all" and r["pass"]:
                print("PASS", r["uid"], r["side"], r["central"], r["trades"], r["net"], round(r["t"], 3))
    elif mode == "placebo":
        us = units()
        combos = sorted({(r["root"], str(r["tf"]), r["sess"]) for r in us if not r["family"].startswith("straddle_t_")})
        jobs = [(a, b, c, sd) for a, b, c in combos for sd in (1, 2)]
        with Pool(8) as pool:
            res = list(pool.imap(placebo_job, jobs, chunksize=1))
        rows = write_csv(OUT / "placebo.csv", res)
        c = counts(rows)
        (OUT / "placebo_counts.json").write_text(json.dumps({"placebo_units": len(jobs), **c}, indent=1))
        print("placebo units", len(jobs), json.dumps(c))
        for r in rows:
            if r["side"] != "all" and r["pass"]:
                print("PLACEBO PASS", r["uid"], r["side"], r["central"], r["trades"], r["net"], round(r["t"], 3))
    elif mode == "member":
        r = next(x for x in csv.DictReader((ADMIT / "build_units.csv").open()) if x["uid"] == "orb-NQ-tf1|pre|")
        res = unit_job(r)
        write_csv(OUT / "member_orb_sides.csv", [res])
        (OUT / "member_orb_sides.json").write_text(json.dumps(res))
        for x in res["rows"]:
            print(x["side"], x["central"], x["trades"], x["net"], None if x["t"] is None else round(x["t"], 2), x["share_pos"],
                  {k: x.get(k) for k in ("a", "b", "c", "d", "e", "pass")})
    else:
        raise SystemExit("units | placebo | member")


if __name__ == "__main__":
    main(sys.argv[1])

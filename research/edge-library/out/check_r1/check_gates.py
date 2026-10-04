"""CHECKER (stage 2b) -- BUILD gates of every round-1 unit recomputed from the stores with MY OWN code (numpy + json only;
library.py and the analyst's scripts are not imported), then compared with out/admit_r1/build_units.csv.
  heat map   judged cells = not author ('info') cells, not dead variants (a variant with no trade in the session in any exit
             cell), identical trade lists once. pass = median net > 0 and share(net > 0) >= 60 %.
  central    the positive judged cell whose net is closest to the median (ties: lowest variant, then exit index).
  control    bar families: EXPECTED net of a day- and session-matched random-entry ledger with the same exit cell (pool
             c1-<ROOT>-tf<tf>, seeds 1 + 2): sum over (date, session) of k x the pool's mean net there (nearest dates when the
             pool is short) -- the exact mean the analyst's 200 random draws estimate. Time-fired: mean of the same cell in the
             two seeds of the '-shift' store. lift = central net - control.
  bar        95th percentile of the best cell t of every null replicate: bar families the four C1 pools x 7 sessions x 2 seeds
             of the market; time-fired the round-1 shift stores of the market (2 seeds each, all sessions together).
Reads runs/ only (period build asserted on every store). Writes out/check_r1/check_gates.json + my_build_units.csv."""
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[2]
RUNS = W / "runs"
OUT = Path(__file__).resolve().parent
SESS7 = ("eve", "asia", "london", "pre", "nyam", "mid", "pm")
R1 = ("vwap_trend_pull", "va_reclaim", "orb_confirm", "late_mom", "open_fade", "vol_spike_break",
      "straddle_tight_0830", "straddle_tight_0930", "straddle_tight_1000")
TIMED = ("late_mom", "straddle_tight_0830", "straddle_tight_0930", "straddle_tight_1000")
_S = {}


def load(key):
    if key not in _S:
        d = RUNS / key
        m = json.loads((d / "run.json").read_text())
        assert m.get("period") == "build" and m["range"]["end"] <= "2023-12-31" and not m["range"].get("holdout"), key
        z = np.load(d / "cells.npz")
        u = {k: z[k] for k in z.files}
        assert not len(u["date"]) or int(u["date"].max()) <= 738885, key          # 2023-12-31 as an ordinal
        u["meta"] = m
        u["idx"] = {c["id"]: i for i, c in enumerate(m["cells"])}
        _S[key] = u
    return _S[key]


def cell(u, i, sess=None):
    a, b = int(u["off"][i]), int(u["off"][i + 1])
    x = {k: u[k][a:b] for k in ("date", "entry_ms", "dur_s", "net", "side", "sess")}
    if sess not in (None, "all"):
        m = x["sess"] == SESS7.index(sess)
        x = {k: v[m] for k, v in x.items()}
    return x


def tstat(net):
    n = len(net)
    if n < 2:
        return None
    sd = float(np.std(net, ddof=1))
    return float(np.mean(net) / (sd / math.sqrt(n))) if sd > 0 else None


def sig(x):
    if not len(x["net"]):
        return "empty"
    h = hashlib.sha1()
    for k in ("entry_ms", "dur_s", "side"):
        h.update(np.ascontiguousarray(x[k], np.int64).tobytes())
    h.update(np.round(x["net"] * 100).astype(np.int64).tobytes())
    return h.hexdigest()


def heat(u, sess, pick=None):
    """{label: {'rows': judged rows, ...}} of one store-session; label '' or 'dir=long' / 'dir=short'."""
    cells = u["meta"]["cells"]
    axis = u["meta"].get("mirror") or None
    rows = []
    for i, c in enumerate(cells):
        x = cell(u, i, sess)
        rows.append({"id": c["id"], "vi": c["vi"], "xi": c["xi"], "net": round(float(x["net"].sum()), 2), "trades": len(x["net"]),
                     "t": tstat(x["net"]), "sig": sig(x), "info": bool(c.get("info")),
                     "label": f"{axis}={c['variant'][axis]}" if axis else "", "stop": (c.get("exit") or {}).get("stop_mode"),
                     "tgt": (c.get("exit") or {}).get("tgt_r")})
    alive = {r["vi"] for r in rows if r["trades"]}
    out = {}
    for lab in sorted({r["label"] for r in rows}):
        rs = [r for r in rows if r["label"] == lab and not r["info"]]
        live = sorted((r for r in rs if r["vi"] in alive), key=lambda r: (r["vi"], r["xi"]))
        seen, judged = set(), []
        for r in live:
            if r["sig"] in seen:
                continue
            seen.add(r["sig"])
            judged.append(r)
        if not judged:
            out[lab] = {"cells": 0, "share": None, "median": None, "pass": False, "central": None, "rows": []}
            continue
        net = np.array([r["net"] for r in judged])
        med, sh = float(np.median(net)), float((net > 0).mean())
        pos = [r for r in judged if r["net"] > 0]
        cen = min(pos, key=lambda r: (round(abs(r["net"] - med), 6), r["vi"], r["xi"])) if pos else None
        out[lab] = {"cells": len(judged), "cells_all": len(rs), "dead": len(rs) - len(live), "dup": len(live) - len(judged),
                    "share": sh, "median": med, "pass": bool(med > 0 and sh >= 0.6 - 1e-12), "p70": bool(med > 0 and sh >= 0.7 - 1e-12),
                    "p80": bool(med > 0 and sh >= 0.8 - 1e-12), "central": cen, "rows": judged}
    return out


def c1_expected(x, pool):
    """Expected net of the day- and session-matched random ledger; (expected, unmatched trades)."""
    pd_, ps, pn = pool["date"], pool["sess"], pool["net"]
    order = np.lexsort((pd_, ps))
    pd_, ps, pn = pd_[order], ps[order], pn[order]
    tot, short = 0.0, 0
    keys, counts = np.unique(np.stack([x["date"].astype(np.int64), x["sess"].astype(np.int64)]), axis=1, return_counts=True)
    for (d, s), k in zip(keys.T.tolist(), counts.tolist()):
        ms = ps == s
        own = pn[ms & (pd_ == d)]
        if len(own) >= k:
            tot += k * float(own.mean())
            continue
        tot += float(own.sum())
        need = k - len(own)
        cm = ms & (pd_ != d)
        if not cm.any():
            short += need
            continue
        dist = np.abs(pd_[cm] - d)
        cut = np.sort(dist)[min(need, len(dist)) - 1]
        ex = pn[cm][dist <= cut]
        got = min(need, len(ex))
        tot += got * float(ex.mean())
        short += need - got
    return tot, short


def main():
    keys = sorted(p.parent.name for p in RUNS.glob("*/run.json"))
    metas = {k: json.loads((RUNS / k / "run.json").read_text()) for k in keys}
    assert all(m.get("period") == "build" for m in metas.values()), "a non-BUILD store sits in runs/"
    build = [k for k in keys if metas[k].get("stage") == "build" and metas[k]["family"] in R1]
    print("round-1 BUILD stores", len(build), flush=True)
    # ---- nulls: bars
    reps = []
    for k in keys:
        m = metas[k]
        if m.get("stage") != "null":
            continue
        if m.get("control") == "c1":
            u = load(k)
            for s in SESS7:
                for sd in (1, 2):
                    idx = [i for i, c in enumerate(m["cells"]) if c["id"].startswith(f"s{sd}_")]
                    ts_ = [tstat(cell(u, i, s)["net"]) or 0.0 for i in idx]
                    nets = [float(cell(u, i, s)["net"].sum()) for i in idx]
                    reps.append({"group": f"c1-{m['root']}", "key": k, "seed": sd, "sess": s, "best_t": max(ts_),
                                 "share": float(np.mean(np.array(nets) > 0)), "median": float(np.median(nets)),
                                 "cen_t": None, "nets": nets, "ts": ts_})
        elif m.get("control") == "shift":
            u = load(k)
            g = f"shift-{m['root']}" if m["family"] in TIMED else f"shift_s1-{m['root']}"
            for sd in (1, 2):
                idx = [i for i, c in enumerate(m["cells"]) if c["id"].startswith(f"s{sd}_")]
                ts_ = [tstat(cell(u, i)["net"]) or 0.0 for i in idx]
                nets = [float(cell(u, i)["net"].sum()) for i in idx]
                reps.append({"group": g, "key": k, "seed": sd, "sess": "all", "best_t": max(ts_),
                             "share": float(np.mean(np.array(nets) > 0)), "median": float(np.median(nets)), "nets": nets, "ts": ts_})
    bars = {}
    for g in sorted({r["group"] for r in reps}):
        b = sorted(r["best_t"] for r in reps if r["group"] == g)
        bars[g] = {"bar": float(np.percentile(b, 95)), "nulls": len(b), "max": b[-1], "best": [round(v, 3) for v in b]}
    for root in ("NQ", "ES", "GC"):
        b = sorted(r["best_t"] for r in reps if r["group"] in (f"shift-{root}", f"shift_s1-{root}"))
        bars[f"shift_all-{root}"] = {"bar": float(np.percentile(b, 95)), "nulls": len(b), "max": b[-1]}
    # like-for-like sensitivity (mine): the random-minute tight brackets only, all three markets
    b = sorted(r["best_t"] for r in reps if r["group"].startswith("shift-") and "straddle_tight" in r["key"])
    bars["tight_all_roots"] = {"bar": float(np.percentile(b, 95)), "nulls": len(b), "max": b[-1], "best": [round(v, 3) for v in b]}
    # ---- null "units": how often does a random unit pass heat map + bar (luck rate)
    luck = {}
    for r in reps:
        nets, ts_ = np.array(r["nets"]), r["ts"]
        med, sh = float(np.median(nets)), float((nets > 0).mean())
        ok = med > 0 and sh >= 0.6 - 1e-12
        cen_t = None
        if (nets > 0).any():
            j = min((i for i in range(len(nets)) if nets[i] > 0), key=lambda i: (round(abs(nets[i] - med), 6), i))
            cen_t = ts_[j]
        g = luck.setdefault(r["group"], {"units": 0, "heat": 0, "both": 0})
        g["units"] += 1
        g["heat"] += ok
        g["both"] += bool(ok and (cen_t or 0.0) > bars[r["group"]]["bar"])
    # ---- units
    rows = []
    for k in build:
        u = load(k)
        m = u["meta"]
        fam, root, tf = m["family"], m["root"], str(m["tf"])
        codes = sorted({int(v) for v in np.unique(u["sess"]) if v >= 0})
        sessions = ["all"] if fam == "straddle_tight_0930" else [SESS7[c] for c in codes]
        for s in sessions:
            for lab, h in heat(u, s).items():
                r = {"uid": f"{k}|{s}|{lab}", "family": fam, "root": root, "tf": tf, "sess": s, "cells": h["cells"],
                     "share": h["share"], "median": h["median"], "p60": h["pass"], "p70": h.get("p70", False), "p80": h.get("p80", False),
                     "central": h["central"]["id"] if h["central"] else None,
                     "central_net": h["central"]["net"] if h["central"] else None,
                     "central_t": h["central"]["t"] if h["central"] else None,
                     "central_trades": h["central"]["trades"] if h["central"] else None}
                if h["pass"]:
                    cid = h["central"]["id"]
                    if fam in TIMED:
                        su = load(f"{fam}-{root}-tf{tf}-shift")
                        nets = [float(cell(su, su["idx"][f"s{sd}_{cid}"])["net"].sum()) for sd in (1, 2)]
                        r.update(ctrl=float(np.mean(nets)), short=0, lift=h["central"]["net"] - float(np.mean(nets)))
                        g = f"shift-{root}"
                    else:
                        pu = load(f"c1-{root}-tf{tf}")
                        xid = cid.rsplit("_", 1)[-1]
                        parts = [cell(pu, pu["idx"][f"s{sd}_{xid}"]) for sd in (1, 2)]
                        pool = {q: np.concatenate([p[q] for p in parts]) for q in ("date", "sess", "net")}
                        e, short = c1_expected(cell(u, u["idx"][cid], s), pool)
                        r.update(ctrl=e, short=short, lift=h["central"]["net"] - e)
                        g = f"c1-{root}"
                    r["bar"] = bars[g]["bar"]
                    r["g_ctrl"] = bool(r["lift"] > 0 and not r["short"])
                    r["g_bar"] = bool((r["central_t"] or 0.0) > r["bar"])
                    r["weak"] = bool(m.get("weak"))
                    r["build_pass"] = bool(r["g_ctrl"] and r["g_bar"] and (not r["weak"] or (r["central_t"] or 0) >= 3.0))
                rows.append(r)
    # ---- compare with the analyst
    theirs = {r["uid"]: r for r in csv.DictReader((W / "out" / "admit_r1" / "build_units.csv").open())}
    mine = {r["uid"]: r for r in rows}
    cmp = {"units_mine": len(mine), "units_theirs": len(theirs), "only_mine": sorted(set(mine) - set(theirs)),
           "only_theirs": sorted(set(theirs) - set(mine)), "share_diff": [], "pass_diff": [], "central_diff": [], "lift_sign_diff": [],
           "build_pass_diff": [], "max_abs_lift_gap": 0.0}
    for uid in sorted(set(mine) & set(theirs)):
        a, b = mine[uid], theirs[uid]
        if b["share_pos"] not in ("", None) and a["share"] is not None and abs(float(b["share_pos"]) - a["share"]) > 6e-5:
            cmp["share_diff"].append((uid, a["share"], b["share_pos"]))
        if (b["plateau"] == "True") != a["p60"]:
            cmp["pass_diff"].append(uid)
        if a["p60"]:
            if b["member"] != a["central"]:
                cmp["central_diff"].append((uid, a["central"], b["member"]))
            if b["ctrl_lift"] not in ("", None):
                gap = abs(float(b["ctrl_lift"]) - a["lift"])
                cmp["max_abs_lift_gap"] = max(cmp["max_abs_lift_gap"], gap)
                if (float(b["ctrl_lift"]) > 0) != (a["lift"] > 0):
                    cmp["lift_sign_diff"].append((uid, round(a["lift"], 1), b["ctrl_lift"]))
            if (b["build_pass"] == "True") != a["build_pass"]:
                cmp["build_pass_diff"].append((uid, a["build_pass"], b["build_pass"], b["fail"]))
    counts = {"units": len(rows), "p60": sum(r["p60"] for r in rows), "p70": sum(r["p70"] for r in rows), "p80": sum(r["p80"] for r in rows),
              "p60_ctrl": sum(bool(r["p60"] and r.get("g_ctrl")) for r in rows),
              "p60_ctrl_bar": sum(bool(r["p60"] and r.get("build_pass")) for r in rows)}
    passers = [r for r in rows if r["p60"] and r.get("build_pass")]
    near = sorted((r for r in rows if r["p60"] and r.get("g_ctrl") and not r.get("g_bar")), key=lambda r: r["bar"] - (r["central_t"] or 0))
    print("counts", counts)
    print("bars", {k: (round(v["bar"], 4), v["nulls"]) for k, v in bars.items()})
    print("luck", luck)
    print("compare", {k: (v if not isinstance(v, list) else (len(v), v[:6])) for k, v in cmp.items()})
    for r in passers:
        print("PASS", r["uid"], r["central"], "share", round(r["share"], 4), "cells", r["cells"], "net", r["central_net"], "t", round(r["central_t"], 3),
              "bar", round(r["bar"], 3), "lift", round(r["lift"], 1), "trades", r["central_trades"])
    for r in near[:8]:
        print("NEAR(bar)", r["uid"], r["central"], "share", round(r["share"], 4), "t", round(r["central_t"] or 0, 3), "bar", round(r["bar"], 3),
              "lift", round(r["lift"], 1))
    cols = []
    for r in rows:
        cols += [c for c in r if c not in cols]
    with (OUT / "my_build_units.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, cols)
        w.writeheader()
        w.writerows(rows)
    (OUT / "check_gates.json").write_text(json.dumps({"counts": counts, "bars": bars, "luck": luck, "compare": cmp,
                                                      "passers": passers, "near_bar": near[:8]}, indent=1, default=str))


if __name__ == "__main__":
    main()

"""CHECKER (adversarial, read-only on runs/): own plateau / null / hold / date scan of every store. Uses no library.py judging code."""
import json, sys, math, datetime as dt
from pathlib import Path
from multiprocessing import Pool
import numpy as np, pandas as pd

W = Path("/Users/ramoscapital/ramos-quant-homebase/research/edge-library")
OUT = W / "out" / "check_admit"
SESS7 = ("eve", "asia", "london", "pre", "nyam", "mid", "pm")
SC = {s: i for i, s in enumerate(SESS7)}
REASONS = ("sl", "tp", "time", "eod", "trail", "bars", "book", "other")
SESS_END = {"asia": 3 * 3600, "london": 8 * 3600 + 25 * 60, "pre": 9 * 3600 + 30 * 60, "nyam": 11 * 3600, "mid": 13 * 3600 + 30 * 60,
            "eve": 23 * 3600 + 59 * 60}


def load(d):
    meta = json.loads((d / "run.json").read_text())
    z = np.load(d / "cells.npz")
    return meta, {k: z[k] for k in z.files}


def tstat(x):
    n = len(x)
    if n < 2:
        return None
    sd = x.std(ddof=1)
    return float(x.mean() / (sd / math.sqrt(n))) if sd > 0 else None


def cells_in(meta, a, sess):
    """per cell: net, n, t, sig, vi, xi for a session ('all' = everything)"""
    off = a["off"]
    rows = []
    for i, c in enumerate(meta["cells"]):
        s, e = int(off[i]), int(off[i + 1])
        m = np.ones(e - s, bool) if sess == "all" else a["sess"][s:e] == SC[sess]
        net = a["net"][s:e][m].astype(np.float64)
        if len(net):
            sig = hash((a["entry_ms"][s:e][m].tobytes(), a["dur_s"][s:e][m].tobytes(), a["side"][s:e][m].tobytes(),
                        np.round(net * 100).astype(np.int64).tobytes()))
        else:
            sig = "empty"
        rows.append({"id": c["id"], "vi": c["vi"], "xi": c["xi"], "net": float(net.sum()), "n": int(len(net)), "t": tstat(net), "sig": sig,
                     "variant": c["variant"], "exit": c.get("exit") or {}})
    return rows


def plateau(rows):
    alive = {r["vi"] for r in rows if r["n"]}
    live = sorted((r for r in rows if r["vi"] in alive), key=lambda r: (r["vi"], r["xi"]))
    seen, j = set(), []
    for r in live:
        if r["sig"] in seen:
            continue
        seen.add(r["sig"])
        j.append(r)
    if not j:
        return {"pass": False, "cells": 0, "share": None, "median": None, "member": None, "t": None, "net": None, "n": None}
    net = np.array([r["net"] for r in j])
    med, sh = float(np.median(net)), float((net > 0).mean())
    pos = [r for r in j if r["net"] > 0]
    mem = min(pos, key=lambda r: (round(abs(r["net"] - med), 6), r["vi"], r["xi"])) if pos else None
    return {"pass": bool(med > 0 and sh >= 0.6 - 1e-12), "cells": len(j), "share": sh, "median": med,
            "member": mem["id"] if mem else None, "t": mem["t"] if mem else None, "net": mem["net"] if mem else None,
            "n": mem["n"] if mem else None, "best_t": max((r["t"] or 0.0) for r in j)}


def hold_scan(meta, a):
    """exit clock of every trade; -> counts"""
    n = len(a["net"])
    if not n:
        return {"n": 0}
    ex = a["entry_ms"].astype(np.int64) + a["dur_s"].astype(np.int64) * 1000
    et = pd.DatetimeIndex(ex * 1_000_000, tz="UTC").tz_convert("America/New_York")
    sod = (et.hour * 3600 + et.minute * 60 + et.second).to_numpy()
    exd = np.array([d.toordinal() for d in et.date]) if n < 0 else (et.normalize().tz_localize(None).to_numpy().astype("datetime64[D]").astype(np.int64) + 719163)
    rs = a["reason"]
    out = {"n": int(n), "reasons": {REASONS[k]: int((rs == k).sum()) for k in range(len(REASONS)) if (rs == k).any()}}
    clock = np.isin(rs, [2, 3, 7])                       # time / eod / other
    mm = sod[clock] // 60
    u, c = np.unique(mm, return_counts=True)
    out["clock_exit_minutes"] = {f"{int(x)//60:02d}:{int(x)%60:02d}": int(y) for x, y in zip(u, c)}
    # exits after the day's flatten (15:58:00 + 90 s slack) and before 18:00, any reason
    out["after_1600"] = int(((sod > 16 * 3600) & (sod < 18 * 3600)).sum())
    # exit date vs trade date: an exit on a later calendar day than the trade date = held past its day
    out["exit_after_trade_date"] = int((exd > a["date"].astype(np.int64)).sum())
    out["exit_date_gt_or_sod_ge_1559_30"] = int(((exd == a["date"]) & (sod >= 15 * 3600 + 59 * 60 + 30) & (sod < 18 * 3600)).sum())
    # clock exits at the END of the entry session (+- 120 s), pm excluded (its end is the day flat)
    se = 0
    for s, end in SESS_END.items():
        m = clock & (a["sess"] == SC[s])
        if s == "eve":
            se += int((m & (np.abs(sod - end) <= 120)).sum())
        else:
            se += int((m & (np.abs(sod - end) <= 120)).sum())
    out["clock_exit_at_session_end"] = se
    out["max_date"] = dt.date.fromordinal(int(a["date"].max())).isoformat()
    out["min_date"] = dt.date.fromordinal(int(a["date"].min())).isoformat()
    return out


def scan(arg):
    root_dir, key = arg
    d = W / root_dir / key
    meta, a = load(d)
    res = {"dir": root_dir, "key": key, "stage": meta.get("stage"), "period": meta.get("period"), "range": meta.get("range"),
           "hold_to": meta.get("hold_to"), "cell_hold": sorted({(c.get("inputs") or {}).get("hold_to") for c in meta["cells"]}, key=str),
           "control": meta.get("control"), "family": meta.get("family"), "root": meta.get("root"), "tf": str(meta.get("tf")),
           "base": meta.get("base"), "weak": bool(meta.get("weak")), "n_cells": len(meta["cells"]),
           "sess_present": [SESS7[int(s)] for s in np.unique(a["sess"]) if s >= 0] if len(a["sess"]) else [],
           "sess_none": int((a["sess"] < 0).sum()), "hold": hold_scan(meta, a), "units": [], "nulls": []}
    present = res["sess_present"]
    ctl = meta.get("control")
    if root_dir == "runs" and meta.get("stage") == "build":
        base = meta.get("base")
        sessions = meta.get("base_pass_sessions") if base else [s for s in SESS7 if s in present]
        axis = meta.get("mirror")
        for s in sessions:
            rows = cells_in(meta, a, s)
            groups = {"": rows}
            if axis:
                groups = {}
                for r in rows:
                    groups.setdefault(f"{axis}={r['variant'][axis]}", []).append(r)
            for lab, g in groups.items():
                pl = plateau(g)
                res["units"].append({"uid": f"{key}|{s}|{lab}", **pl})
    elif root_dir == "runs" and meta.get("stage") == "null":
        if ctl == "c1":
            for s in SESS7:
                rows = cells_in(meta, a, s)
                for sd in (1, 2):
                    g = [r for r in rows if r["id"].startswith(f"s{sd}_")]
                    pl = plateau(g)
                    res["nulls"].append({"group": f"c1-{meta['root']}", "sess": s, "seed": sd, "best_t": max((r["t"] or 0.0) for r in g), **pl})
        elif ctl == "shift":
            rows = cells_in(meta, a, "all")
            for sd in (1, 2):
                g = [r for r in rows if r["id"].startswith(f"s{sd}_")]
                pl = plateau(g)
                res["nulls"].append({"group": f"shift-{meta['root']}", "sess": "all", "seed": sd, "best_t": max((r["t"] or 0.0) for r in g), **pl})
        elif ctl == "c2":
            base = meta.get("base")
            sessions = meta.get("base_pass_sessions") if base else [s for s in SESS7 if s in present]
            axis = meta.get("mirror")
            for s in sessions:
                rows = cells_in(meta, a, s)
                pl = plateau(rows)
                res["nulls"].append({"group": "c2-stage_d" if base else "c2-l2", "sess": s, "seed": meta.get("seed"),
                                     "best_t": max((r["t"] or 0.0) for r in rows), **pl})
    return res


if __name__ == "__main__":
    jobs = [(rd, p.parent.name) for rd in ("runs", "runs_admit") for p in sorted((W / rd).glob("*/run.json"))]
    print("stores", len(jobs), flush=True)
    with Pool(6) as pool:
        out = list(pool.imap_unordered(scan, jobs, chunksize=2))
    (OUT / "scan.json").write_text(json.dumps(out, default=str))
    print("done")

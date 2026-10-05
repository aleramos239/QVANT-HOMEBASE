"""CHECKER OOS -- own recomputation of the saved strategies' verdicts from the stores on disk.
No judge.py code is imported. library.load_unit only reads a store (run.json + cells.npz).
Rule recomputed: EDGE_SPEC "ADMISSION v2" + "CHECKER FIXES" F1-F6 + "PERIODS AMENDED" + "FULL OUT-OF-SAMPLE".
  python chk.py <unit index 0..14 | all> [draws]     -> out/check_oos/res/<unit>.json
Only cells the analyst already read are opened (stores on disk; nothing is simulated here)."""
from __future__ import annotations
import csv, datetime as dt, hashlib, json, sys
from pathlib import Path
import numpy as np

W = Path("/Users/ramoscapital/ramos-quant-homebase/research/edge-library")
HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(W)); sys.path.insert(0, str(W / "engine"))
import library as LB  # noqa: E402  (load_unit, FIELDS, SESS_CODE: reading stores only)

PER = {"build": ("2021-09-22", "2023-12-31"), "pick": ("2024-01-01", "2024-12-31"),
       "check": ("2025-01-01", "2025-12-31"), "exam": ("2026-01-01", "2026-12-31")}
TAG = {"pick": "pick", "check": "check", "exam": "exam"}
PRIO = ["runs", "runs_v2", "runs_admit", "runs_admit_r1", "runs_deepen", "runs_events"]
TIER1 = {"NFP", "CPI", "PPI", "RETAIL", "GDP", "PCE"}
UNITS = [  # (family, root, tf, session, day filter)
    ("straddle_tight_0830", "NQ", "30", "pre", None), ("straddle_tight_0830", "NQ", "30", "pre", "A"),
    ("straddle_tight_0830", "NQ", "30", "pre", "B"), ("straddle_tight_0830", "GC", "30", "pre", "A"),
    ("straddle_tight_0830", "GC", "30", "pre", "B"), ("straddle_tight_1000", "NQ", "30", "nyam", "C"),
    ("straddle_tight_1000", "GC", "30", "nyam", "C"), ("first_bar_mom", "NQ", "30", "mid", None),
    ("first_bar_mom", "NQ", "15", "mid", None), ("first_bar_mom", "ES", "15", "mid", None),
    ("orb", "NQ", "15", "pre", None), ("tema_slope", "NQ", "30", "eve", None), ("donchian", "NQ", "30", "nyam", None),
    ("straddle_t_0830", "NQ", "30", "pre", None), ("straddle_t_1800", "NQ", "30", "eve", None)]


def addr(u):
    return f"{u[0]}-{u[1]}-tf{u[2]}-{u[3]}" + (f"@{u[4]}" if u[4] else "")


IDX = [r for r in json.loads((HERE / "idx.json").read_text()) if r["dir"] != "runs_void" and "error" not in r]
IDX.sort(key=lambda r: (PRIO.index(r["dir"]) if r["dir"] in PRIO else 99, r["dir"], r["key"]))
_ST: dict = {}


def inper(r, period):
    a, b = PER[period]
    return bool(r["start"]) and a <= r["start"] and r["end"] <= b


def load(r):
    k = (r["dir"], r["key"])
    if k not in _ST:
        s = LB.load_unit(r["key"], W / r["dir"])
        s["_i"] = {c["id"]: i for i, c in enumerate(s["meta"]["cells"])}
        _ST[k] = s
    return _ST[k]


def cell(st, cid, sess=None, days=None):
    i = st["_i"][cid]
    a, b = int(st["off"][i]), int(st["off"][i + 1])
    x = {k: st[k][a:b] for k in LB.FIELDS}
    m = np.ones(b - a, bool)
    if sess is not None:
        m &= x["sess"] == LB.SESS_CODE[sess]
    if days is not None:
        m &= np.isin(x["date"].astype(np.int64), days)
    return {k: v[m] for k, v in x.items()}


# ---------------------------------------------------------------- release-day filter (own parse of events.csv)
def event_days(group, events_csv=None, drop=None):
    at, types = {"A": ("08:30", None), "B": ("08:30", TIER1), "C": ("10:00", None)}[group]
    out = set()
    with open(events_csv or W / "engine" / "cache" / "events.csv") as fh:
        for r in csv.DictReader(fh):
            if r["time_et"] == at and (types is None or r["type"] in types) and not (drop and drop(r)):
                out.add(dt.date.fromisoformat(r["date"]).toordinal())
    return np.array(sorted(out), np.int64)


# ---------------------------------------------------------------- tables
def sig(x):
    if not len(x["net"]):
        return "empty"
    h = hashlib.sha1()
    for k in ("entry_ms", "dur_s", "side"):
        h.update(np.ascontiguousarray(x[k], np.int64).tobytes())
    h.update(np.round(np.asarray(x["net"], np.float64) * 100).astype(np.int64).tobytes())
    return h.hexdigest()


def base_rec(u, period, stress=False, need=None):
    fam, root, tf, sess, _ = u
    key = f"{fam}-{root}-tf{tf}" + ("" if period == "build" and not stress else f"-{sess}-{'build' if period == 'build' else TAG[period]}") + ("-stress" if stress else "")
    two = bool(json.loads((W / "runs" / f"{fam}-{root}-tf{tf}" / "run.json").read_text()).get("both_sides_declared"))
    out = []
    for r in IDX:
        if r["key"] != key or not inper(r, period) or r["stress"] != stress or r["control"] in ("c1", "shift", "c2"):
            continue
        if stress and two and r["oco"] != 100:
            continue
        if need is not None and not all(c in load(r)["_i"] for c in need):
            continue
        out.append(r)
    return out


def build_table(u, days):
    fam, root, tf, sess, _ = u
    r = [x for x in IDX if x["dir"] == "runs" and x["key"] == f"{fam}-{root}-tf{tf}"][0]
    st = load(r)
    assert not st["meta"].get("mirror"), "mirror family: not handled"
    rows = []
    for c in st["meta"]["cells"]:
        x0 = cell(st, c["id"], sess)
        x = cell(st, c["id"], sess, days)
        rows.append({"id": c["id"], "vi": c["vi"], "xi": c["xi"], "info": bool(c.get("info")), "n_sess": len(x0["net"]),
                     "net": float(x["net"].sum()), "trades": int(len(x["net"])), "sig": sig(x)})
    alive = {r_["vi"] for r_ in rows if r_["n_sess"]}
    live = sorted([r_ for r_ in rows if not r_["info"] and r_["vi"] in alive], key=lambda r_: (r_["vi"], r_["xi"]))
    seen, judged = set(), []
    for r_ in live:
        if r_["sig"] in seen:
            continue
        seen.add(r_["sig"])
        judged.append(r_)
    return st, r, rows, judged, {"cells": len(rows), "info": sum(r_["info"] for r_ in rows),
                                 "dead": sum(1 for r_ in rows if not r_["info"] and r_["vi"] not in alive), "dup": len(live) - len(judged)}


def tstats(nets, trades):
    nets = np.asarray(nets, float)
    return {"cells": len(nets), "positive": int((nets > 0).sum()), "share_pos": float((nets > 0).mean()), "avg": float(nets.mean()),
            "median": float(np.median(nets)), "avg_trades": float(np.mean(trades))}


# ---------------------------------------------------------------- control: random minute (time-fired) -- every seed on disk
def shift_seeds(u, period, ids):
    fam, root, tf, sess, _ = u
    out = {}
    for r in IDX:
        if r["control"] != "shift" or r["family"] != fam or r["root"] != root or r["tf"] != tf or r["stress"] or not inper(r, period):
            continue
        if r["sess"] not in (None, sess):
            continue
        st = load(r)
        for c in st["meta"]["cells"]:
            sd = int(c["inputs"]["shift_seed"])
            pre = f"s{sd}_"
            assert c["id"].startswith(pre), (r["key"], c["id"], sd)
            if sd in out:
                continue
            if all(pre + i in st["_i"] for i in ids):
                out[sd] = (r, pre)
    return out


def shift_ctl(u, period, ids, days, avg, draws, rng):
    S = shift_seeds(u, period, ids)
    if len(S) < 2:
        return {"pass": False, "why": "fewer than 2 seeds", "seeds": sorted(S)}
    per = {}
    for sd, (r, pre) in sorted(S.items()):
        st = load(r)
        xs = [cell(st, pre + i, None, days) for i in ids]
        per[sd] = xs
    alld = np.unique(np.concatenate([x["date"].astype(np.int64) for xs in per.values() for x in xs] + [np.zeros(0, np.int64)]))
    A = np.zeros((len(per), len(alld)))
    for k, sd in enumerate(sorted(per)):
        for x in per[sd]:
            np.add.at(A[k], np.searchsorted(alld, x["date"].astype(np.int64)), x["net"].astype(float))
    A /= len(ids)
    raw = A.sum(axis=1)
    pick = rng.integers(0, len(per), size=(draws, len(alld)))
    mix = A[pick, np.arange(len(alld))[None, :]].sum(axis=1)
    return {"seeds": sorted(S), "stores": sorted({f"{r['dir']}/{r['key']}" for r, _ in S.values()}), "ctl_mean": float(raw.mean()),
            "raw": [round(float(v), 2) for v in raw], "lift": float(avg - raw.mean()), "p_beat": float((avg > mix).mean()),
            "p_beat_seeds": float((avg > raw).mean()), "n_draws": draws,
            "two_seed_lift": float(avg - raw[:2].mean())}


# ---------------------------------------------------------------- control: random entries (bar-based) -- every seed on disk
def c1_seeds(u, period, xids):
    _, root, tf, sess, _ = u
    out = {}
    for r in IDX:
        if r["control"] != "c1" or r["family"] != "random" or r["root"] != root or r["tf"] != tf or r["stress"] or not inper(r, period):
            continue
        if r["sess"] not in (None, sess):
            continue
        st = load(r)
        for c in st["meta"]["cells"]:
            sd = int(c["inputs"]["seed"])
            pre = f"s{sd}_"
            assert c["id"].startswith(pre), (r["key"], c["id"])
            if sd in out:
                continue
            if all(pre + x in st["_i"] for x in xids):
                out[sd] = (r, pre)
    return out


def c1_ctl(u, yst, period, ids, days, avg, draws, rng, only_seeds=None):
    fam, root, tf, sess, _ = u
    xids = sorted({i.rsplit("_", 1)[-1] for i in ids})
    S = c1_seeds(u, period, xids)
    if only_seeds:
        S = {k: v for k, v in S.items() if k in only_seeds}
    if not S:
        return {"pass": False, "why": "no pool"}
    # pools per exit: date, net, slot key = (date, seed, n-th entry of that seed that day)
    pools, keys = {}, []
    for xid in xids:
        D, N, K = [], [], []
        for sd, (r, pre) in sorted(S.items()):
            x = cell(load(r), pre + xid, sess)
            o = np.lexsort((x["entry_ms"], x["date"]))
            d, n = x["date"][o].astype(np.int64), x["net"][o].astype(float)
            rank = np.zeros(len(d), np.int64)
            for j in range(1, len(d)):
                rank[j] = rank[j - 1] + 1 if d[j] == d[j - 1] else 0
            D.append(d); N.append(n); K.append(d * 100000 + sd * 1000 + rank)
        d, n, k = np.concatenate(D), np.concatenate(N), np.concatenate(K)
        o = np.argsort(d, kind="stable")
        pools[xid] = (d[o], n[o], k[o])
        keys.append(k)
    uni = np.unique(np.concatenate(keys))
    nk = len(uni)
    # per exit: padded [dates x M] matrices of slot index and net
    mats = {}
    for xid, (d, n, k) in pools.items():
        ud, first, cnt = np.unique(d, return_index=True, return_counts=True)
        M = int(cnt.max())
        ix = np.full((len(ud), M), nk, np.int64)
        nm = np.zeros((len(ud), M))
        si = np.searchsorted(uni, k)
        for j in range(len(ud)):
            ix[j, :cnt[j]] = si[first[j]:first[j] + cnt[j]]
            nm[j, :cnt[j]] = n[first[j]:first[j] + cnt[j]]
        mats[xid] = (ud, cnt, ix, nm, d, n, si)
    # the variants: per exit, the dates and trade counts
    var = {}
    ntr = 0
    for cid in ids:
        md = cell(yst, cid, sess, days)["date"].astype(np.int64)
        ntr += len(md)
        var.setdefault(cid.rsplit("_", 1)[-1], []).append(np.unique(md, return_counts=True))
    out = np.zeros(draws)
    fb = short = 0
    CH = 200
    for a in range(0, draws, CH):
        R = min(CH, draws - a)
        P = np.concatenate([rng.random((R, nk), dtype=np.float32), np.full((R, 1), 9.0, np.float32)], axis=1)
        for xid, vs in var.items():
            ud, cnt, ix, nm, d_all, n_all, si_all = mats[xid]
            order = np.argsort(P[:, ix], axis=2, kind="stable")                    # R x D x M
            C = np.cumsum(np.take_along_axis(np.broadcast_to(nm, (R,) + nm.shape), order, 2), axis=2)
            C = np.concatenate([np.zeros((R, len(ud), 1)), C], axis=2)
            for (vd, vk) in vs:
                if not len(vd):
                    continue
                j = np.searchsorted(ud, vd)
                has = (j < len(ud)) & (ud[np.minimum(j, len(ud) - 1)] == vd)
                own = np.where(has, cnt[np.minimum(j, len(ud) - 1)], 0)
                take = np.minimum(own, vk)
                jj = np.minimum(j, len(ud) - 1)
                out[a:a + R] += (C[:, jj, take] * has[None, :]).sum(axis=1)
                for g in np.flatnonzero(own < vk):                               # shortfall: nearest dates of the pool
                    need = int(vk[g] - own[g])
                    ok = ud != vd[g]
                    if not ok.any():
                        if a == 0:
                            short += need
                        continue
                    dist = np.abs(ud[ok] - vd[g])
                    o = np.argsort(dist, kind="stable")
                    cum = np.cumsum(cnt[ok][o])
                    cut = dist[o][min(int(np.searchsorted(cum, need, "left")), len(o) - 1)]
                    use = ud[ok][dist <= cut]
                    m = np.isin(d_all, use)
                    got = min(need, int(m.sum()))
                    if a == 0:
                        fb += got; short += need - got
                    if got == int(m.sum()):
                        out[a:a + R] += float(n_all[m].sum())
                    else:
                        pp = P[:, si_all[m]]
                        od = np.argsort(pp, axis=1)[:, :got]
                        out[a:a + R] += n_all[m][od].sum(axis=1)
    out /= len(ids)
    return {"seeds": sorted(S), "stores": sorted({f"{r['dir']}/{r['key']}" for r, _ in S.values()}), "ctl_mean": float(out.mean()),
            "ctl_sd": float(out.std(ddof=1)), "lift": float(avg - out.mean()), "p_beat": float((avg > out).mean()), "n_draws": draws,
            "fallback_share": fb / max(1, ntr), "short": int(short)}


# ---------------------------------------------------------------- control: day filter
def days_ctl(yst, u, ids, days, subsets, rng):
    sess = u[3]
    d = np.concatenate([cell(yst, c, sess)["date"].astype(np.int64) for c in ids])
    n = np.concatenate([cell(yst, c, sess)["net"].astype(float) for c in ids])
    if not len(d):
        return {"pass": False, "why": "no trade"}
    ud, inv = np.unique(d, return_inverse=True)
    N, T = np.zeros(len(ud)), np.zeros(len(ud))
    np.add.at(N, inv, n); np.add.at(T, inv, 1.0)
    ins = np.isin(ud, days)
    k = int(ins.sum())
    if not k or not T[ins].sum():
        return {"pass": False, "why": "no trade inside the filter"}
    obs, unf = float(N[ins].sum() / T[ins].sum()), float(N.sum() / T.sum())
    vals = np.zeros(subsets)
    for a in range(0, subsets, 500):
        pick = np.argsort(rng.random((500, len(ud))), axis=1)[:, :k]
        vals[a:a + 500] = N[pick].sum(axis=1) / np.maximum(1.0, T[pick].sum(axis=1))
    return {"per_trade": obs, "unfiltered_per_trade": unf, "lift": obs - unf, "days_in": k, "days_all": len(ud), "p_beat": float((obs > vals).mean())}


def controls(u, yst, period, ids, days, avg, draws, rng):
    timed = u[0].startswith("straddle")
    out = {}
    need_p = period == "build"
    if u[4]:
        c = days_ctl(yst, u, ids, days, 4000, rng)
        c["pass"] = bool(c.get("lift", -1) > 0 and (not need_p or c["p_beat"] >= 0.95)) if "why" not in c else False
        out["days"] = c
    c = shift_ctl(u, period, ids, days, avg, draws, rng) if timed else c1_ctl(u, yst, period, ids, days, avg, draws, rng)
    if "why" not in c:
        c["pass"] = bool(c["lift"] > 0 and (not need_p or c["p_beat"] >= 0.95) and not c.get("short"))
    out["shift" if timed else "c1"] = c
    return out


def fast(xs):
    r = {}
    for nm, thr in (("lt5", 5), ("le5", 6)):
        gw = fw = net = fnet = 0.0
        for x in xs:
            n, d = x["net"].astype(float), x["dur_s"]
            f = d < thr
            gw += n[n > 0].sum(); fw += n[f & (n > 0)].sum(); net += n.sum(); fnet += n[f].sum()
        r[nm] = {"winners_share": float(fw / gw) if gw > 0 else None, "net_share": float(fnet / net) if net > 0 else None,
                 "net_fast_avg": float(fnet / max(1, len(xs))), "net_avg": float(net / max(1, len(xs)))}
    return r


def maxdd(x, comm=None):
    """Max drawdown of one variant: closed-trade equity in entry order (own definition; the card's may use daily worst-open)."""
    if not len(x["net"]):
        return 0.0
    o = np.argsort(x["entry_ms"], kind="stable")
    eq = np.cumsum(x["net"][o].astype(float))
    return float((np.maximum.accumulate(np.r_[0.0, eq]) - np.r_[0.0, eq]).max())


def year_block(u, period, ids, days, draws, rng, default=None, survivors=None):
    sess = u[3]
    recs = base_rec(u, period)
    if not recs:
        return None
    yst = load(recs[0])
    miss = [c for c in ids if c not in yst["_i"]]
    assert not miss, (addr(u), period, miss[:3])
    xs = [cell(yst, c, sess, days) for c in ids]
    nets = [float(x["net"].sum()) for x in xs]
    ts = tstats(nets, [len(x["net"]) for x in xs])
    out = {"store": f"{recs[0]['dir']}/{recs[0]['key']}", "n_candidate_stores": len(recs), **ts, "nets": dict(zip(ids, [round(v, 2) for v in nets]))}
    out["t4"] = bool(ts["avg"] > 0 and ts["median"] > 0)
    out["controls"] = controls(u, yst, period, ids, days, ts["avg"], draws, rng)
    out["t5"] = all(c.get("pass") for c in out["controls"].values())
    srecs = base_rec(u, period, stress=True, need=ids)
    if srecs:
        sst = load(srecs[0])
        sn = [float(cell(sst, c, sess, days)["net"].sum()) for c in ids]
        out.update(stress_store=f"{srecs[0]['dir']}/{srecs[0]['key']}", stress_oco=srecs[0]["oco"], stress_avg=float(np.mean(sn)),
                   stress_median=float(np.median(sn)), stress_positive=int((np.array(sn) > 0).sum()), t6=bool(np.mean(sn) > 0),
                   stress_nets=dict(zip(ids, [round(v, 2) for v in sn])))
    else:
        out["t6"] = None
    out["fast"] = fast(xs)
    wins = sum(int((x["net"] > 0).sum()) for x in xs); ntr = sum(len(x["net"]) for x in xs)
    gw = sum(float(x["net"][x["net"] > 0].sum()) for x in xs); gl = -sum(float(x["net"][x["net"] < 0].sum()) for x in xs)
    out.update(win_rate=wins / max(1, ntr), pf=gw / gl if gl > 0 else None, maxdd_avg_of_variants=float(np.mean([maxdd(x) for x in xs])))
    if default:
        dx = cell(yst, default, sess, days)
        out["default"] = {"id": default, "net": float(dx["net"].sum()), "trades": int(len(dx["net"])), "win": float((dx["net"] > 0).mean()) if len(dx["net"]) else None,
                          "maxdd": maxdd(dx)}
        if srecs and default in load(srecs[0])["_i"]:
            out["default"]["stress_net"] = float(cell(load(srecs[0]), default, sess, days)["net"].sum())
    if survivors is not None:
        out["saved_profitable"] = sum(1 for c in survivors if float(cell(yst, c, sess, days)["net"].sum()) > 0)
        out["saved_n"] = len(survivors)
    return out, yst


def run_unit(k, draws=4000):
    u = UNITS[k]
    fam, root, tf, sess, grp = u
    rng = np.random.default_rng(20261005 + k)
    days = event_days(grp) if grp else None
    bst, brec, rows, judged, cnt = build_table(u, days)
    ids = [r["id"] for r in judged]
    nets = [r["net"] for r in judged]
    ts = tstats(nets, [r["trades"] for r in judged])
    res = {"unit": addr(u), "build": {"store": f"{brec['dir']}/{brec['key']}", **cnt, **ts}}
    b = res["build"]
    b["t1"] = bool(b["share_pos"] > 0.60 and b["avg"] > 0)
    b["controls"] = controls(u, bst, "build", ids, days, ts["avg"], draws, rng)
    b["t2"] = all(c.get("pass") for c in b["controls"].values())
    # first-2-seeds version of the random control (what out/v2 had)
    timed = fam.startswith("straddle")
    if not timed:
        two = c1_ctl(u, bst, "build", ids, days, ts["avg"], draws, rng, only_seeds=(1, 2))
        b["two_seed"] = {"lift": two["lift"], "p_beat": two["p_beat"]}
    # trade minimum: BUILD average trades scaled by sessions (own count: weekdays in the filter is not the engine calendar -> use trade-day counts)
    # per-year nets of the BUILD period
    yrs = {}
    for y in (2021, 2022, 2023):
        lo, hi = dt.date(y, 1, 1).toordinal(), dt.date(y, 12, 31).toordinal()
        v = []
        for c in ids:
            x = cell(bst, c, sess, days)
            m = (x["date"] >= lo) & (x["date"] <= hi)
            v.append(float(x["net"][m].sum()))
        yrs[str(y)] = float(np.mean(v))
    res["avg_by_year"] = yrs
    # 2024
    pk = year_block(u, "pick", ids, days, draws, rng)
    assert pk is not None, "no 2024 store"
    p, pst = pk
    res["pick"] = p
    res["avg_by_year"]["2024"] = p["avg"]
    # surviving set and default
    surv, default = [], None
    srecs = base_rec(u, "pick", stress=True, need=ids)
    if srecs:
        sst = load(srecs[0])
        bn = {r["id"]: r for r in judged}
        cand = [c for c in ids if bn[c]["net"] > 0 and p["nets"][c] > 0 and float(cell(sst, c, sess, days)["net"].sum()) > 0]
        bs = base_rec(u, "build", stress=True, need=cand)
        if bs:
            bss = load(bs[0])
            surv = [c for c in cand if float(cell(bss, c, sess, days)["net"].sum()) > 0]
            surv.sort(key=lambda c: (round(bn[c]["net"], 2), bn[c]["vi"], bn[c]["xi"]))
            default = surv[(len(surv) - 1) // 2] if surv else None
            res["build_stress_store"] = f"{bs[0]['dir']}/{bs[0]['key']}"
        else:
            res["build_stress_store"] = None
        res["cand_n"] = len(cand)
    res["survivors"] = surv
    res["default"] = default
    res["trades_build_plus_2024"] = b["avg_trades"] + p["avg_trades"]
    b["t3_final"] = bool(res["trades_build_plus_2024"] >= 100)
    res["member_all_seeds"] = bool(b["t1"] and b["t2"] and b["t3_final"] and p["t4"] and p["t5"] and p["t6"] and surv)
    # default per year on BUILD
    if default:
        dy = {}
        x = cell(bst, default, sess, days)
        for y in (2021, 2022, 2023):
            lo, hi = dt.date(y, 1, 1).toordinal(), dt.date(y, 12, 31).toordinal()
            dy[str(y)] = float(x["net"][(x["date"] >= lo) & (x["date"] <= hi)].sum())
        dy["2024"] = float(cell(pst, default, sess, days)["net"].sum())
        res["default_by_year"] = dy
    # 2025
    ck = year_block(u, "check", ids, days, draws, rng, default, surv)
    if ck:
        c, _ = ck
        res["check"] = c
        res["avg_by_year"]["2025"] = c["avg"]
        if default:
            res["default_by_year"]["2025"] = c["default"]["net"]
        c["verdict"] = "FAILED" if not c["avg"] > 0 else ("CONFIRMED" if c["t4"] and c["t5"] and c["t6"] else "WEAK")
    # 2026 (only if a store is on disk: the analyst's read)
    ex = year_block(u, "exam", ids, days, draws, rng, default, surv)
    if ex:
        e, _ = ex
        res["exam"] = e
        res["avg_by_year"]["2026"] = e["avg"]
        if default:
            res["default_by_year"]["2026"] = e["default"]["net"]
        e["verdict"] = "FAILED" if not e["avg"] > 0 else ("CONFIRMED" if e["t4"] and e["t5"] and e["t6"] else "WEAK")
    (HERE / "res").mkdir(exist_ok=True)
    (HERE / "res" / f"{k:02d}_{addr(u).replace('@', '_ev')}.json").write_text(json.dumps(res, indent=1, default=float))
    return res


if __name__ == "__main__":
    which = sys.argv[1]
    draws = int(sys.argv[2]) if len(sys.argv) > 2 else 4000
    for k in (range(len(UNITS)) if which == "all" else [int(which)]):
        r = run_unit(k, draws)
        b, p = r["build"], r["pick"]
        print(r["unit"], "BUILD", b["cells"], round(b["share_pos"], 3), round(b["avg"]), "t1", b["t1"], "t2", b["t2"],
              {n: (round(c.get("lift", 0)), round(c.get("p_beat", 0), 4)) for n, c in b["controls"].items()}, flush=True)
        print("   2024", round(p["avg"]), round(p["median"]), "t4", p["t4"], "t5", p["t5"], "t6", p["t6"],
              {n: round(c.get("lift", 0)) for n, c in p["controls"].items()}, "surv", len(r["survivors"]), "default", r["default"], "member", r["member_all_seeds"], flush=True)
        for per in ("check", "exam"):
            if per in r:
                c = r[per]
                print("  ", per, c["verdict"], c["positive"], "/", c["cells"], round(c["avg"]), round(c["median"]), "stress", round(c.get("stress_avg") or 0),
                      {n: (round(v.get("lift", 0), 1), round(v.get("p_beat", 0), 3)) for n, v in c["controls"].items()},
                      "default", round(c["default"]["net"]) if c.get("default") else None, "saved+", c.get("saved_profitable"), "/", c.get("saved_n"), flush=True)

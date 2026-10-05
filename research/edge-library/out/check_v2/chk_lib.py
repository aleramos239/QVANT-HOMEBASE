"""CHECKER v2 -- my own helpers. Nothing here imports out/v2/*.py or library's judging functions.
Stores are read straight from cells.npz / run.json. The engine (l2sim) is used only for the session calendar.
2024 stores are opened only through pick_store(), which logs the read; nothing dated >= 2025-01-01 is ever read."""
import csv
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

W = Path("/Users/ramoscapital/ramos-quant-homebase/research/edge-library")
OUT = W / "out" / "check_v2"
sys.path.insert(0, str(W / "engine"))
SESS = {s: i for i, s in enumerate(("eve", "asia", "london", "pre", "nyam", "mid", "pm"))}
PICK_DIRS = [W / "runs_v2", W / "runs_admit", W / "runs_admit_r1", W / "runs_deepen", W / "runs_events"]
FIELDS = ("date", "entry_ms", "dur_s", "net", "mae", "side", "sess", "reason", "risk")
SEAL = dt.date(2025, 1, 1).toordinal()
TIER1 = {"NFP", "CPI", "PPI", "RETAIL", "GDP", "PCE"}
READS = []                                        # (store dir, key) of every 2024 store this process opened


# ------------------------------------------------------------------ stores
_ST = {}


def load(key, d=None):
    d = Path(d) if d is not None else W / "runs"
    k = (key, str(d))
    if k not in _ST:
        if len(_ST) > 40:
            _ST.clear()
        meta = json.loads((d / key / "run.json").read_text())
        z = np.load(d / key / "cells.npz")
        st = {"meta": meta, "dir": d, "key": key, **{f: z[f] for f in z.files}}
        st["idx"] = {c["id"]: i for i, c in enumerate(meta["cells"])}
        if len(st["date"]):
            assert int(st["date"].max()) < SEAL, ("EXAM date inside a store", key)
        _ST[k] = st
    return _ST[k]


def exists(key, d=None):
    return ((Path(d) if d is not None else W / "runs") / key / "run.json").exists()


def build_store(key):
    st = load(key)
    assert st["meta"]["period"] == "build", key
    return st


def pick_store(key, dirs=None):
    for d in (dirs or PICK_DIRS):
        if (d / key / "run.json").exists():
            st = load(key, d)
            assert st["meta"]["period"] == "pick", key
            if (d.name, key) not in READS:
                READS.append((d.name, key))
            return st
    return None


def stress_build_store(key):
    st = load(key, W / "runs_v2")
    assert st["meta"]["period"] == "build" and st["meta"].get("stress") is True, key
    return st


def cell(st, cid, sess=None, dm=None):
    """One cell's trades, in a session (None = all), inside a day filter dm(date ordinals, sides) -> mask."""
    i = st["idx"][cid]
    a, b = int(st["off"][i]), int(st["off"][i + 1])
    x = {f: st[f][a:b] for f in FIELDS}
    m = np.ones(b - a, bool) if sess in (None, "all") else (x["sess"] == SESS[sess])
    if dm is not None:
        m = m & dm(x["date"], x["side"])
    return {f: v[m] for f, v in x.items()}


# ------------------------------------------------------------------ calendar and day filters
_CAL = {}


def cal(period, root):
    if (period, root) not in _CAL:
        import l2sim
        a, b = l2sim.period(period)
        assert b < dt.date(2025, 1, 1)
        _CAL[(period, root)] = np.array(sorted(d.toordinal() for d in l2sim.sessions(a, b, root)), np.int64)
    return _CAL[(period, root)]


_EV = {}


def ev_days(group):
    if not _EV:
        R = [r for r in csv.DictReader(open(W / "engine" / "cache" / "events.csv")) if r["date"] < "2025-01-01"]
        o = lambda r: dt.date.fromisoformat(r["date"]).toordinal()  # noqa: E731
        _EV["A"] = np.array(sorted({o(r) for r in R if r["time_et"] == "08:30"}), np.int64)
        _EV["B"] = np.array(sorted({o(r) for r in R if r["time_et"] == "08:30" and r["type"] in TIER1}), np.int64)
        _EV["C"] = np.array(sorted({o(r) for r in R if r["time_et"] == "10:00"}), np.int64)
    return _EV[group]


def day_filter(u):
    """-> None (no filter) or f(date ordinals, sides) -> bool mask."""
    if u.get("group"):
        g = ev_days(u["group"])
        return lambda date, side=None: np.isin(np.asarray(date, np.int64), g)
    if u.get("side"):
        sys.path.insert(0, str(W / "out" / "deepen"))
        import labels as L                           # day labels of stage 2a (data, not a judging function)
        s, r = u["side"], u["root"]
        return lambda date, side=None: L.side_mask(s, r, np.asarray(date), np.zeros(len(date)) if side is None else side)
    return None


def scope_days(u, period):
    c = cal(period, u["root"])
    f = day_filter(u)
    return c if f is None else c[f(c)]


# ------------------------------------------------------------------ the unit's table
def sig(x):
    if not len(x["net"]):
        return "empty"
    h = hashlib.sha1()
    h.update(np.ascontiguousarray(x["entry_ms"], np.int64).tobytes())
    h.update(np.ascontiguousarray(x["dur_s"], np.int64).tobytes())
    h.update(np.ascontiguousarray(x["side"], np.int64).tobytes())
    h.update(np.round(np.asarray(x["net"], np.float64) * 100).astype(np.int64).tobytes())
    return h.hexdigest()


def build_rows(st, u):
    """All cells of the unit (its mirror label) on the BUILD store: id, vi, xi, dead, info; net / trades / sig in the unit's
    session and day filter. dead = the cell's variant (vi) has no trade in the session in any exit cell (before the day filter)."""
    sess, dm = u["sess"], day_filter(u)
    cells = st["meta"]["cells"]
    axis = st["meta"].get("mirror") or None
    n_sess = {}
    for c in cells:
        n_sess[c["vi"]] = n_sess.get(c["vi"], 0) + len(cell(st, c["id"], sess)["net"])
    rows = []
    for c in cells:
        if axis:
            if f"{axis}={c['variant'][axis]}" != u["label"]:
                continue
        else:
            assert not u["label"], (u["uid"], "label without a mirror axis")
        x = cell(st, c["id"], sess, dm)
        rows.append({"id": c["id"], "vi": c["vi"], "xi": c["xi"], "info": bool(c.get("info")), "dead": n_sess[c["vi"]] == 0,
                     "net": float(x["net"].sum()), "trades": int(len(x["net"])), "sig": sig(x)})
    return rows


def rows_on(st, u, ref):
    """The same cells on another store (2024, stress): BUILD flags, this store's net / trades / sig."""
    dm = day_filter(u)
    out = []
    for r in ref:
        if r["id"] not in st["idx"]:
            assert r["dead"] or r["info"], (r["id"], st["key"])
            continue
        x = cell(st, r["id"], u["sess"], dm)
        out.append({**r, "net": float(x["net"].sum()), "trades": int(len(x["net"])), "sig": sig(x)})
    return out


def judged(rows):
    """Not info, not dead, identical trade lists once (first in (vi, xi) order)."""
    live = sorted([r for r in rows if not r["info"] and not r["dead"]], key=lambda r: (r["vi"], r["xi"]))
    seen, keep = set(), []
    for r in live:
        if r["sig"] in seen:
            continue
        seen.add(r["sig"])
        keep.append(r)
    return keep


def tstats(rows):
    j = judged(rows)
    if not j:
        return {"cells": 0, "ids": []}
    net = np.array([r["net"] for r in j])
    tr = np.array([r["trades"] for r in j])
    return {"cells": len(j), "ids": [r["id"] for r in j], "share": float((net > 0).mean()), "avg": float(net.mean()),
            "median": float(np.median(net)), "avg_trades": float(tr.mean()), "sum_net": float(net.sum()), "sum_trades": int(tr.sum())}


# ------------------------------------------------------------------ control: random entries (coupled table draws)
def _pool_matrix(pu, sess, xid, seeds, days, R):
    """nets[D, len(seeds) * R] of the pool's exit cell `xid` (NaN = no such slot); slot = (seed, n-th entry of that day)."""
    M = np.full((len(days), len(seeds) * R), np.nan)
    for si, sd in enumerate(seeds):
        cid = f"s{sd}_{xid}"
        if cid not in pu["idx"]:
            return None
        x = cell(pu, cid, sess)
        o = np.lexsort((x["entry_ms"], x["date"]))
        d, n = x["date"][o].astype(np.int64), x["net"][o].astype(np.float64)
        di = np.searchsorted(days, d)
        assert (days[di] == d).all()
        first = np.r_[True, d[1:] != d[:-1]] if len(d) else np.zeros(0, bool)
        start = np.maximum.accumulate(np.where(first, np.arange(len(d)), 0)) if len(d) else np.zeros(0, int)
        rank = np.arange(len(d)) - start
        assert not len(rank) or rank.max() < R
        M[di, si * R + rank] = n
    return M


def _max_rank(pu, sess, xids, seeds):
    r = 1
    for xid in xids:
        for sd in seeds:
            cid = f"s{sd}_{xid}"
            if cid in pu["idx"]:
                d = cell(pu, cid, sess)["date"]
                if len(d):
                    r = max(r, int(np.unique(d, return_counts=True)[1].max()))
    return r


def c1_table(st, u, ids, pu, seed, seeds=(1, 2), K=200, coupled=True):
    """K random TABLES. Coupled: one random priority per (replicate, day, slot), shared by every variant; a variant with k trades
    on a day takes the k lowest-priority slots that exist in its exit cell's pool that day. Shortfall: the nearest dates."""
    rng = np.random.default_rng(seed)
    sess, dm = u["sess"], day_filter(u)
    xids = sorted({c.rsplit("_", 1)[-1] for c in ids})
    pool_days = [cell(pu, f"s{sd}_{x}", sess)["date"] for x in xids for sd in seeds if f"s{sd}_{x}" in pu["idx"]]
    mem = {c: cell(st, c, sess, dm)["date"].astype(np.int64) for c in ids}
    days = np.unique(np.concatenate([d.astype(np.int64) for d in pool_days] + list(mem.values()) + [np.zeros(0, np.int64)]))
    R = _max_rank(pu, sess, xids, seeds)
    S = len(seeds) * R
    D = len(days)
    P = rng.random((K, D, S), dtype=np.float32)
    P2 = rng.random((K, D, S), dtype=np.float32)
    cum, Ms = {}, {}
    for xid in xids:
        M = _pool_matrix(pu, sess, xid, seeds, days, R)
        if M is None:
            return {"ok": False, "why": f"no pool cell for exit {xid}"}
        Ms[xid] = M
        if coupled:
            valid = ~np.isnan(M)
            Pm = np.where(valid[None], P, np.float32(9.0))
            o = np.argsort(Pm, axis=2)
            ns = np.take_along_axis(np.broadcast_to(np.nan_to_num(M)[None], Pm.shape), o, 2)
            cum[xid] = np.concatenate([np.zeros((K, D, 1)), np.cumsum(ns, axis=2)], axis=2)
    draws = np.zeros(K)
    fb = short = n = 0
    for c in ids:
        xid = c.rsplit("_", 1)[-1]
        M = Ms[xid]
        valid = ~np.isnan(M)
        n_own = valid.sum(axis=1)
        ud, kk = np.unique(mem[c], return_counts=True)
        n += len(mem[c])
        if not len(ud):
            continue
        di = np.searchsorted(days, ud)
        take = np.minimum(kk, n_own[di])
        if coupled:
            draws += cum[xid][:, di, take].sum(axis=1)
        else:
            Pi = np.where(valid[di][None], rng.random((K, len(di), S), dtype=np.float32), np.float32(9.0))
            o = np.argsort(Pi, axis=2)
            ns = np.take_along_axis(np.broadcast_to(np.nan_to_num(M[di])[None], Pi.shape), o, 2)
            cs = np.concatenate([np.zeros((K, len(di), 1)), np.cumsum(ns, axis=2)], axis=2)
            draws += cs[:, np.arange(len(di)), take].sum(axis=1)
        need = kk - take
        for j in np.flatnonzero(need > 0):
            d, nd = int(ud[j]), int(need[j])
            cd, cs_ = np.nonzero(valid)
            keep = days[cd] != d
            cd, cs_ = cd[keep], cs_[keep]
            if not len(cd):
                short += nd
                continue
            dist = np.abs(days[cd] - d)
            cut = np.sort(dist)[min(nd, len(dist)) - 1]
            use = dist <= cut
            cd, cs_ = cd[use], cs_[use]
            got = min(nd, len(cd))
            fb += got
            short += nd - got
            nets = M[cd, cs_]
            if got == len(cd):
                draws += nets.sum()
            else:
                pr = P2[:, cd, cs_] if coupled else rng.random((K, len(cd)), dtype=np.float32)
                od = np.argpartition(pr, got - 1, axis=1)[:, :got]
                draws += nets[od].sum(axis=1)
    draws /= max(1, len(ids))
    return {"ok": True, "draws": draws, "mean": float(draws.mean()), "sd": float(draws.std(ddof=1)), "real": len(seeds),
            "fallback_share": fb / n if n else 0.0, "short": int(short), "slots_per_day": float(np.mean([(~np.isnan(m)).sum(1).mean() for m in Ms.values()]))}


# ------------------------------------------------------------------ control: two seeds mixed by day (random minute / shuffled book)
def day_avg(cells, days):
    A = np.zeros(len(days))
    for x in cells:
        if len(x["net"]):
            i = np.searchsorted(days, x["date"])
            assert (days[i] == x["date"]).all()
            np.add.at(A, i, x["net"])
    return A / max(1, len(cells))


def mix(A1, A2, seed, K=2000):
    rng = np.random.default_rng(seed)
    pick = rng.random((K, len(A1))) < 0.5
    draws = np.where(pick, A1[None], A2[None]).sum(axis=1)
    raw = [float(A1.sum()), float(A2.sum())]
    return {"ok": True, "draws": draws, "mean": float(np.mean(raw)), "raw": raw, "sd": float(draws.std(ddof=1)), "real": 2,
            "sd_exact": float(np.sqrt(((A1 - A2) ** 2).sum()) / 2)}


def shift_table(su, u, ids, period, seed):
    dm = day_filter(u)
    cs = {}
    for sd in (1, 2):
        if any(f"s{sd}_{c}" not in su["idx"] for c in ids):
            return {"ok": False, "why": "no control cell"}
        cs[sd] = [cell(su, f"s{sd}_{c}", None, dm) for c in ids]
    days = np.unique(np.concatenate([scope_days(u, period)] + [x["date"].astype(np.int64) for sd in (1, 2) for x in cs[sd]]))
    return mix(day_avg(cs[1], days), day_avg(cs[2], days), seed)


def c2_table(s1, s2, u, ids, period, seed):
    dm = day_filter(u)
    if any(c not in s["idx"] for s in (s1, s2) for c in ids):
        return {"ok": False, "why": "shuffled-book store lacks cells"}
    cs = [[cell(s, c, u["sess"], dm) for c in ids] for s in (s1, s2)]
    days = np.unique(np.concatenate([scope_days(u, period)] + [x["date"].astype(np.int64) for c in cs for x in c]))
    return mix(day_avg(cs[0], days), day_avg(cs[1], days), seed)


def verdict(avg, ctl, need_p):
    if not ctl.get("ok"):
        return {"pass": False, "why": ctl.get("why")}
    lift = avg - ctl["mean"]
    p = float((avg > ctl["draws"]).mean())
    out = {"pass": bool(lift > 0 and (p >= 0.95 or not need_p) and not ctl.get("short")), "lift": round(lift, 2), "p_beat": round(p, 4),
           "ctl_mean": round(ctl["mean"], 2), "ctl_sd": round(ctl["sd"], 2), "real": ctl["real"], "z": round(lift / ctl["sd"], 2) if ctl["sd"] > 0 else None}
    for k in ("fallback_share", "short", "raw", "slots_per_day"):
        if k in ctl:
            out[k] = ctl[k] if not isinstance(ctl[k], float) else round(ctl[k], 4)
    return out


# ------------------------------------------------------------------ controls: Level 2 base, day filter
def per_trade(st, u, ids, filtered=True):
    dm = day_filter(u) if filtered else None
    net = n = 0.0
    for c in ids:
        x = cell(st, c, u["sess"], dm)
        net += float(x["net"].sum())
        n += len(x["net"])
    return (net / n if n else 0.0), net, int(n)


def base_test(st, bst, u, ids):
    if any(c not in bst["idx"] for c in ids):
        return {"pass": False, "why": "base store lacks cells"}
    a = per_trade(st, u, ids)[0]
    b = per_trade(bst, u, ids)[0]
    return {"pass": bool(a > b), "per_trade": round(a, 2), "base_per_trade": round(b, 2)}


def days_test(st, u, ids, seed, need_p, n_sub=4000):
    d = np.concatenate([cell(st, c, u["sess"])["date"] for c in ids]).astype(np.int64)
    n = np.concatenate([cell(st, c, u["sess"])["net"] for c in ids]).astype(np.float64)
    if not len(d):
        return {"pass": False, "why": "no trade"}
    days, inv = np.unique(d, return_inverse=True)
    N = np.bincount(inv, n, len(days))
    T = np.bincount(inv, None, len(days)).astype(float)
    ins = day_filter(u)(days)
    k, nd = int(ins.sum()), len(days)
    if k == 0 or T[ins].sum() == 0:
        return {"pass": False, "why": "no trade inside the filter"}
    obs, unf = float(N[ins].sum() / T[ins].sum()), float(N.sum() / T.sum())
    out = {"per_trade": round(obs, 2), "unfiltered_per_trade": round(unf, 2), "days_in": k, "days_all": nd, "real": n_sub}
    if k >= nd:
        return {**out, "pass": False, "why": "the filter keeps every day"}
    rng = np.random.default_rng(seed)
    vals = np.zeros(n_sub)
    for a in range(0, n_sub, 500):
        pk = np.argsort(rng.random((500, nd)), axis=1)[:, :k]
        vals[a:a + 500] = N[pk].sum(axis=1) / np.maximum(1.0, T[pk].sum(axis=1))
    p = float((obs > vals).mean())
    out.update(p_beat=round(p, 4), **{"pass": bool(obs > unf and (p >= 0.95 or not need_p))})
    return out


# ------------------------------------------------------------------ units (the analyst's list of names; nothing judged is taken from it)
def _b(v):
    return str(v).strip().lower() in ("true", "1")


def units():
    base = {r["uid"]: (r["base"] or None) for r in csv.DictReader(open(W / "out" / "admit" / "build_units.csv"))}
    out = []
    for r in csv.DictReader(open(W / "out" / "v2" / "build_units.csv")):
        out.append({"uid": r["uid"], "src": r["src"], "key": r["key"], "family": r["family"], "root": r["root"], "tf": r["tf"],
                    "sess": r["sess"], "label": r["label"], "group": r["group"] or None, "side": r["side"] or None,
                    "timed": _b(r["timed"]), "l2": _b(r["l2"]), "stage_d": _b(r["stage_d"]), "base": base.get(r["uid"]) if r["src"] == "s1" else None,
                    "controls": r["controls"].split("+"), "A": r})
    return out

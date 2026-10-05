"""ADMISSION v2 helpers (EDGE_SPEC "USER DIRECTION — CORRECTION AND ADMISSION v2", parts A-C). METHOD, FIXED BEFORE ANY v2 NUMBER:
A unit's TABLE = its judged variants (library.judged_rows: dead cells and author cells out, identical trade lists once).
BUILD (1) share of judged variants with net > 0 >= 60 % (library convention; exactly 60 % is flagged) AND the average variant's net > 0.
BUILD (3) trade minimum on the AVERAGE variant's trade count: mean BUILD trades scaled to BUILD + 2024 at the same trades-per-day
      rate (x (1 + days_2024 / days_BUILD), the unit's own day scope) >= 100; re-checked on the real BUILD + 2024 count once open.
BUILD (2) REAL EDGE, every control on disk that applies must pass (lift > 0 AND the table average beats >= 95 % of the replicates):
  c1     bar-based units. Pool = runs/c1-<root>-tf<tf> (2 seeds, same exit cell, same session). K = 200 replicates. ONE replicate =
         one random table: for every (date, session) with k trades of a variant, k pool trades of that date + session without
         replacement, shortfall filled from the nearest dates (the matching rule of library.c1_draws), and the SAME draw is used
         by every variant of the table: a pool trade is the slot (date, seed, n-th entry of that seed that day), each slot gets one
         random priority per replicate, a variant takes its k lowest-priority slots. Replicate value = mean over the judged variants.
  shift  time-fired units. The on-disk random-minute (or random-direction) store has 2 seeds = 2 real replicates (THIN). K = 200
         replicates = day-mixes of the two seeds (each day takes seed 1 or seed 2 for the whole table). Lift = table average minus
         the mean of the two seeds' table averages.
  c2     Level 2 units: the 2 shuffled-book stores, K = 200 day-mixes as for shift (THIN). No store on disk = fail.
  base   Level 2 filter / exit variants: the table's net per trade must beat the same strategy WITHOUT the option (same variants).
  days   day-filter units: the filtered table's net per trade (sum of nets / sum of trades over the judged variants) must beat
         the unfiltered table's and beat >= 95 % of 4,000 random same-size subsets of the table's trading days.
2024 ON ITS OWN: (4) mean and median of the judged variants' 2024 net > 0; (5) lift > 0 against every control used on BUILD;
(6) mean net > 0 under 2 ticks + 250 ms (+ oco_cancel_ms = 100 for stores with both_sides_declared).
SAVED: variants with net > 0 on BUILD, 2024, BUILD stress, 2024 stress. DEFAULT = the middle survivor by BUILD net: survivors
sorted by (BUILD net, vi, xi) ascending, index (n - 1) // 2 (an even count takes the LOWER of the two middle ones).
Held <= 5 s: the stores keep whole seconds (floor), so "fast" = dur_s < 5 for store tables; exact ms for the default's trade rows.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
import zlib
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[2]
for p in (str(W), str(W / "engine"), str(W / "out" / "events"), str(W / "out" / "deepen")):
    if p not in sys.path:
        sys.path.insert(0, p)
import library as LB  # noqa: E402

OUT = W / "out" / "v2"
RV = W / "runs_v2"
K = 200
SUBSETS = 4000
P_NEED = 0.95
SHARE = 0.60
FAST_S = 5
CAPS = {"runs": 2000, "cells": 80000, "wfs": 40}          # v2 part D: candidate cap 50,000 -> 80,000
PICK_DIRS = [RV, W / "runs_admit", W / "runs_admit_r1", W / "runs_deepen", W / "runs_events"]
U64 = np.uint64
MAXU = np.iinfo(np.uint64).max


# ---------------------------------------------------------------- units

def _b(v) -> bool:
    return str(v).strip().lower() in ("true", "1")


def units() -> list:
    """Every stored unit: stage 1 (1,623), round 1 (258), event units (15), stage-4 entry units (18), + the two stage-2a
    day-filter sides that were opened on 2024."""
    import families as F
    out = []
    for r in csv.DictReader((W / "out" / "admit" / "build_units.csv").open()):
        sd = r["kind"] == "stage_d"
        timed, l2 = _b(r["timed"]), _b(r["l2"])
        ctl = (["shift"] if timed else ["c1"]) + (["c2"] if l2 else []) + (["base"] if sd else [])
        out.append({"uid": r["uid"], "src": "s1", "key": r["key"], "family": r["family"], "base": r["base"] or None, "root": r["root"],
                    "tf": str(r["tf"]), "sess": r["sess"], "label": r["label"] or "", "timed": timed, "l2": l2, "stage_d": sd,
                    "weak": _b(r["weak"]), "penalty": _b(r["penalty"]), "group": None, "side": None, "controls": ctl})
    for r in csv.DictReader((W / "out" / "admit_r1" / "build_units.csv").open()):
        timed = _b(r["timed"])
        out.append({"uid": r["uid"], "src": "r1", "key": r["key"], "family": r["family"], "base": None, "root": r["root"],
                    "tf": str(r["tf"]), "sess": r["sess"], "label": r["label"] or "", "timed": timed, "l2": False, "stage_d": False,
                    "weak": _b(r["weak"]), "penalty": bool(F.penalty_for(r["family"], r["sess"])), "group": None, "side": None,
                    "controls": ["shift"] if timed else ["c1"]})
    for src, f in (("ev", "events"), ("en", "entries")):
        for r in csv.DictReader((W / "out" / f / "build_units.csv").open()):
            key = f"{r['family']}-{r['root']}-tf30"
            out.append({"uid": r["uid"], "src": src, "key": key, "family": r["family"], "base": None, "root": r["root"], "tf": "30",
                        "sess": r["sess"], "label": "", "timed": True, "l2": False, "stage_d": False,
                        "weak": r["family"] in F.WEAK_FAMILIES, "penalty": False, "group": r["group"], "side": None,
                        "controls": ["days", "shift"]})
    out.append({"uid": "donchian-NQ-tf5|nyam||vol_lo", "src": "2a", "key": "donchian-NQ-tf5", "family": "donchian", "base": None,
                "root": "NQ", "tf": "5", "sess": "nyam", "label": "", "timed": False, "l2": False, "stage_d": False, "weak": False,
                "penalty": False, "group": None, "side": "vol_lo", "controls": ["days", "c1"]})
    out.append({"uid": "straddle_t_0830-NQ-tf30|pre||news_only", "src": "2a", "key": "straddle_t_0830-NQ-tf30",
                "family": "straddle_t_0830", "base": None, "root": "NQ", "tf": "30", "sess": "pre", "label": "", "timed": True,
                "l2": False, "stage_d": False, "weak": False, "penalty": False, "group": None, "side": "news_only",
                "controls": ["days", "shift"]})
    assert len({u["uid"] for u in out}) == len(out)
    return out


def member_name(u: dict) -> str:
    n = f"{u['family']}_{u['root']}_tf{u['tf']}_{u['sess']}"
    if u["label"]:
        n += "_" + u["label"].replace("=", "")
    if u["group"]:
        n += f"_ev{u['group']}"
    if u["side"]:
        n += f"_{u['side']}"
    return n


# ---------------------------------------------------------------- day scope

def day_mask(u: dict, date, side=None) -> np.ndarray:
    """Trades (by trade-date ordinal) inside the unit's day filter (all True for a unit without one)."""
    date = np.asarray(date)
    if u.get("group"):
        import ev as E
        return E.mask(u["group"], date)
    if u.get("side"):
        import labels as L
        return L.side_mask(u["side"], u["root"], date, np.zeros(len(date)) if side is None else side)
    return np.ones(len(date), bool)


def scope_days(u: dict, period: str) -> np.ndarray:
    """Ordinals of the period's sessions inside the unit's day filter."""
    cal = LB._ordinals(LB.calendar(period, u["root"]))
    return cal[day_mask(u, cal)]


# ---------------------------------------------------------------- stores, tables

_STORE: dict = {}


def store(key: str, runs_dir=None, period: str | None = None) -> dict:
    k = (key, str(runs_dir))
    if k not in _STORE:
        if len(_STORE) > 24:
            _STORE.clear()
        u = LB.load_unit(key, runs_dir)
        u["_idx"] = {c["id"]: i for i, c in enumerate(u["meta"]["cells"])}
        _STORE[k] = u
    u = _STORE[k]
    if period is not None:
        assert u["meta"].get("period") == period, (key, u["meta"].get("period"))
    return u


def has(key: str, runs_dir=None) -> bool:
    return ((Path(runs_dir) if runs_dir is not None else LB.RUNS) / key / "run.json").exists()


def find_pick(key: str):
    """The directory that holds a 2024 store `key`, or None (v2's own first, then the earlier stages')."""
    for d in PICK_DIRS:
        if (d / key / "run.json").exists():
            return d
    return None


def cellx(st: dict, cid: str, sess: str | None, u: dict | None = None) -> dict:
    """One cell's trades in a session (None = all sessions) and inside the unit's day filter."""
    i = st["_idx"][cid]
    a, b = int(st["off"][i]), int(st["off"][i + 1])
    x = {k: st[k][a:b] for k in LB.FIELDS}
    m = np.ones(b - a, bool) if sess is None else x["sess"] == LB.SESS_CODE[sess]
    if u is not None and (u.get("group") or u.get("side")):
        m = m & day_mask(u, x["date"], x["side"])
    return {k: v[m] for k, v in x.items()}


def base_rows(st: dict, u: dict) -> list:
    return LB.plateau_units(st, u["sess"])[u["label"]]


def table(st: dict, u: dict, dead_from: dict | None = None, filtered: bool = True) -> list:
    """The unit's table on a store: rows of library.session_table for the unit's session + mirror label; with a day filter
    (and filtered=True) net / trades / sig are recomputed on the kept trades. dead_from = {cell id: dead} lays the BUILD dead
    flags over a 2024 table (as every earlier stage did)."""
    rows = [dict(r) for r in base_rows(st, u)]
    if filtered and (u.get("group") or u.get("side")):
        for r in rows:
            x = cellx(st, r["id"], u["sess"], u)
            s = LB.stats(x["net"])
            i = st["_idx"][r["id"]]
            a, b = int(st["off"][i]), int(st["off"][i + 1])
            full = {k: st[k][a:b] for k in LB.FIELDS}
            m = (full["sess"] == LB.SESS_CODE[u["sess"]]) & day_mask(u, full["date"], full["side"])
            r.update(net=s["net"], trades=s["trades"], t=s["t"], sig=LB.trade_sig(full, m))
    if dead_from is not None:
        for r in rows:
            r["dead"] = bool(dead_from.get(r["id"], r.get("dead", False)))
    return rows


def table_stats(rows: list) -> dict:
    j, n_dead, n_dup = LB.judged_rows(rows)
    if not j:
        return {"cells": 0, "ids": [], "share_pos": None, "avg_net": None, "median_net": None, "avg_trades": 0.0, "dead": n_dead, "dup": n_dup}
    net = np.array([float(r["net"]) for r in j])
    tr = np.array([int(r["trades"]) for r in j])
    return {"cells": len(j), "ids": [r["id"] for r in j], "share_pos": float((net > 0).mean()), "avg_net": float(net.mean()),
            "median_net": float(np.median(net)), "avg_trades": float(tr.mean()), "sum_net": float(net.sum()), "sum_trades": int(tr.sum()),
            "positive": int((net > 0).sum()), "dead": n_dead, "dup": n_dup,
            "v60": bool(net.mean() > 0 and (net > 0).mean() >= 0.6 - 1e-12), "v70": bool(net.mean() > 0 and (net > 0).mean() >= 0.7 - 1e-12),
            "v80": bool(net.mean() > 0 and (net > 0).mean() >= 0.8 - 1e-12)}


def exit_id(cid: str) -> str:
    return cid.rsplit("_", 1)[-1]


def seed_of(name: str, what: str) -> int:
    return zlib.crc32(f"v2|{name}|{what}".encode()) % (2 ** 31)


# ---------------------------------------------------------------- control c1: coupled table draws

def _mix(x):
    x = (x ^ (x >> U64(30))) * U64(0xbf58476d1ce4e5b9)
    x = (x ^ (x >> U64(27))) * U64(0x94d049bb133111eb)
    return x ^ (x >> U64(31))


def _prio(codes: np.ndarray, seed: int, salt=0, k: int = K) -> np.ndarray:
    """(k, *codes.shape) random priorities: one per (replicate, pool slot); the same slot gets the same priority in every
    variant of the table (that is the coupling)."""
    with np.errstate(over="ignore"):
        base = _mix(codes.astype(U64) + U64(seed) * U64(0x9e3779b97f4a7c15) + np.asarray(salt, U64) * U64(0xd1b54a32d192ed03))
        j = (np.arange(k, dtype=U64) + U64(1)).reshape((-1,) + (1,) * codes.ndim)
        return _mix(base[None, ...] + j * U64(0x2545f4914f6cdd1d))


def pool_arrays(pu: dict, sess: str, xid: str, seeds=(1, 2), u: dict | None = None):
    """The pool of one exit cell in one session, sorted by date: (date, net, slot code, cumulative net) or None."""
    D, N, C = [], [], []
    for sd in seeds:
        cid = f"s{sd}_{xid}"
        if cid not in pu["_idx"]:
            return None
        x = cellx(pu, cid, sess)
        o = np.lexsort((x["entry_ms"], x["date"]))
        d, n = x["date"][o].astype(np.int64), x["net"][o].astype(np.float64)
        if len(d):
            first = np.r_[True, d[1:] != d[:-1]]
            start = np.maximum.accumulate(np.where(first, np.arange(len(d)), 0))
            rank = np.arange(len(d)) - start
            assert rank.max() < 2048
        else:
            rank = np.zeros(0, np.int64)
        D.append(d)
        N.append(n)
        C.append(d * 4096 + (sd - 1) * 2048 + rank)
    d, n, c = np.concatenate(D), np.concatenate(N), np.concatenate(C)
    o = np.argsort(d, kind="stable")
    d, n, c = d[o], n[o], c[o].astype(U64)
    return d, n, c, np.r_[0.0, np.cumsum(n)]


def c1_cell(md: np.ndarray, pool, seed: int, k: int = K) -> tuple:
    """K coupled draws for ONE variant: -> (nets (K,), fallback trades, unmatched trades)."""
    pd_, pn, pc, cs = pool
    out = np.zeros(k)
    if not len(md):
        return out, 0, 0
    ud, kk = np.unique(np.asarray(md, np.int64), return_counts=True)
    lo, hi = np.searchsorted(pd_, ud, "left"), np.searchsorted(pd_, ud, "right")
    n_own = hi - lo
    full = n_own <= kk
    out += float((cs[hi[full]] - cs[lo[full]]).sum())
    sel = np.flatnonzero(n_own > kk)
    if len(sel):
        order = sel[np.argsort(n_own[sel], kind="stable")]
        a = 0
        while a < len(order):
            b = a + 1
            while b < len(order) and k * (b - a + 1) * int(n_own[order[b]]) <= 3_000_000:
                b += 1
            g = order[a:b]
            a = b
            M = int(n_own[g].max())
            idx = lo[g][:, None] + np.arange(M)[None, :]
            valid = np.arange(M)[None, :] < n_own[g][:, None]
            idx = np.where(valid, idx, 0)
            P = _prio(pc[idx], seed, 0, k)
            P[:, ~valid] = MAXU
            nets = pn[idx]
            kg = kk[g]
            if int(kg.max()) == 1:
                am = P.argmin(axis=-1)
                out += np.take_along_axis(np.broadcast_to(nets, P.shape), am[..., None], -1)[..., 0].sum(axis=1)
            else:
                km = int(kg.max())
                od = np.argpartition(P, km - 1, axis=-1)[..., :km] if km < M else np.argsort(P, axis=-1)
                ps = np.take_along_axis(P, od, -1)
                o2 = np.argsort(ps, axis=-1)
                od = np.take_along_axis(od, o2, -1)
                ns = np.take_along_axis(np.broadcast_to(nets, P.shape), od, -1)
                keep = np.arange(od.shape[-1])[None, None, :] < kg[None, :, None]
                out += (ns * keep).sum(axis=(1, 2))
    fb = short = 0
    need_g = np.flatnonzero(n_own < kk)
    if len(need_g):
        upd, first, cnt = np.unique(pd_, return_index=True, return_counts=True)
        for g in need_g:
            d, need = int(ud[g]), int(kk[g] - n_own[g])
            ok = upd != d
            dist = np.abs(upd[ok] - d)
            if not len(dist):
                short += need
                continue
            o = np.argsort(dist, kind="stable")
            cum = np.cumsum(cnt[ok][o])
            j = int(np.searchsorted(cum, need, "left"))
            cut = dist[o][min(j, len(o) - 1)]
            use = np.flatnonzero(dist <= cut)
            ei = np.concatenate([np.arange(first[ok][t], first[ok][t] + cnt[ok][t]) for t in use])
            got = min(need, len(ei))
            fb += got
            short += need - got
            if got == len(ei):
                out += float(pn[ei].sum())
            else:
                P = _prio(pc[ei], seed, d % 100003 + 7, k)
                od = np.argpartition(P, got - 1, axis=-1)[:, :got]
                out += pn[ei][od].sum(axis=1)
    return out, fb, short


def c1_table(st: dict, u: dict, ids: list, pu: dict, seed: int, seeds=(1, 2)) -> dict:
    """Control c1 at TABLE level: K coupled replicates of the table average."""
    pools: dict = {}
    draws = np.zeros(K)
    fb = short = n = 0
    for cid in ids:
        xid = exit_id(cid)
        if xid not in pools:
            pools[xid] = pool_arrays(pu, u["sess"], xid, seeds)
        if pools[xid] is None:
            return {"ok": False, "why": f"no pool cell for exit {xid}"}
        md = cellx(st, cid, u["sess"], u)["date"]
        d, f, s = c1_cell(md, pools[xid], seed)
        draws += d
        fb += f
        short += s
        n += len(md)
    draws /= max(1, len(ids))
    return {"ok": True, "draws": draws, "mean": float(draws.mean()), "sd": float(draws.std(ddof=1)), "p95": float(np.percentile(draws, 95)),
            "fallback_share": fb / n if n else 0.0, "short": int(short), "replicates": K, "real_replicates": len(seeds)}


# ---------------------------------------------------------------- controls shift / c2: day-mixes of the two seeds

def seed_day_avg(cells: list, days: np.ndarray) -> np.ndarray:
    """Per-day table average of a list of cells (packed arrays): sum of the cells' nets that day / number of cells."""
    A = np.zeros(len(days))
    for x in cells:
        if len(x["net"]):
            i = np.searchsorted(days, x["date"])
            ok = (i < len(days)) & (days[np.minimum(i, len(days) - 1)] == x["date"])
            np.add.at(A, i[ok], x["net"][ok])
    return A / max(1, len(cells))


def mix_draws(A1: np.ndarray, A2: np.ndarray, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, 2, size=(K, len(A1))).astype(bool)
    draws = np.where(pick, A1[None, :], A2[None, :]).sum(axis=1)
    raw = [float(A1.sum()), float(A2.sum())]
    return {"ok": True, "draws": draws, "mean": float(np.mean(raw)), "raw": raw, "sd": float(draws.std(ddof=1)),
            "p95": float(np.percentile(draws, 95)), "replicates": K, "real_replicates": 2}


def all_days(u: dict, period: str, extra=()) -> np.ndarray:
    cal = LB._ordinals(LB.calendar(period, u["root"]))
    ex = [np.asarray(e, np.int64) for e in extra if len(e)]
    return np.unique(np.concatenate([cal] + ex)) if ex else cal


def shift_table(su: dict, u: dict, ids: list, period: str, seed: int) -> dict:
    """Control shift: the same table at random minutes / with a random direction (2 seeds), on the unit's days, all sessions."""
    cells = {sd: [] for sd in (1, 2)}
    for sd in (1, 2):
        for cid in ids:
            k = f"s{sd}_{cid}"
            if k not in su["_idx"]:
                return {"ok": False, "why": f"no control cell {k}"}
            cells[sd].append(cellx(su, k, None, u))
    days = all_days(u, period, [x["date"] for sd in (1, 2) for x in cells[sd]])
    return mix_draws(seed_day_avg(cells[1], days), seed_day_avg(cells[2], days), seed)


def c2_table(s1: dict, s2: dict, u: dict, ids: list, period: str, seed: int) -> dict:
    """Control c2: the same table with a shuffled book (2 seeds), same session."""
    cells = []
    for s in (s1, s2):
        if any(cid not in s["_idx"] for cid in ids):
            return {"ok": False, "why": "shuffled-book store lacks cells"}
        cells.append([cellx(s, cid, u["sess"], u) for cid in ids])
    days = all_days(u, period, [x["date"] for c in cells for x in c])
    return mix_draws(seed_day_avg(cells[0], days), seed_day_avg(cells[1], days), seed)


def verdict(avg: float, ctl: dict, need_p: bool) -> dict:
    """lift and share of replicates beaten; pass = lift > 0 (and p >= 95 % on BUILD; and no unmatched trade for c1)."""
    if not ctl.get("ok"):
        return {"pass": False, "why": ctl.get("why", "no control")}
    lift = avg - ctl["mean"]
    p = float((avg > ctl["draws"]).mean())
    ok = lift > 0 and (p >= P_NEED or not need_p) and not ctl.get("short")
    out = {"pass": bool(ok), "lift": round(lift, 2), "p_beat": round(p, 4), "ctl_mean": round(ctl["mean"], 2), "ctl_p95": round(ctl["p95"], 2),
           "ctl_sd": round(ctl["sd"], 2), "replicates": ctl["replicates"], "real_replicates": ctl["real_replicates"],
           "thin": ctl["real_replicates"] < 20}
    for k in ("fallback_share", "short", "raw"):
        if k in ctl:
            out[k] = ctl[k] if k != "fallback_share" else round(ctl[k], 4)
    return out


# ---------------------------------------------------------------- control base (Level 2 option) and days (day filter)

def per_trade(st: dict, u: dict, ids: list, filtered: bool = True) -> tuple:
    net = n = 0.0
    for cid in ids:
        x = cellx(st, cid, u["sess"], u if filtered else None)
        net += float(x["net"].sum())
        n += len(x["net"])
    return (net / n if n else 0.0), net, int(n)


def base_test(st: dict, bst: dict, u: dict, ids: list) -> dict:
    if any(c not in bst["_idx"] for c in ids):
        return {"pass": False, "why": "base store lacks cells"}
    a, an, at = per_trade(st, u, ids)
    b, bn, bt = per_trade(bst, u, ids)
    return {"pass": bool(a > b), "per_trade": round(a, 2), "base_per_trade": round(b, 2), "lift_per_trade": round(a - b, 2),
            "avg_net": round(an / len(ids), 2), "base_avg_net": round(bn / len(ids), 2), "trades_kept_share": round(at / bt, 4) if bt else None}


def days_test(st: dict, u: dict, ids: list, seed: int, need_p: bool) -> dict:
    """Day filter: net per trade of the filtered table vs the unfiltered table and vs SUBSETS random same-size subsets of the
    days the unfiltered table traded."""
    dates, nets = [], []
    for cid in ids:
        x = cellx(st, cid, u["sess"], None)
        dates.append(x["date"])
        nets.append(x["net"])
    d, n = np.concatenate(dates), np.concatenate(nets).astype(np.float64)
    if not len(d):
        return {"pass": False, "why": "no trade"}
    days, inv = np.unique(d, return_inverse=True)
    N, T = np.zeros(len(days)), np.zeros(len(days))
    np.add.at(N, inv, n)
    np.add.at(T, inv, 1.0)
    ins = day_mask(u, days)
    k, nd = int(ins.sum()), len(days)
    if k == 0 or T[ins].sum() == 0:
        return {"pass": False, "why": "no trade inside the filter"}
    obs, unf = float(N[ins].sum() / T[ins].sum()), float(N.sum() / T.sum())
    out = {"per_trade": round(obs, 2), "unfiltered_per_trade": round(unf, 2), "lift_per_trade": round(obs - unf, 2), "days_in": k,
           "days_all": nd, "replicates": SUBSETS, "real_replicates": SUBSETS, "thin": False}
    if k >= nd:
        return {**out, "pass": False, "why": "the filter keeps every day"}
    rng = np.random.default_rng(seed)
    vals = np.zeros(SUBSETS)
    for a in range(0, SUBSETS, 500):
        pick = np.argsort(rng.random((500, nd)), axis=1)[:, :k]
        vals[a:a + 500] = N[pick].sum(axis=1) / np.maximum(1.0, T[pick].sum(axis=1))
    p = float((obs > vals).mean())
    out.update(p_beat=round(p, 4), subset_p95=round(float(np.percentile(vals, 95)), 2), **{"pass": bool(obs > unf and (p >= P_NEED or not need_p))})
    return out


# ---------------------------------------------------------------- the average variant

def fast_share(xs: list) -> dict:
    """Share of profit from trades held <= 5 s over a list of variants (pooled): winners held < 5 whole seconds / all winners,
    and the net of those trades / the net."""
    gw = fw = net = fnet = 0.0
    for x in xs:
        n, d = np.asarray(x["net"], np.float64), np.asarray(x["dur_s"])
        f = d < FAST_S
        gw += float(n[n > 0].sum())
        fw += float(n[f & (n > 0)].sum())
        net += float(n.sum())
        fnet += float(n[f].sum())
    return {"fast_profit_share": round(fw / gw, 4) if gw > 0 else None, "net_fast": round(fnet / max(1, len(xs)), 2),
            "net": round(net / max(1, len(xs)), 2)}


def avg_variant(xs: list, cal: np.ndarray, years: list) -> list:
    """The AVERAGE variant per year then combined. trades / net / max drawdown = mean over the variants (each variant's own daily
    drawdown inside the row's span); win rate, profit factor, average trade = pooled over all the variants' trades."""
    rows = []
    spans = [(str(y), np.array([dt.date.fromordinal(int(o)).year == y for o in cal])) for y in years] + [("combined", np.ones(len(cal), bool))]
    for name, dm in spans:
        days = cal[dm]
        tr = net = gw = gl = wins = 0.0
        dds = []
        for x in xs:
            m = np.isin(x["date"], days)
            n = np.asarray(x["net"], np.float64)[m]
            tr += len(n)
            net += float(n.sum())
            gw += float(n[n > 0].sum())
            gl += float(-n[n < 0].sum())
            wins += int((n > 0).sum())
            daily = np.zeros(len(days))
            if len(n):
                np.add.at(daily, np.searchsorted(days, x["date"][m]), n)
            eq = np.cumsum(daily)
            dds.append(float((np.maximum.accumulate(np.r_[0.0, eq])[1:] - eq).max()) if len(eq) else 0.0)
        nv = max(1, len(xs))
        rows.append({"period": name, "trades": round(tr / nv, 1), "net": round(net / nv, 2), "win": round(wins / tr, 4) if tr else None,
                     "pf": round(gw / gl, 3) if gl > 0 else None, "max_dd": round(float(np.mean(dds)), 2) if dds else 0.0,
                     "avg_trade": round(net / tr, 2) if tr else None})
    return rows

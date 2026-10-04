#!/usr/bin/python3
"""Adversarial verifier for out/shortlist.csv. Independent hand walk (pure python; only the evalcore loader / pool resolver / day-matched
picker are reused). Run: PYTHONPATH=~/ramos-quant-homebase /usr/bin/python3 verify_shortlist.py [--workers 4] [--top 6]
Outputs out/shortlist_flags.csv (config, flags + diagnostics) and out/shortlist_verify.json (a/b/c/d numbers)."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import sys
import time
import zlib
from multiprocessing import get_context
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalcore as E  # noqa: E402

OUT = E.D / "out"
SNAP_L, SNAP_J = OUT / "a3p2_snap_ledger.csv", OUT / "a3p2_snap_jobs.jsonl"
FIRM_ID = {"lucid": "lucid-flex-50k@2026-09-27", "apex": "apex-legacy-50k@2026-09-27b"}
AX = ["micros", "day_lock", "day_take", "day_stop", "max_day_tr", "target_take"]
GR = {  # copied from the a3_pass2 docstring
    "lucid": {"micros": [10, 20, 30, 40], "day_lock": [0, 750, 1000, 1500], "day_take": [0, 1000, 1250, 1500],
              "day_stop": [0, 1000, 2000], "max_day_tr": [1, 0], "target_take": [0, 1]},
    "apex": {"micros": [20, 40, 60, 80, 100], "day_lock": [0, 1000, 2000], "day_take": [0, 1500, 2000, 3000],
             "day_stop": [0, 1000, 2000, 3000], "max_day_tr": [1, 0], "target_take": [0, 1]},
}
TOGGLE = ("max_day_tr", "target_take")
INF = float("inf")
HARD = ("RULE_STEP", "HM_COLL", "SINGLE_YEAR:", "NET_LE0", "MISMATCH", "USES_2025", "CAP_", "LIFT")   # ONOFF / SINGLE_YEAR_1NQ are notes
ET = ZoneInfo("America/New_York")


def guard():
    """Desk-window rule: no offline compute 09:18-09:36 ET on weekdays."""
    while True:
        n = dt.datetime.now(ET)
        if n.weekday() < 5 and dt.time(9, 18) <= n.time() < dt.time(9, 36):
            time.sleep(20)
        else:
            return


# ------------------------------------------------------------------ independent hand walk

def cost(n):
    return (n // 10) * 4.0 + (n % 10) * 1.0


def walk_day(trs, mf, m, mt, ds, dl, tk, tt, cap, cnt):
    """trs: [(te, tx, side, gross1, mae1)], mf: best-point $ per 1 NQ. -> (tot, worst, traded, closes[(cum, cw, real_at_close)])."""
    real, nent, stop, opens, P, EE, closes = 0.0, 0, False, [], [], [], []

    def flush(upto):
        nonlocal real, stop
        opens.sort()
        while opens and opens[0][0] <= upto:
            o = opens.pop(0)
            real += o[1]
            if dl and real >= dl:
                stop = True
            closes.append((real, nent))

    for k, (te, tx, sd, g, mae) in enumerate(trs):
        if opens:
            flush(te)
        if stop or (mt and nent >= mt):
            continue
        n = m
        if n > cap:
            n = cap
            cnt["clip"] += 1
        c = cost(n)
        p = n * g / 10.0 - c
        w = min(p, -mae * n / 10.0 - c)
        ow = op = 0.0
        conc = n
        for o in opens:
            ow += o[2]
            op += o[1]
            conc += o[4]
        cnt["maxconc"] = max(cnt["maxconc"], conc)
        cnt["ovl"] += 1 if opens else 0
        e = real + ow + w
        if ds and e <= -ds:
            p = -ds - (real + op) - E.TICK_USD * n
            w, stop = p, True
            e = real + ow + w
        elif tk or tt:
            lv = []
            if tk:
                lv.append((tk, tk - E.TICK_USD * n))
            if tt:
                lv.append((tt + E.TICK_USD * n, tt))
            trig, fin = min(lv)
            best = max(n * mf[k] / 10.0 - c, p)
            if real + op + best >= trig:
                p = fin - (real + op)
                w, stop = min(w, p), True
                e = real + ow + w
        opens.append((tx, p, w, sd, n))
        nent += 1
        P.append(p)
        EE.append(e)
    flush(INF)
    if not P:
        return 0.0, 0.0, False, []
    tot = sum(P)
    cl = []
    if closes:
        cum, pm, run, rm = [], [], 0.0, INF
        for p, e in zip(P, EE):
            run += p
            rm = min(rm, e)
            cum.append(run)
            pm.append(rm)
        cl = [(cum[c - 1], min(pm[c - 1], cum[c - 1]), r) for r, c in closes]
    return tot, min(min(EE), tot), True, cl


class Cfg:
    """Trades on a calendar: day index -> ([(te,tx,side,g,mae)], [mfe])."""

    def __init__(self, date, te, tx, side, g, mae, mfe, cal):
        pos = {int(o): i for i, o in enumerate(cal)}
        order = sorted(range(len(date)), key=lambda j: (int(date[j]), int(te[j])))
        self.trs, self.mf = [[] for _ in cal], [[] for _ in cal]
        for j in order:
            i = pos[int(date[j])]
            self.trs[i].append((int(te[j]), int(tx[j]), int(side[j]), float(g[j]), float(mae[j])))
            self.mf[i].append(float(mfe[j]))
        self.D = len(cal)


def base_days(cfg, r, cell, cap):
    """Base walk of every day for one rule cell (target_take off). -> list of (tot, worst, traded, closes), counters."""
    m, dl, tk, ds, mt, _ = cell
    dll = r.get("daily_loss_limit") or 0.0
    ds_eff = min(ds, dll) if (dll and ds) else (dll if dll else ds)
    cnt = dict(clip=0, maxconc=0, ovl=0)
    days = [walk_day(t, f, m, mt, ds_eff, dl, tk, 0.0, cap, cnt) if t else (0.0, 0.0, False, []) for t, f in zip(cfg.trs, cfg.mf)]
    return days, cnt, ds_eff


def take_level(r, profit, largest, td):
    tgt, c = r["eval_target"], r.get("consistency")
    L = tgt - profit
    if c is not None:
        L = max(L, largest / c - profit)
        if not (max(largest, L) <= c * (profit + L) + 1e-9):
            return None
    if td + 1 < r["eval_min_days"]:
        return None
    return L if L > 0 else None


def race_hw(cfg, days, r, cell, ds_eff, cap, models=("eod", "intraday")):
    """{model: (p5, bust5, med_days, pass_by_start[np bool], daily_net)} rolling 5-session starts."""
    m, dl, tk, ds, mt, tt_on = cell
    mll, lock_at, lock_floor, tgt, mind, cons = r["trailing_mll"], r["lock_at"], r["lock_floor"], r["eval_target"], r["eval_min_days"], r.get("consistency")
    dll = r.get("daily_loss_limit") or 0.0
    memo = {}

    def rewalk(i, L):
        if (i, L) not in memo:
            cnt = dict(clip=0, maxconc=0, ovl=0)
            a, b, tr, _ = walk_day(cfg.trs[i], cfg.mf[i], m, mt, ds_eff, dl, tk, L, cap, cnt)
            memo[i, L] = (a, b, tr)
        return memo[i, L]

    res = {}
    for mod in models:
        passed, busted, dd = [], [], []
        for s in range(cfg.D - 4):
            profit = peak = largest = 0.0
            floor, td, out, day = -float(mll), 0, 0, 0
            for k in range(5):
                i = s + k
                pnl, wst, tr, cl = days[i]
                if tt_on:
                    if tr:
                        L = take_level(r, profit, largest, td)
                        if L is not None:
                            pnl, wst, tr = rewalk(i, L)
                else:
                    for (ct, cw, cr) in cl:
                        if profit + cr >= tgt and td + 1 >= mind and (cons is None or max(largest, cr) <= cons * (profit + cr)):
                            pnl, wst = ct, cw
                            break
                if dll:
                    pnl = max(pnl, -dll)
                new = profit + pnl
                if new <= floor or (mod == "intraday" and profit + wst <= floor):
                    out, day = 2, k + 1
                    break
                profit = new
                td += 1 if tr else 0
                largest = max(largest, pnl)
                if new > peak:
                    peak = new
                floor = lock_floor if peak >= lock_at else peak - mll
                if new >= tgt and td >= mind and (cons is None or largest <= cons * new):
                    out, day = 1, k + 1
                    break
            passed.append(out == 1)
            busted.append(out == 2)
            dd.append(day)
        ps = np.array(passed)
        dd = np.array(dd)
        res[mod] = (float(ps.mean()), float(np.mean(busted)), float(np.median(dd[ps])) if ps.any() else float("nan"), ps)
    return res


def daily_net(days, r):
    dll = r.get("daily_loss_limit") or 0.0
    return np.array([max(d[0], -dll) if dll else d[0] for d in days])


# ------------------------------------------------------------------ data helpers

_C = {}


def load_pool(srcs):
    k = tuple(srcs)
    if k not in _C:
        _C[k] = E.concat_tr([E.load(s) for s in srcs])
    return _C[k]


def calendar(*trs):
    s = {dt.date.fromisoformat(d).toordinal() for d in E.tape_sessions("2021-01-01", "2024-12-31")}
    for t in trs:
        s |= set(int(x) for x in t.date)
    return np.array(sorted(s), np.int64)


def cfg_of(t, idx, cal):
    return Cfg(t.date[idx], t.te[idx], t.tx[idx], t.side[idx], t.g[idx], t.mae[idx], t.mfe[idx], cal)


def rules_r(f):
    return E.firm_rules(FIRM_ID[f])[1]


def cell_from(row):
    return tuple(int(row[a]) for a in AX)


def neighbours(f, cell):
    """One-step neighbours on the 6-axis rule grid -> [(axis, direction, cell)]."""
    out = []
    for a_i, a in enumerate(AX):
        vals = GR[f][a]
        j = vals.index(cell[a_i])
        for d in (-1, 1):
            if 0 <= j + d < len(vals):
                c = list(cell)
                c[a_i] = vals[j + d]
                out.append((a, d, tuple(c)))
    return out


def grid_neighbours(gid, cell_i):
    """Cells one step away on one axis of the heat-map grid -> [(axis_key, dir, cell index)]."""
    gj = json.loads((E.GRIDS / gid / "grid.json").read_text())
    cells = {tuple(c["coords"]): c for c in gj["cells"] if c.get("status") == "done"}
    me = next(c for c in gj["cells"] if int(c["i"]) == int(cell_i))
    out = []
    for ax_i, ax in enumerate(gj["axes"]):
        for d in (-1, 1):
            co = list(me["coords"])
            co[ax_i] += d
            c = cells.get(tuple(co))
            if c is not None:
                out.append((ax["key"], d, int(c["i"])))
    return out


# ------------------------------------------------------------------ one config

def verify(a):
    row, do_full, K_fresh = a
    guard()
    f = "lucid" if row["firm"].startswith("lucid") else "apex"
    r = rules_r(f)
    cap = r["cap_micros"]
    fam, key, sess = row["strategy_id"].split("|")
    tf = int(row["tf"])
    params = json.loads(row["params"])
    t = E.load(row["src"])
    prof = E.profile_from(fam, dict(params, tf=tf))
    pl = E.resolve_pool(prof, SNAP_L, SNAP_J)
    pool = load_pool(pl["srcs"])
    cal = calendar(t, pool)
    m_idx = np.flatnonzero(t.sess == E.SESS_CODE[sess])
    cfg = cfg_of(t, m_idx, cal)
    cell = cell_from(row)
    out = dict(config=row["strategy_id"], firm=row["firm"], rank=int(row["rank"]), rules=row["rules"], flags=[], info={})
    fl = out["flags"]

    days, cnt, ds_eff = base_days(cfg, r, cell, cap)
    rc = race_hw(cfg, days, r, cell, ds_eff, cap)
    e, i_ = rc["eod"], rc["intraday"]
    chk = dict(p5_eod=(e[0], float(row["p5_eod"])), bust5_eod=(e[1], float(row["bust5_eod"])), med_eod=(e[2], float(row["med_days_eod"])),
               p5_intra=(i_[0], float(row["p5_intra"])), bust5_intra=(i_[1], float(row["bust5_intra"])))
    out["a"] = {k: dict(hand=v[0], sheet=v[1], diff=v[0] - v[1]) for k, v in chk.items()}
    if any(not (abs(v[0] - v[1]) <= 1.5e-6 or (v[0] != v[0] and v[1] != v[1])) for v in chk.values()):
        fl.append("MISMATCH_p5")
    ps = e[3]

    # ---- (d) data + caps
    raw = json.loads((E._src_dir(row["src"]) / "trades.json").read_text())
    raw = raw if isinstance(raw, list) else raw.get("trades", [])
    n_raw_2025 = sum(1 for x in raw if x["date"] >= "2025-01-01")
    max_used = max(dt.date.fromordinal(int(x)).isoformat() for x in list(t.date) + list(pool.date))
    used_dates = [dt.date.fromordinal(int(d)).isoformat() for d, tr in zip(cal, cfg.trs) if tr]
    rj = json.loads(((E._src_dir(row["src"]) if E._src_dir(row["src"]).is_dir() else E._src_dir(row["src"]).parent) / "run.json").read_text())
    out["d"] = dict(raw_2025plus_dropped=n_raw_2025, max_trade_date=max(used_dates), max_date_own_or_pool=max_used, max_cal=dt.date.fromordinal(int(cal[-1])).isoformat(),
                    run_range_end=(rj.get("range") or {}).get("end"), micros=cell[0], cap=cap, clip=cnt["clip"], max_conc=cnt["maxconc"], overlaps=cnt["ovl"])
    if max(used_dates) >= "2025-01-01" or max_used >= "2025-01-01" or out["d"]["max_cal"] >= "2025-01-01":
        fl.append("USES_2025")
    if cell[0] > cap or cnt["clip"] or cnt["maxconc"] > cap:
        fl.append("CAP_VIOLATION")

    # ---- (b) controls: reproduce production seed (K=10) and a fresh seed set
    sub = SimpleNamespace(date=t.date[m_idx], sess=t.sess[m_idx], n=len(m_idx))
    carry = ("side", "g", "mae", "mfe", "risk", "sess")

    def ctrl_p5(seed, K):
        ctl = E.daymatched_controls(sub, pool, K=K, seed=seed, mask=None, carry=carry)
        v = []
        for c in ctl:
            cc = Cfg(c["date"], c["te"], c["tx"], c["side"], c["g"], c["mae"], c["mfe"], cal)
            dd, _, dse = base_days(cc, r, cell, cap)
            rr = race_hw(cc, dd, r, cell, dse, cap)
            v.append((rr["eod"][0], rr["intraday"][0]))
        return np.array(v)

    thr = float(row["thr_eod"])
    if do_full:
        v0 = ctrl_p5(zlib.crc32(f"{key}|{sess}".encode()), 10)
        out["b_repro"] = dict(ctrl_p5_hand=float(v0[:, 0].mean()), ctrl_p5_sheet=float(row["ctrl_p5_eod"]), diff=float(v0[:, 0].mean() - float(row["ctrl_p5_eod"])))
        if abs(out["b_repro"]["diff"]) > 1.5e-6:
            fl.append("MISMATCH_ctrl")
    v1 = ctrl_p5(zlib.crc32(f"verify-fresh-a|{key}|{sess}".encode()), K_fresh)
    v2 = ctrl_p5(zlib.crc32(f"verify-fresh-b|{key}|{sess}".encode()), K_fresh)
    vv = np.vstack([v1, v2])
    lift_e, lift_i = e[0] - vv[:, 0].mean(), i_[0] - vv[:, 1].mean()
    se = float(vv[:, 0].std(ddof=1) / math.sqrt(len(vv)))
    out["b_fresh"] = dict(K=len(vv), ctrl_eod=float(vv[:, 0].mean()), ctrl_se=se, lift_eod=float(lift_e), lift_eod_sheet=float(row["lift_eod"]), lift_intra=float(lift_i),
                          lift_intra_sheet=float(row["lift_intra"]), thr_eod=thr)
    if lift_e <= thr:
        fl.append("LIFT_FRESH<=THR")
    if lift_i <= 0:
        fl.append("LIFT_INTRA_FRESH<=0")

    # ---- (c) neighbours: rule grid
    p0 = e[0]
    worst_step = worst_tog = (0.0, None)
    nb = []
    for ax, d, c in neighbours(f, cell):
        dd, _, dse = base_days(cfg, r, c, cap)
        pn = race_hw(cfg, dd, r, c, dse, cap, ("eod",))["eod"][0]
        drop = (p0 - pn) / p0 if p0 > 0 else 0.0
        nb.append((ax, d, pn, drop, c))
        tag = f"{ax}{'+' if d > 0 else '-'}{c[AX.index(ax)]}({drop * 100:.0f}%)"
        if drop > 0.4:
            onoff = ax in TOGGLE or 0 in (cell[AX.index(ax)], c[AX.index(ax)])       # feature switched on/off, not a size step
            fl.append(("RULE_ONOFF_COLLAPSE:" if onoff else "RULE_STEP_COLLAPSE:") + tag)
    out["c_rules"] = [dict(axis=x[0], dir=x[1], p5=x[2], rel_drop=x[3], onoff=bool(x[0] in TOGGLE or 0 in (cell[AX.index(x[0])], x[4][AX.index(x[0])]))) for x in nb]
    # neighbouring heat-map cells (same session, identical rules)
    hm = []
    if "#" in row["src"]:
        gid, ci = row["src"].split("#")
        for ax, d, cj in grid_neighbours(gid, int(ci)):
            tn = E.load(f"{gid}#{cj}")
            cn = cal if set(tn.date.tolist()) <= set(cal.tolist()) else calendar(t, pool, tn)
            cfn = cfg_of(tn, np.flatnonzero(tn.sess == E.SESS_CODE[sess]), cn)
            dd, _, dse = base_days(cfn, r, cell, cap)
            rn = race_hw(cfn, dd, r, cell, dse, cap)
            pn = rn["eod"][0]
            drop = (p0 - pn) / p0 if p0 > 0 else 0.0
            ntr = int((tn.sess == E.SESS_CODE[sess]).sum())
            hm.append(dict(axis=ax, dir=d, cell=cj, p5=pn, p5_intra=rn["intraday"][0], rel_drop=drop, trades=ntr))
            if drop > 0.4:
                fl.append(f"HM_COLLAPSE:{ax}{'+' if d > 0 else '-'}#{cj}({drop * 100:.0f}%)")
    else:
        out["info"]["hm"] = "screen run, no heat-map neighbours"
    out["c_hm"] = hm

    # single-year concentration (rules-walked daily net, and raw 1-NQ net)
    dn = daily_net(days, r)
    yrs = np.array([dt.date.fromordinal(int(o)).year for o in cal])
    ny = {int(y): float(dn[yrs == y].sum()) for y in sorted(set(yrs.tolist()))}
    tot = sum(ny.values())
    top_y = max(ny, key=lambda y: ny[y])
    share = ny[top_y] / tot if tot > 0 else float("nan")
    t3 = sum(v for y, v in ny.items() if y >= 2022)
    ys = np.array([dt.date.fromordinal(int(cal[s])).year for s in range(cfg.D - 4)])
    p5y = {int(y): float(ps[ys == y].mean()) for y in (2022, 2023, 2024) if (ys == y).sum() >= 100}
    out["c_year"] = dict(net_by_year=ny, total=tot, top_year=top_y, top_share=share, top_share_2022_24=(max(v for y, v in ny.items() if y >= 2022) / t3 if t3 > 0 else float("nan")), p5_by_year=p5y)
    if tot <= 0:
        fl.append("NET_LE0_AT_RULES")
    elif share > 0.6:
        fl.append(f"SINGLE_YEAR:{top_y}({share * 100:.0f}%)")
    q = np.maximum(1.0, np.array([float(x.get("qty") or 1) for x in raw if x["date"] < "2025-01-01"]))
    dates = [x["date"] for x in raw if x["date"] < "2025-01-01"]
    tsess = t.sess
    net1 = np.array([float(x["net"]) for x in raw if x["date"] < "2025-01-01"]) / q
    sel = tsess == E.SESS_CODE[sess]
    n1 = {}
    for j in np.flatnonzero(sel):
        n1[int(dates[j][:4])] = n1.get(int(dates[j][:4]), 0.0) + float(net1[j])
    t1 = sum(n1.values())
    if t1 > 0 and max(n1.values()) / t1 > 0.6:
        fl.append(f"SINGLE_YEAR_1NQ:{max(n1, key=n1.get)}({max(n1.values()) / t1 * 100:.0f}%)")
    out["c_year"]["net1nq_by_year"] = n1
    # informational
    if i_[0] < 0.5 * e[0]:
        out["info"]["eod_model_dependent"] = True
    out["p5_eod_hand"], out["p5_intra_hand"] = e[0], i_[0]
    return out


# ------------------------------------------------------------------ driver

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--top", type=int, default=6)
    ap.add_argument("--kfresh", type=int, default=10)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    rows = list(csv.DictReader((OUT / "shortlist.csv").open()))
    tasks = [(r, int(r["rank"]) <= a.top, a.kfresh) for r in rows]
    if a.limit:
        tasks = tasks[: a.limit]
    t0 = time.time()
    res = []
    with get_context("spawn").Pool(a.workers, maxtasksperchild=10) as pl:
        for i, x in enumerate(pl.imap_unordered(verify, tasks, chunksize=1), 1):
            res.append(x)
            if i % 5 == 0:
                print(f"{i}/{len(tasks)} {time.time() - t0:.0f}s", flush=True)
    res.sort(key=lambda x: (x["firm"], x["rank"]))
    (OUT / "shortlist_verify.json").write_text(json.dumps(res, indent=1, default=str))
    with (OUT / "shortlist_flags.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["config", "firm", "rank", "rules", "flags", "p5_eod_hand", "p5_intra_hand", "fresh_lift_eod", "sheet_lift_eod", "thr_eod", "min_rule_step_p5_rel",
                    "min_hm_p5_rel", "top_year", "top_year_share", "p5_by_year", "eod_model_dependent", "hard_flag"])
        for x in res:
            steps = [1 - c["rel_drop"] for c in x["c_rules"] if c["axis"] not in TOGGLE and not c.get("onoff")]
            hms = [1 - c["rel_drop"] for c in x["c_hm"]]
            w.writerow([x["config"], x["firm"], x["rank"], x["rules"], ";".join(x["flags"]) or "OK", round(x["p5_eod_hand"], 6), round(x["p5_intra_hand"], 6),
                        round(x["b_fresh"]["lift_eod"], 4), round(x["b_fresh"]["lift_eod_sheet"], 4), round(x["b_fresh"]["thr_eod"], 4),
                        round(min(steps), 3) if steps else "", round(min(hms), 3) if hms else "", x["c_year"]["top_year"], round(x["c_year"]["top_share"], 3),
                        "/".join(f"{v:.2f}" for v in x["c_year"]["p5_by_year"].values()), int(bool(x["info"].get("eod_model_dependent"))),
                        int(any(f.startswith(HARD) for f in x["flags"]))])
    print("done", len(res), f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()

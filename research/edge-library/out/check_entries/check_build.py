"""INDEPENDENT CHECK of STAGE 4 (BUILD only). Own code: reads runs/<key>/run.json + cells.npz and engine/cache/events.csv
directly. Does NOT import out/entries/*, out/events/* or library.py. No 2024 / 2025+ P&L is read (stores are asserted BUILD).
  python out/check_entries/check_build.py  ->  out/check_entries/check_units.csv, check_per_x.csv, check_build.log (stdout)"""
import csv
import datetime as dt
import json
import math
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[2]
RUNS = W / "runs"
OUT = Path(__file__).resolve().parent
SESS7 = ("eve", "asia", "london", "pre", "nyam", "mid", "pm")
BAR = {"NQ": 2.5607770536606678, "ES": 2.0010262339325084, "GC": 1.627917623785153}      # the files' values (read by hand)
ALPHA = 1 - 0.05 / 18
TIER1 = {"NFP", "CPI", "PPI", "RETAIL", "GDP", "PCE"}
UNITS = [("W", "straddle_wide_0830", "pre", ("A", "B")), ("W", "straddle_wide_1000", "nyam", ("C",)),
         ("D", "event_dir_0830", "pre", ("A", "B")), ("D", "event_dir_1000", "nyam", ("C",))]
ROOTS = ("NQ", "ES", "GC")
B0, B1 = dt.date(2021, 9, 22).toordinal(), dt.date(2023, 12, 31).toordinal()


def cal():
    rows = list(csv.DictReader((W / "engine" / "cache" / "events.csv").open()))
    assert all(r["time_et"] in ("08:30", "10:00", "14:00") for r in rows), {r["time_et"] for r in rows}
    g = {"A": set(), "B": set(), "C": set()}
    for r in rows:
        if r["date"] >= "2025-01-01":
            continue
        o = dt.date.fromisoformat(r["date"]).toordinal()
        if r["time_et"] == "08:30":
            g["A"].add(o)
            if r["type"] in TIER1:
                g["B"].add(o)
        elif r["time_et"] == "10:00":
            g["C"].add(o)
    return {k: np.array(sorted(v), np.int64) for k, v in g.items()}, rows


G, CAL_ROWS = cal()


def load(key):
    d = RUNS / key
    meta = json.loads((d / "run.json").read_text())
    z = np.load(d / "cells.npz")
    u = {k: z[k] for k in z.files}
    assert meta["period"] == "build" and meta["range"]["end"] <= "2023-12-31" and meta["range"]["start"] == "2021-09-22", key
    if len(u["date"]):
        assert B0 <= int(u["date"].min()) and int(u["date"].max()) <= B1, (key, "dates outside BUILD")
    return meta, u


def cell(u, i):
    a, b = int(u["off"][i]), int(u["off"][i + 1])
    return {k: u[k][a:b] for k in ("date", "entry_ms", "dur_s", "net", "side", "sess")}


def tstat(x):
    x = np.asarray(x, np.float64)
    n = len(x)
    if n < 2:
        return None
    sd = x.std(ddof=1)
    return float(x.mean() / (sd / math.sqrt(n))) if sd > 0 else None


def heat(meta, u, scode, gdays, vi_only=None):
    """-> (judged rows [(idx, id, vi, xi, net, trades)], n_dead, n_dup). dead = the variant has no trade in the session in any
    exit cell over the whole store; identical trade lists (on the judged days) counted once, first in (vi, xi) order."""
    cells = meta["cells"]
    alive = set()
    for i, c in enumerate(cells):
        x = cell(u, i)
        if (x["sess"] == scode).any():
            alive.add(c["vi"])
    rows, seen, dead, dup = [], set(), 0, 0
    for i in sorted(range(len(cells)), key=lambda k: (cells[k]["vi"], cells[k]["xi"])):
        c = cells[i]
        if vi_only is not None and c["vi"] != vi_only:
            continue
        if c.get("info"):
            continue
        if c["vi"] not in alive:
            dead += 1
            continue
        x = cell(u, i)
        m = (x["sess"] == scode) & np.isin(x["date"], gdays)
        sig = (x["entry_ms"][m].tobytes(), x["dur_s"][m].tobytes(), x["side"][m].tobytes(),
               np.round(x["net"][m] * 100).astype(np.int64).tobytes()) if m.any() else "empty"
        if sig in seen:
            dup += 1
            continue
        seen.add(sig)
        rows.append((i, c["id"], c["vi"], c["xi"], float(x["net"][m].sum()), int(m.sum())))
    return rows, dead, dup


def central(rows):
    net = np.array([r[4] for r in rows])
    med = float(np.median(net))
    pos = [k for k in range(len(rows)) if net[k] > 0]
    if not pos:
        return None, med, 0.0
    k = min(pos, key=lambda k: (round(abs(net[k] - med), 6), rows[k][2], rows[k][3]))
    return rows[k], med, float((net > 0).mean())


def subset_pct(x, gdays, seed, draws):
    days, inv = np.unique(x["date"], return_inverse=True)
    daily = np.zeros(len(days))
    np.add.at(daily, inv, x["net"].astype(np.float64))
    ins = np.isin(days, gdays)
    k, n = int(ins.sum()), len(days)
    obs = float(daily[ins].sum())
    rng = np.random.default_rng(seed)
    beat, done = 0, 0
    while done < draws:
        b = min(1000, draws - done)
        pick = np.argsort(rng.random((b, n)), axis=1)[:, :k]
        beat += int((obs > daily[pick].sum(axis=1)).sum())
        done += b
    # normal approximation of the same test (sampling k of n days without replacement), as a cross-check
    mu, var = k * daily.mean(), k * daily.var(ddof=1) * (1 - k / n)
    z = (obs - mu) / math.sqrt(var) if var > 0 else 0.0
    return beat / draws, k, n, z


def fast5(x):
    net, dur = x["net"].astype(np.float64), x["dur_s"]
    fw = float(net[(dur < 5) & (net > 0)].sum())
    gw = float(net[net > 0].sum())
    return float(net.sum()) - fw, fw, (fw / gw if gw > 0 else None), float(net[dur < 5].sum()), int((dur < 5).sum()), float(np.median(dur)) if len(dur) else None


def sessions_2024(root):
    """COUNT of 2024 trading days per group (calendar only, no P&L): weekdays of 2024 on the events calendar. The analyst counts
    the root's cached 2024 sessions; a holiday release would differ by a day or two -- test (a) has > 10 trades of slack or none."""
    return {g: int(sum(1 for o in G[g] if dt.date.fromordinal(int(o)).year == 2024)) for g in G}


def main():
    units, perx = [], []
    for code, fam, sess, groups in UNITS:
        scode = SESS7.index(sess)
        for g in groups:
            clock = "A" if g in ("A", "B") else "C"
            for root in ROOTS:
                key = f"{fam}-{root}-tf30"
                meta, u = load(key)
                smeta, su = load(key + "-shift")
                assert len(meta["cells"]) == (36 if code == "W" else 224), key
                other = sorted({SESS7[int(s)] for s in np.unique(u["sess"]) if s != scode})
                rows, dead, dup = heat(meta, u, scode, G[g])
                cm, med, sp = central(rows)
                uid = f"{code}-{g}-{root}"
                r = {"uid": uid, "cells": len(rows), "dead": dead, "dup": dup, "positive": int(sum(x[4] > 0 for x in rows)),
                     "share_pos": round(sp, 4), "median_net": round(med, 2), "other_sessions_in_store": "/".join(other)}
                r["v60"], r["v70"], r["v80"] = [bool(med > 0 and sp >= v - 1e-12) for v in (0.6, 0.7, 0.8)]
                r["b"] = r["v60"]
                if cm is None:
                    r.update(central=None, a=False, c=False, d=False, e=False, g5=False)
                    units.append(r)
                    continue
                x = cell(u, cm[0])
                ms = x["sess"] == scode
                xs = {k: v[ms & np.isin(x["date"], G[g])] for k, v in x.items()}
                xn = {k: v[ms & ~np.isin(x["date"], G[clock])] for k, v in x.items()}
                xu = {k: v[ms] for k, v in x.items()}
                t = tstat(xs["net"]) or 0.0
                me, mn = float(xs["net"].mean()), (float(xn["net"].mean()) if len(xn["net"]) else 0.0)
                p4, k, n, z = subset_pct(xu, G[g], 20261004, 4000)
                p200, _, _, _ = subset_pct(xu, G[g], 7, 200000)
                wo, fw, share, nfast, nf, hold = fast5(xs)
                d24 = sessions_2024(root)[g]
                nul = []
                for sd in (1, 2):
                    j = next(i for i, c in enumerate(smeta["cells"]) if c["id"] == f"s{sd}_{cm[1]}")
                    y = cell(su, j)
                    nul.append(float(y["net"][np.isin(y["date"], G[g])].sum()))
                yr = {}
                for yy in (2021, 2022, 2023):
                    m = np.array([dt.date.fromordinal(int(o)).year == yy for o in xs["date"]], bool)
                    yr[yy] = round(float(xs["net"][m].sum()), 2)
                r.update(central=cm[1], trades=len(xs["net"]), net=round(float(xs["net"].sum()), 2), t=round(t, 4), bar=round(BAR[root], 4),
                         mean_event=round(me, 2), mean_nonevent=round(mn, 2), lift=round(me - mn, 2), nonevent_trades=len(xn["net"]),
                         e_p4000=round(p4, 5), e_p200k=round(p200, 5), e_z=round(z, 3), days_in=k, days_all=n,
                         net_wo_fast_winners=round(wo, 2), fast_winner_usd=round(fw, 2), fast_profit_share=None if share is None else round(share, 4),
                         net_fast=round(nfast, 2), fast_trades=nf, median_hold_s=hold, days_2024=d24, null_mean=round(float(np.mean(nul)), 2),
                         y2021=yr[2021], y2022=yr[2022], y2023=yr[2023],
                         a=bool(len(xs["net"]) + d24 >= 100), c=bool(me - mn > 0), d=bool(t >= BAR[root]), e=bool(p200 >= ALPHA), g5=bool(wo > 0))
                r["e_4000_agrees"] = bool((p4 >= ALPHA) == r["e"])
                r["pass_ae"] = bool(r["a"] and r["b"] and r["c"] and r["d"] and r["e"])
                r["pass"] = bool(r["pass_ae"] and r["g5"])
                r["failed"] = ", ".join(nm for nm, kk in (("a", "a"), ("b", "b"), ("c", "c"), ("d", "d"), ("e", "e"), ("5s", "g5")) if not r[kk])
                units.append(r)
                if code == "D":
                    variants = {c["vi"]: c["variant"] for c in meta["cells"]}
                    for vi in sorted(variants):
                        rr, _, _ = heat(meta, u, scode, G[g], vi_only=vi)
                        nets = np.array([q[4] for q in rr])
                        wof, nulm = [], []
                        for q in rr:
                            xx = cell(u, q[0])
                            mm = (xx["sess"] == scode) & np.isin(xx["date"], G[g])
                            wof.append(fast5({k: v[mm] for k, v in xx.items()})[0])
                            nn = []
                            for sd in (1, 2):
                                j = next(i for i, c in enumerate(smeta["cells"]) if c["id"] == f"s{sd}_{q[1]}")
                                y = cell(su, j)
                                nn.append(float(y["net"][np.isin(y["date"], G[g])].sum()))
                            nulm.append(float(np.mean(nn)))
                        perx.append({"uid": uid, "x": variants[vi]["x"], "cells": len(rr), "share_pos": round(float((nets > 0).mean()), 4),
                                     "median_net": round(float(np.median(nets)), 2), "median_net_wo_fast_winners": round(float(np.median(wof)), 2),
                                     "null_median_net": round(float(np.median(nulm)), 2),
                                     "beats_null_share": round(float(np.mean(nets > np.array(nulm))), 4), "trades": max(q[5] for q in rr)})
    cols = sorted({k for r in units for k in r}, key=lambda k: (k != "uid", k))
    with (OUT / "check_units.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, cols)
        w.writeheader()
        w.writerows(units)
    with (OUT / "check_per_x.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, list(perx[0]))
        w.writeheader()
        w.writerows(perx)
    print("calendar days <2025: A", len(G["A"]), "B", len(G["B"]), "C", len(G["C"]), "| alpha", round(ALPHA, 5))
    for r in units:
        print(f"{r['uid']:7s} {str(r.get('central')):18s} cells {r['cells']} (dead {r['dead']} dup {r['dup']}) pos {r['share_pos']} "
              f"({int(r['v60'])}{int(r['v70'])}{int(r['v80'])}) med {r['median_net']} | tr {r.get('trades')} net {r.get('net')} t {r.get('t')}/{r.get('bar')} "
              f"| lift {r.get('lift')} | e {r.get('e_p4000')} / {r.get('e_p200k')} z {r.get('e_z')} | wo-fw {r.get('net_wo_fast_winners')} share {r.get('fast_profit_share')} "
              f"hold {r.get('median_hold_s')} | null {r.get('null_mean')} | yrs {r.get('y2021')} {r.get('y2022')} {r.get('y2023')} | "
              f"{'PASS' if r.get('pass') else 'fail ' + str(r.get('failed'))} | other sess {r['other_sessions_in_store'] or '-'}")
    for x in perx:
        print("  X", x)

    # ---- compare with the analyst's tables (numbers only; nothing of his code is run)
    an = {r["uid"]: r for r in csv.DictReader((W / "out" / "entries" / "build_units.csv").open())}
    bad = []
    for r in units:
        a = an[r["uid"]]
        chk = [("central", str(r.get("central")), a["central"]), ("cells", r["cells"], int(a["cells"])),
               ("positive", r["positive"], int(a["positive"])), ("median_net", r["median_net"], float(a["median_net"])),
               ("trades", r.get("trades"), int(a["trades"])), ("net", r.get("net"), float(a["net"])),
               ("t", round(r.get("t") or 0, 3), round(float(a["t"]), 3)), ("lift", r.get("lift"), float(a["lift_mean"])),
               ("wo_fw", r.get("net_wo_fast_winners"), float(a["net_wo_fast_winners"])),
               ("null_mean", r.get("null_mean"), float(a["null_mean"])), ("days_in", r.get("days_in"), int(a["days_in"])),
               ("days_all", r.get("days_all"), int(a["days_all"]))]
        for nm, mine, his in chk:
            if isinstance(mine, float) and abs(mine - his) > 0.011 or (not isinstance(mine, float) and mine != his):
                bad.append((r["uid"], nm, mine, his))
        for nm in ("a", "b", "c", "d", "e", "g5", "pass"):
            if str(r[nm]) != a[nm]:
                bad.append((r["uid"], "verdict " + nm, r[nm], a[nm]))
        if abs(r["e_p200k"] - float(a["e_p"])) > 0.01:
            bad.append((r["uid"], "e_p (>1 pt apart)", r["e_p200k"], a["e_p"]))
        if int(a["event_days_2024"]) != r["days_2024"]:
            bad.append((r["uid"], "2024 day count (info)", r["days_2024"], a["event_days_2024"]))
    ax = {(r["uid"], float(r["x"])): r for r in csv.DictReader((W / "out" / "entries" / "per_x.csv").open())}
    for x in perx:
        a = ax[(x["uid"], float(x["x"]))]
        for nm in ("cells", "share_pos", "median_net", "median_net_wo_fast_winners", "null_median_net", "beats_null_share", "trades"):
            if abs(float(x[nm]) - float(a[nm])) > 0.011:
                bad.append((x["uid"], x["x"], nm, x[nm], a[nm]))
    print("DIFFERENCES vs the analyst:", len(bad))
    for b in bad:
        print("  ", b)
    print("units passing BUILD (mine):", [r["uid"] for r in units if r.get("pass")], "| a-e only:", [r["uid"] for r in units if r.get("pass_ae")])


if __name__ == "__main__":
    main()

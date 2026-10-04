"""CHECKER stage 3: every admitted event member, recomputed two ways (nothing goes to the ledger):
  A. the engine from scratch (l2sim.run on the member's spec inputs), base and 2 ticks + 250 ms, BUILD and 2024;
  B. MY OWN tick replay of the written rule (no engine order code): bracket around the last print 1 s before the clock time,
     live 85 ms later, OCO, cancel after 5 min, stop / target in points, flat 15:58 (13:13 NQ half days), 1 tick slip, $4.
Compared trade for trade with members/<name>/trades_*.json (event days) and with the unit stores (all days).
Fill probe (own): a triggered stop entry fills at the first print >= 1 / 5 / 25 ms after its trigger print, never better
than the stop price (+ 1 tick); exits from that fill (same distances). Also with the stop-loss EXIT delayed the same way (info).
2024 is read only for cells the analyst already read. EXAM never."""
import csv, datetime as dt, json, sys
from multiprocessing import get_context
from pathlib import Path
import numpy as np
W = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(W)); sys.path.insert(0, str(W / "engine"))
import l2sim as S  # noqa: E402
import families  # noqa: E402
OUT = Path(__file__).resolve().parent
MS = 1_000_000
EV = [r for r in csv.DictReader(open(W / 'engine/cache/events.csv')) if r['date'] < '2025-01-01']
T1 = {'NFP', 'CPI', 'PPI', 'RETAIL', 'GDP', 'PCE'}
G = {'A': {r['date'] for r in EV if r['time_et'] == '08:30'},
     'B': {r['date'] for r in EV if r['time_et'] == '08:30' and r['type'] in T1},
     'C': {r['date'] for r in EV if r['time_et'] == '10:00'}}
MEMBERS = [
    dict(name='straddle_tight_0830_GC_tf30_pre_evA', fam='straddle_tight_0830', root='GC', arm='08:29:59', off=0.6, stop=1.6, tgt=1.6, group='A', cell='offA_pts1p6-r1', sess='pre', also='B'),
    dict(name='straddle_tight_0830_NQ_tf30_pre_evB', fam='straddle_tight_0830', root='NQ', arm='08:29:59', off=5.0, stop=5.0, tgt=15.0, group='B', cell='offB_pts5-r3', sess='pre'),
    dict(name='straddle_tight_1000_GC_tf30_nyam_evC', fam='straddle_tight_1000', root='GC', arm='09:59:59', off=0.6, stop=1.6, tgt=1.6, group='C', cell='offA_pts1p6-r1', sess='nyam'),
]
# (slip_ticks, place_ms, entry_delay_ms, delay_stop_exit)
VARS = [(1.0, 85, 0, False), (2.0, 250, 0, False), (1.0, 85, 1, False), (1.0, 85, 5, False), (1.0, 85, 25, False),
        (1.0, 85, 1, True), (1.0, 85, 5, True), (1.0, 85, 25, True), (2.0, 85, 0, False), (3.0, 85, 0, False)]


def own_day(args):
    root, iso, arm, OFF, STOP, TGT = args
    d = dt.date.fromisoformat(iso)
    S.check_holdout(d, False)
    assert d < dt.date(2025, 1, 1)
    PV, TICK = S.SPECS[root]
    tt = lambda x: round(round(x / TICK) * TICK, 6)
    tape = S.load_tape(d, root)
    if tape is None or not len(tape.ts):
        return iso, None
    flat = S.day_flat(d, root)
    w_end = "13:15" if flat != "15:58" else "16:10"
    ts, px = tape.ts, tape.px
    t_arm = S.et_ns(d, arm)
    t_cancel = t_arm + 300 * 1_000_000_000
    lo = int(np.searchsorted(ts, S.et_ns(d, "00:00"), "left"))
    hi = int(np.searchsorted(ts, S.et_ns(d, w_end), "left"))
    ia = int(np.searchsorted(ts, t_arm, "left"))
    if ia <= lo or ia >= hi:
        return iso, {v: None for v in VARS}
    lp = float(px[ia - 1])
    up, dn = tt(lp + OFF), tt(lp - OFF)
    ic = int(np.searchsorted(ts, t_cancel, "left"))
    ifl = min(int(np.searchsorted(ts, S.et_ns(d, flat), "left")), hi)
    out = {}
    for v in VARS:
        slip_t, place_ms, trig_ms, dly_exit = v
        slip = slip_t * TICK
        a = int(np.searchsorted(ts, t_arm + place_ms * MS, "left"))
        seg = px[a:min(ic, hi)]
        hit = np.flatnonzero((seg >= up - 1e-9) | (seg <= dn + 1e-9))
        if not len(hit):
            out[v] = None; continue
        k = a + int(hit[0])
        side = 1 if px[k] >= up - 1e-9 else -1
        stop_px = up if side > 0 else dn
        kf = k if not trig_ms else int(np.searchsorted(ts, ts[k] + trig_ms * MS, "left"))
        if kf >= hi:
            out[v] = None; continue
        p = float(px[kf])
        fill = tt((max(stop_px, p) + slip) if side > 0 else (min(stop_px, p) - slip))
        sl, tp = tt(fill - side * STOP), tt(fill + side * TGT)
        b = kf + 1
        seg = px[b:ifl]
        if side > 0:
            h_sl = np.flatnonzero(seg <= sl + 1e-9); h_tp = np.flatnonzero(seg >= tp + TICK - 1e-9)
        else:
            h_sl = np.flatnonzero(seg >= sl - 1e-9); h_tp = np.flatnonzero(seg <= tp - TICK + 1e-9)
        i_sl = b + int(h_sl[0]) if len(h_sl) else None
        i_tp = b + int(h_tp[0]) if len(h_tp) else None
        if i_sl is not None and (i_tp is None or i_sl <= i_tp):
            ke = i_sl if not (trig_ms and dly_exit) else min(int(np.searchsorted(ts, ts[i_sl] + trig_ms * MS, "left")), hi - 1)
            q = float(px[ke])
            ex = tt((min(sl, q) - slip) if side > 0 else (max(sl, q) + slip)); why, kx = "sl", ke
        elif i_tp is not None:
            ex, why, kx = tp, "tp", i_tp
        else:
            kx = ifl if ifl < hi else hi - 1
            ex, why = tt(float(px[kx]) - side * slip), "time"
        net = side * (ex - fill) * PV - 4.0
        path = px[kf:kx + 1]
        mae = max(0.0, (fill - float(min(path.min(), ex))) if side > 0 else (float(max(path.max(), ex)) - fill))
        out[v] = {"date": iso, "side": side, "entry_ms": int(ts[kf]) // MS, "exit_ms": int(ts[kx]) // MS, "entry": fill, "exit": ex, "why": why,
                  "net": round(net, 2), "stop_px": stop_px, "slip_pts": round(side * (fill - stop_px), 6), "dur_s": (int(ts[kx]) - int(ts[kf])) / 1e9,
                  "mae_usd": round(mae * PV, 2), "trig_ms": int(ts[k]) // MS}
    return iso, out


def cmp(mine, other, label, quiet=False):
    a = {t["date"]: t for t in mine}; b = {t["date"]: t for t in other}
    only_a, only_b = sorted(set(a) - set(b)), sorted(set(b) - set(a))
    diff = []
    for d in sorted(set(a) & set(b)):
        x, y = a[d], b[d]
        xs = x["side"] if isinstance(x["side"], int) else (1 if x["side"] == "long" else -1)
        ys = y["side"] if isinstance(y["side"], int) else (1 if y["side"] == "long" else -1)
        xe, ye = x.get("entry_price", x.get("entry")), y.get("entry_price", y.get("entry"))
        if xs != ys or x["entry_ms"] != y["entry_ms"] or abs(x["net"] - y["net"]) > 0.005 or abs(xe - ye) > 1e-9:
            diff.append((d, xs, ys, x["entry_ms"], y["entry_ms"], x["net"], y["net"]))
    r = {"a": len(a), "a_net": round(sum(t["net"] for t in mine), 2), "b": len(b), "b_net": round(sum(t["net"] for t in other), 2),
         "only_a": only_a, "only_b": only_b, "differing": len(diff), "diff_head": diff[:5]}
    print(f"  {label}: {r['a']} trades {r['a_net']:.2f} | {r['b']} trades {r['b_net']:.2f} | only left {len(only_a)} only right {len(only_b)} | differing {len(diff)}", flush=True)
    for x in diff[:4]: print("     diff", x)
    if only_a or only_b: print("     only left", only_a[:6], "only right", only_b[:6])
    return r


def main():
    rep = {}
    reads = []
    with get_context("spawn").Pool(8) as pool:
        for M in MEMBERS:
            name, root = M["name"], M["root"]
            spec = json.loads((W / "members" / name / "spec.json").read_text())
            cls = families.REGISTRY[M["fam"]][0]
            params = dict(spec["inputs"])
            rep[name] = {}
            print("==", name, flush=True)
            for period in ("build", "pick"):
                a, b = S.period(period)
                days = [d.isoformat() for d in S.sessions(a, b, root)]
                assert days[-1] < "2025-01-01"
                res = dict(pool.imap_unordered(own_day, [(root, d, M["arm"], M["off"], M["stop"], M["tgt"]) for d in days], chunksize=8))
                base_e = S.run(cls, params, period=period, root=root, workers=8)
                str_e = S.run(cls, params, period=period, root=root, workers=8, **S.STRESS)
                skipped = {s["date"] for s in base_e["skipped"]}
                own = {v: [r[v] for d, r in sorted(res.items()) if r is not None and r.get(v) is not None and d not in skipped] for v in VARS}
                R = {"sessions": len(days), "engine_skipped": sorted(skipped), "range": base_e["meta"]["range"]}
                print(f" {period}: sessions {len(days)} engine range {base_e['meta']['range']} skipped {len(skipped)}")
                # store cell (all days)
                key = f"{M['fam']}-{root}-tf30" if period == "build" else f"{M['fam']}-{root}-tf30-{M['sess']}-pick"
                rd = W / "runs" if period == "build" else (W / "runs_admit_r1" if (W / "runs_admit_r1" / key).exists() else W / "runs_events")
                meta = json.loads((rd / key / "run.json").read_text()); z = np.load(rd / key / "cells.npz")
                i = next(k for k, c in enumerate(meta["cells"]) if c["id"] == M["cell"])
                o0, o1 = int(z["off"][i]), int(z["off"][i + 1])
                sm = z["sess"][o0:o1] == {"pre": 3, "nyam": 4}[M["sess"]]
                st_ms, st_net = z["entry_ms"][o0:o1][sm], z["net"][o0:o1][sm]
                e_ms = np.array([t["entry_ms"] for t in base_e["trades"]]); e_net = np.array([t["net"] for t in base_e["trades"]])
                same_store = len(st_ms) == len(e_ms) and bool((np.sort(st_ms) == np.sort(e_ms)).all()) and abs(st_net.sum() - e_net.sum()) < 0.01 and bool(np.allclose(st_net[np.argsort(st_ms)], e_net[np.argsort(e_ms)]))
                print(f"  engine re-run vs store {rd.name}/{key} cell {M['cell']}: store {len(st_ms)} trades {st_net.sum():.2f} | engine {len(e_ms)} trades {e_net.sum():.2f} | identical {same_store}")
                R["engine_vs_store_identical"] = same_store
                for g in [M["group"]] + ([M["also"]] if M.get("also") else []):
                    gd = G[g]
                    f = lambda L: [t for t in L if t["date"] in gd]
                    Rg = {}
                    if g == M["group"]:
                        mem = json.loads((W / "members" / name / f"trades_{period}.json").read_text())
                        Rg["engine_vs_member_file"] = cmp(f(base_e["trades"]), mem, f"[{g}] engine re-run (event days) vs member file")
                    Rg["own_vs_engine_base"] = cmp(f(own[VARS[0]]), f(base_e["trades"]), f"[{g}] OWN replay vs engine (base)")
                    Rg["own_vs_engine_stress"] = cmp(f(own[VARS[1]]), f(str_e["trades"]), f"[{g}] OWN replay vs engine (2 ticks + 250 ms)")
                    tr = f(own[VARS[0]])
                    net = np.array([t["net"] for t in tr])
                    Rg["base"] = {"trades": len(tr), "net": round(float(net.sum()), 2), "t": float(net.mean() / (net.std(ddof=1) / np.sqrt(len(net)))),
                                  "win": float((net > 0).mean()), "worst_open_loss": max(t["mae_usd"] for t in tr)}
                    Rg["stress_engine"] = {"trades": len(f(str_e["trades"])), "net": round(sum(t["net"] for t in f(str_e["trades"])), 2)}
                    Rg["per_year"] = {}
                    for t in tr: Rg["per_year"].setdefault(t["date"][:4], [0, 0.0]); Rg["per_year"][t["date"][:4]][0] += 1; Rg["per_year"][t["date"][:4]][1] += t["net"]
                    fast = [t for t in tr if t["dur_s"] <= 2.0]
                    Rg["le_2s"] = {"trades": len(fast), "net": round(sum(t["net"] for t in fast), 2)}
                    Rg["probe"] = {}
                    for v in VARS[2:]:
                        x = f(own[v])
                        Rg["probe"][(f"{v[2]}ms{'_exit_too' if v[3] else ''}") if v[2] else f"slip{v[0]:g}ticks_only"] = {"trades": len(x), "net": round(sum(t["net"] for t in x), 2),
                                                                               "mean_slip": round(float(np.mean([t["slip_pts"] for t in x])), 3)}
                    Rg["mean_slip_base"] = round(float(np.mean([t["slip_pts"] for t in tr])), 3)
                    # the whole-day control: all days outside the group, base
                    print(f"  [{g}] base {Rg['base']} | stress {Rg['stress_engine']} | <=2s {Rg['le_2s']} | per year {Rg['per_year']}")
                    print(f"  [{g}] probe {Rg['probe']}")
                    R[g] = Rg
                    if period == "pick":
                        reads.append((name, M["fam"], root, M["cell"], g, "2024", "central variant: engine re-run base + stress, own replay, fill probe 1/5/25 ms", len(tr), round(float(net.sum()), 2)))
                R["own_all_days"] = {"trades": len(own[VARS[0]]), "net": round(sum(t["net"] for t in own[VARS[0]]), 2)}
                R["own_vs_engine_all_days"] = cmp(own[VARS[0]], base_e["trades"], "[all days] OWN replay vs engine (base)")
                rep[name][period] = R
                (OUT / f"own_{name}_{period}.json").write_text(json.dumps(own[VARS[0]]))
                (OUT / f"own5_{name}_{period}.json").write_text(json.dumps(own[VARS[3]]))
    (OUT / "chk_member.json").write_text(json.dumps(rep, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
    import os
    if os.environ.get("SKIP_READS"): return
    newf = not (OUT / "checker_pick_reads.csv").exists()
    with (OUT / "checker_pick_reads.csv").open("a", newline="") as fh:
        w = csv.writer(fh)
        if newf: w.writerow(["member", "family", "root", "cell", "group", "period", "what", "trades", "net"])
        w.writerows(reads)


if __name__ == "__main__":
    main()

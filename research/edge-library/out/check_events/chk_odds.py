"""CHECKER stage 3: (1) own fill probe of orb_NQ_tf1_pre on its stored trade records (trade list fixed, each trade re-priced on
the tape; L = 0 must equal the stored net); (2) the odds of two accounts (Lucid Flex 50K, Apex 50K eval) with MY OWN day walk,
'about $1,000 of risk' size cut to the contract limit, both fill models (trigger print; 5 ms later = my own re-priced trades).
BUILD + 2024 trades already read by the analyst. 2025+ never."""
import csv, datetime as dt, json, sys
from multiprocessing import get_context
from pathlib import Path
import numpy as np
sys.dont_write_bytecode = True
W = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(W)); sys.path.insert(0, str(W / "engine"))
import l2sim as S  # noqa: E402
OUT = Path(__file__).resolve().parent
MS = 1_000_000
EV = [r for r in csv.DictReader(open(W / 'engine/cache/events.csv')) if r['date'] < '2025-01-01']
T1 = {'NFP', 'CPI', 'PPI', 'RETAIL', 'GDP', 'PCE'}
G = {'A': {r['date'] for r in EV if r['time_et'] == '08:30'}, 'B': {r['date'] for r in EV if r['time_et'] == '08:30' and r['type'] in T1},
     'C': {r['date'] for r in EV if r['time_et'] == '10:00'}}


def orb_day(args):
    root, iso, trades = args
    d = dt.date.fromisoformat(iso); S.check_holdout(d, False); assert d.year < 2025
    PV, TICK = S.SPECS[root]
    tt = lambda x: round(round(x / TICK) * TICK, 6)
    tape = S.load_tape(d, root)
    ts, px = tape.ts, tape.px
    flat = S.day_flat(d, root)
    hi = int(np.searchsorted(ts, S.et_ns(d, "13:15" if flat != "15:58" else "16:10"), "left"))
    ifl = min(int(np.searchsorted(ts, S.et_ns(d, flat), "left")), hi)
    out = []
    for t in trades:
        side = 1 if t["side"] == "long" else -1
        stop_px = float(t["order_price"])
        a = int(np.searchsorted(ts, int(t["entry_ms"]) * MS, "left")); b = int(np.searchsorted(ts, (int(t["entry_ms"]) + 1) * MS, "left"))
        ks = [k for k in range(a, b) if side * (px[k] - stop_px) >= -1e-9 and abs(tt((max(stop_px, px[k]) if side > 0 else min(stop_px, px[k])) + side * TICK) - t["entry_price"]) < 1e-6]
        if not ks:
            out.append(None); continue
        k = ks[0]
        dsl, dtp = abs(t["entry_price"] - t["sl"]), abs(t["tp"] - t["entry_price"])
        r = {}
        for L in (0, 1, 5, 25):
            kf = k if not L else min(int(np.searchsorted(ts, ts[k] + L * MS, "left")), hi - 1)
            p = float(px[kf])
            fill = tt((max(stop_px, p) + TICK) if side > 0 else (min(stop_px, p) - TICK))
            sl, tp = tt(fill - side * dsl), tt(fill + side * dtp)
            seg = px[kf + 1:max(ifl, kf + 1)]
            if side > 0:
                hs, ht = np.flatnonzero(seg <= sl + 1e-9), np.flatnonzero(seg >= tp + TICK - 1e-9)
            else:
                hs, ht = np.flatnonzero(seg >= sl - 1e-9), np.flatnonzero(seg <= tp - TICK + 1e-9)
            i_sl = kf + 1 + int(hs[0]) if len(hs) else None; i_tp = kf + 1 + int(ht[0]) if len(ht) else None
            if i_sl is not None and (i_tp is None or i_sl <= i_tp):
                q = float(px[i_sl]); ex = tt((min(sl, q) - TICK) if side > 0 else (max(sl, q) + TICK)); kx = i_sl
            elif i_tp is not None:
                ex, kx = tp, i_tp
            else:
                kx = max(min(ifl, hi - 1), kf); ex = tt(float(px[kx]) - side * TICK)
            path = px[kf:kx + 1]
            mae = max(0.0, (fill - float(min(path.min(), ex))) if side > 0 else (float(max(path.max(), ex)) - fill))
            r[L] = {"net": side * (ex - fill) * PV - 4.0, "mae_usd": mae * PV}
        out.append(r)
    return iso, out


def orb_probe(pool):
    rep = {}
    t5 = []
    for per in ("build", "pick"):
        tr = json.loads((W / "members/orb_NQ_tf1_pre" / f"trades_{per}.json").read_text())
        assert max(t["date"] for t in tr) < "2025-01-01"
        by = {}
        for t in tr: by.setdefault(t["date"], []).append(t)
        res = dict(pool.imap_unordered(orb_day, [("NQ", d, v) for d, v in sorted(by.items())], chunksize=8))
        stored = sum(t["net"] for t in tr); n_ok = ident = 0; add = {1: 0.0, 5: 0.0, 25: 0.0}
        for d, v in by.items():
            for t, r in zip(v, res[d]):
                if r is None:
                    t5.append({"date": t["date"], "gross": t["gross"], "mae_usd": t["mae_usd"]}); continue
                n_ok += 1; ident += abs(r[0]["net"] - t["net"]) < 0.01
                for L in add: add[L] += r[L]["net"] - r[0]["net"]
                t5.append({"date": t["date"], "gross": t["net"] + (r[5]["net"] - r[0]["net"]) + 4.0, "mae_usd": r[5]["mae_usd"]})
        rep[per] = {"trades": len(tr), "replayed": n_ok, "identical_at_0ms": ident, "stored_net": round(stored, 2), **{f"{L}ms": round(stored + add[L], 2) for L in add},
                    "max_trades_a_day": max(len(v) for v in by.values())}
        print("orb probe", per, rep[per], flush=True)
    return rep, t5


RULES = {"lucid": dict(target=3000, mll=2000, lock_at=2100, lock_floor=100, min_days=2, cons=0.5, cap=40),
         "apex": dict(target=3000, mll=2000, lock_at=2100, lock_floor=100, min_days=1, cons=None, cap=100)}
cost = lambda n: (n // 10) * 4.0 + (n % 10) * 1.0


def walk(trades, cal, firm, n, H, before=None):
    r = RULES[firm]
    idx = {d: i for i, d in enumerate(cal)}
    pnl, wst, trd = np.zeros(len(cal)), np.zeros(len(cal)), np.zeros(len(cal), bool)
    seen = set()
    for t in trades:
        assert t["date"] not in seen, "more than one trade a day"; seen.add(t["date"])
        c = cost(n); p = n * t["gross"] / 10.0 - c; i = idx[t["date"]]
        pnl[i], wst[i], trd[i] = p, min(p, -t["mae_usd"] * n / 10.0 - c), True
    P = len(cal) - H + 1
    res = np.zeros(P, np.int8)
    for s in range(P):
        profit = peak = largest = 0.0; floor, td = -float(r["mll"]), 0
        for k in range(s, s + H):
            new = profit + pnl[k]
            if new <= floor or profit + wst[k] <= floor:
                res[s] = 2; break
            profit = new; td += int(trd[k]); largest = max(largest, pnl[k]); peak = max(peak, new)
            floor = float(r["lock_floor"]) if peak >= r["lock_at"] else peak - r["mll"]
            if new >= r["target"] and td >= r["min_days"] and (r["cons"] is None or largest <= r["cons"] * new):
                res[s] = 1; break
    out = {"p": float((res == 1).mean()), "bust": float((res == 2).mean()), "starts": P}
    if before is not None:
        sel = np.array([s + 1 < len(cal) and cal[s + 1] in before for s in range(P)])
        out.update(p_before=float((res[sel] == 1).mean()), starts_before=int(sel.sum()))
    return out


def main():
    with get_context("spawn").Pool(8) as pool:
        orb_rep, orb5 = orb_probe(pool)
    theirs = json.loads((W / "out/events/odds.json").read_text())
    rep = {"orb_probe": orb_rep, "odds": {}}
    jobs = [("straddle_tight_0830_GC_tf30_pre_evA", "GC", "A"), ("straddle_tight_0830_NQ_tf30_pre_evB", "NQ", "B"),
            ("straddle_tight_1000_GC_tf30_nyam_evC", "GC", "C"), ("orb_NQ_tf1_pre", "NQ", None)]
    for name, root, g in jobs:
        d = W / "members" / name
        base = json.loads((d / "trades_build.json").read_text()) + json.loads((d / "trades_pick.json").read_text())
        if g:
            five = [t for per in ("build", "pick") for t in json.loads((OUT / f"own5_{name}_{per}.json").read_text()) if t["date"] in G[g]]
            five = [{"date": t["date"], "gross": t["net"] + 4.0, "mae_usd": t["mae_usd"]} for t in five]
            mine0 = {t["date"]: t for per in ("build", "pick") for t in json.loads((OUT / f"own_{name}_{per}.json").read_text()) if t["date"] in G[g]}
            dm = [abs(mine0[t["date"]]["mae_usd"] - t["mae_usd"]) for t in base]
            print(name, "my base MAE vs member file MAE: max abs diff $", max(dm), "| trades", len(base), len(five))
        else:
            five = orb5
        cal = [x.isoformat() for x in S.sessions(S.BUILD[0], S.PICK[1], root)]
        assert cal[-1] <= "2024-12-31"
        pvm = S.SPECS[root][0] / 10.0
        stop = float(np.median([abs(t["entry_price"] - t["sl"]) for t in base]))
        m1000 = int(round(1000.0 / (stop * pvm)))
        rep["odds"][name] = {"median_stop_pts": stop, "micros_1000_uncut": m1000, "rows": []}
        print(f"{name}: median stop {stop} pts x ${pvm:g} a point per micro -> {m1000} micros for $1,000 (uncut); sessions {len(cal)}")
        for firm, label in (("lucid", "Lucid Flex 50K"), ("apex", "Apex 50K")):
            n = min(RULES[firm]["cap"], m1000)
            for fill, tr in (("BASE", base), ("5MS", five)):
                w = walk(tr, cal, firm, n, 10, G["B"])
                th = [x for x in theirs[name]["rows"] if x["account"] == label and x["fill"] == fill and x["size"] == "R1000"][0]
                row = {"account": label, "fill": fill, "micros": n, "their_micros": th["micros"], "net_1c": round(sum(t["gross"] - 4.0 for t in tr), 2), "their_net_1c": th["net_1c"],
                       "my_p10": round(w["p"], 4), "their_p10": round(th["eval_p10"], 4), "my_before": round(w["p_before"], 4), "their_before": round(th["eval_p10_before_tier1"], 4),
                       "my_bust": round(w["bust"], 4), "their_bust": round(th["eval_bust10"], 4), "starts": w["starts"], "starts_before": w["starts_before"]}
                rep["odds"][name]["rows"].append(row)
                print("  ", row, flush=True)
    (OUT / "chk_odds.json").write_text(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()

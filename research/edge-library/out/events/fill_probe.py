"""STAGE 3 FILL REALISM (information; reported on every card, not a gate): where does a TRIGGERED stop entry fill?
Engine law = on the trigger print (+ 1 tick). Here the entry fills at the first print >= L ms after the trigger print
(L = 1 / 5 / 25), the exits are replayed from that fill with the same stop and target DISTANCES, flat at the day's flat time.
Two readings (as out/check_r1/sens_fill.py):
  floor    the fill is never better than the stop price (the checker's headline convention: its "$4,869 -> $729")
  neutral  the fill is that later print + 1 tick (it may be better than the stop price)
Works on stored full trade records (order_price = the stop price, entry_ms, sl, tp): the trade list stays fixed, each trade is
re-priced on the tape. net(L) = the stored net + [replay(L) - replay(0)]; `ident` = share of trades whose replay(0) equals the
stored net to the cent. FILL-FRAGILE = the floor net at 5 ms is negative on BUILD or on 2024. BUILD + 2024 only (EXAM sealed).
  python out/events/fill_probe.py -> out/events/fill_probe.json"""
import datetime as dt
import json
import sys
from multiprocessing import get_context
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
W = HERE.parents[1]
sys.path.insert(0, str(W))
sys.path.insert(0, str(W / "engine"))
sys.path.insert(0, str(HERE))
import l2sim as S  # noqa: E402

MS = 1_000_000
LAGS = (0, 1, 5, 25)
COMM = 4.0


def day(args):
    root, iso, trades = args
    d = dt.date.fromisoformat(iso)
    S.check_holdout(d, False)                                     # EXAM stays sealed
    pv, tick = S.SPECS[root]
    tape = S.load_tape(d, root)
    out = []
    if tape is None or not len(tape.ts):
        return [(t["_i"], None) for t in trades]
    ts, px = tape.ts, tape.px
    n = len(ts)

    def tt(x):
        return round(round(x / tick) * tick, 6)

    for t in trades:
        side = 1 if t["side"] == "long" else -1
        stop_px, ent = float(t["order_price"]), float(t["entry_price"])
        t0 = int(t["entry_ms"]) * MS
        a, b = int(np.searchsorted(ts, t0 - MS, "left")), int(np.searchsorted(ts, t0 + 2 * MS, "left"))
        cross = [k for k in range(a, b) if side * (px[k] - stop_px) >= -1e-9]
        exact = [k for k in cross if abs(tt((max(stop_px, px[k]) if side > 0 else min(stop_px, px[k])) + side * tick) - ent) < 1e-6]
        if not cross:
            out.append((t["_i"], None))
            continue
        k = exact[0] if exact else cross[0]
        d_sl = abs(ent - float(t["sl"])) if t.get("sl") is not None else None
        d_tp = abs(float(t["tp"]) - ent) if t.get("tp") is not None else None
        d2 = dt.date.fromisoformat(t["date"])
        ifl = min(int(np.searchsorted(ts, S.et_ns(d2, S.day_flat(d2, root)), "left")), n - 1)
        res = {"same_ts": int(np.searchsorted(ts, ts[k], "right")) - k, "exact": bool(exact)}
        for L in LAGS:
            kf = k if not L else min(int(np.searchsorted(ts, ts[k] + L * MS, "left")), n - 1)
            p = float(px[kf])
            for mode in ("floor", "neutral"):
                if mode == "neutral" and L:
                    fill = tt(p + side * tick)
                else:
                    fill = tt((max(stop_px, p) + tick) if side > 0 else (min(stop_px, p) - tick))
                sg = px[kf + 1:max(ifl, kf + 1)]
                i_sl = i_tp = None
                if d_sl is not None:
                    sl = tt(fill - side * d_sl)
                    h = np.flatnonzero(sg <= sl + 1e-9) if side > 0 else np.flatnonzero(sg >= sl - 1e-9)
                    i_sl = kf + 1 + int(h[0]) if len(h) else None
                if d_tp is not None:
                    tp = tt(fill + side * d_tp)
                    h = np.flatnonzero(sg >= tp + tick - 1e-9) if side > 0 else np.flatnonzero(sg <= tp - tick + 1e-9)
                    i_tp = kf + 1 + int(h[0]) if len(h) else None
                if i_sl is not None and (i_tp is None or i_sl <= i_tp):
                    q = float(px[i_sl])
                    ex, ie, why = tt((min(sl, q) - tick) if side > 0 else (max(sl, q) + tick)), i_sl, "sl"
                elif i_tp is not None:
                    ex, ie, why = tp, i_tp, "tp"
                else:
                    ie = max(ifl, kf)
                    ex, why = tt(float(px[ie]) - side * tick), "eod"
                if mode == "floor" and L == 5:                    # the re-priced trade record (the 5 ms fill model of the odds)
                    path = np.append(px[kf:ie + 1], ex)
                    adv = max(0.0, float((side * (fill - path)).max()))
                    fav = max(0.0, float((side * (path - fill)).max()))
                    res["t5"] = {"entry_price": fill, "exit_price": ex, "exit_reason": why, "entry_ms": int(ts[kf] // MS),
                                 "exit_ms": int(ts[ie] // MS), "sl": None if d_sl is None else sl, "tp": None if d_tp is None else tp,
                                 "mae_pts": round(adv, 6), "mfe_pts": round(fav, 6), "mae_usd": round(adv * pv, 2),
                                 "mfe_usd": round(fav * pv, 2), "gross": round(side * (ex - fill) * pv, 2)}
                res[f"{mode}|{L}"] = side * (ex - fill) * pv - COMM
                if mode == "floor":
                    res[f"slip|{L}"] = side * (fill - stop_px)
        out.append((t["_i"], res))
    return out


def probe(root: str, trades: list, pool) -> dict:
    assert all(t["date"] < "2025-01-01" for t in trades)
    for i, t in enumerate(trades):
        t["_i"] = i
    by: dict = {}
    for t in trades:                                              # the tape file of the entry's calendar day (ET)
        by.setdefault(t["date"], []).append(t)
    res = {}
    for chunk in pool.imap_unordered(day, [(root, d, ts_) for d, ts_ in sorted(by.items())], chunksize=4):
        res.update({i: r for i, r in chunk})
    ok = [i for i in range(len(trades)) if res.get(i) is not None]
    stored = float(sum(t["net"] for t in trades))
    out = {"trades": len(trades), "replayed": len(ok), "stored_net": round(stored, 2),
           "ident": round(float(np.mean([abs(res[i]["floor|0"] - trades[i]["net"]) < 0.01 for i in ok])), 4) if ok else None,
           "exact_trigger": round(float(np.mean([res[i]["exact"] for i in ok])), 4) if ok else None}
    for mode in ("floor", "neutral"):
        out[mode] = {f"{L}ms": round(stored + sum(res[i][f"{mode}|{L}"] - res[i][f"{mode}|0"] for i in ok), 2) for L in LAGS}
    out["mean_slip_pts"] = {f"{L}ms": round(float(np.mean([res[i][f"slip|{L}"] for i in ok])), 3) for L in LAGS} if ok else {}
    out["median_slip_pts"] = {f"{L}ms": round(float(np.median([res[i][f"slip|{L}"] for i in ok])), 3) for L in LAGS} if ok else {}
    out["median_prints_sharing_trigger_ts"] = float(np.median([res[i]["same_ts"] for i in ok])) if ok else None
    t5 = []
    for i, t in enumerate(trades):                                # trades re-priced at 5 ms (floor); a trade not replayed keeps its record
        x = {k: v for k, v in t.items() if k != "_i"}
        if res.get(i) is not None:
            x.update(res[i]["t5"])
            x["net"] = round(x["gross"] - float(x.get("commission") or COMM), 2)
        t5.append(x)
    out["_t5"] = t5
    return out


def main():
    import ev as E
    jobs = []
    adm = json.loads((HERE / "admission.json").read_text())
    bu = {r["uid"]: r for r in json.loads((HERE / "build_units.json").read_text()) if r["pass"]}
    for uid, r in bu.items():
        fam, root, sess, cm, g = r["family"], r["root"], r["sess"], r["central"], r["group"]
        tr = {}
        for per in ("build", "pick"):
            p = HERE / "member_runs" / f"{fam}_{root}_tf30_{sess}-{cm}-{per}.json"
            if not p.exists():
                continue
            tr[per] = [t for t in json.loads(p.read_text())["trades"] if t["date"] in E.days(g)]
        jobs.append((uid, adm.get(uid, {}).get("name", uid), root, tr))
    d = W / "members" / "orb_NQ_tf1_pre"
    jobs.append(("orb_NQ_tf1_pre", "orb_NQ_tf1_pre", "NQ", {per: json.loads((d / f"trades_{per}.json").read_text()) for per in ("build", "pick")}))
    rep = {}
    with get_context("spawn").Pool(8) as pool:
        for uid, name, root, tr in jobs:
            rep[uid] = {"name": name, "root": root}
            for per, trades in tr.items():
                rep[uid][per] = probe(root, trades, pool)
                t5 = rep[uid][per].pop("_t5")
                assert abs(sum(x["net"] for x in t5) - rep[uid][per]["floor"]["5ms"]) < 0.5 or rep[uid][per]["ident"] < 1.0
                (HERE / "member_runs" / f"fill5-{name}-{per}.json").write_text(json.dumps(t5, separators=(",", ":")))
            f5 = [rep[uid][per]["floor"]["5ms"] for per in tr]
            rep[uid]["fill_fragile"] = bool(any(v < 0 for v in f5))
            print(uid, json.dumps(rep[uid]), flush=True)
    (HERE / "fill_probe.json").write_text(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()

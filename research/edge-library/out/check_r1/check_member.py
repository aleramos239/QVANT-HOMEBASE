"""CHECKER (stage 2b) -- the admitted member straddle_tight_0830 NQ offB_pts5-r3, recomputed two ways:
  A. the engine from scratch (l2sim.run on the member's inputs; nothing goes to the ledger), base and 2 ticks + 250 ms;
  B. MY OWN tick replay of the written rule (no engine order code): bracket at 08:29:59 around the last print, live 85 ms
     later, OCO, cancel after 5 min, stop 5 pts, target 15 pts, flat 15:58 (13:13 half days), 1 tick slip, $4 round turn.
Both are compared trade for trade with members/<name>/trades_{build,pick}.json and with the unit stores.
Extra (information for the confirm / demote call): what the net becomes when a TRIGGERED stop fills L ms after its trigger
print instead of on it (the written 250 ms stress only delays the PLACEMENT, and the bracket rests 1 s before the event).
2024 is read only for this cell (already read by the analyst). EXAM never."""
import datetime as dt
import json
import sys
from multiprocessing import get_context
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(W))
sys.path.insert(0, str(W / "engine"))
import l2sim as S  # noqa: E402
import families  # noqa: E402

OUT = Path(__file__).resolve().parent
NAME = "straddle_tight_0830_NQ_tf30_pre"
MS = 1_000_000
PV, TICK = 20.0, 0.25
OFF, STOP, TGT = 5.0, 5.0, 15.0


def tt(x):
    return round(round(x / TICK) * TICK, 6)


def own_day(args):
    """My own replay of one day. -> list of variants {key: trade | None}; key = (slip_ticks, place_ms, trig_ms)."""
    iso, variants = args
    d = dt.date.fromisoformat(iso)
    S.check_holdout(d, False)                       # EXAM stays sealed
    tape = S.load_tape(d, "NQ")
    if tape is None or not len(tape.ts):
        return iso, None
    half = S.day_flat(d, "NQ") != "15:58"
    w_end = "13:15" if half else "16:10"
    ts, px = tape.ts, tape.px
    t_arm = S.et_ns(d, "08:29:59")
    t_cancel = t_arm + 300 * 1_000_000_000
    t_flat = S.et_ns(d, S.day_flat(d, "NQ"))
    lo = int(np.searchsorted(ts, S.et_ns(d, "00:00"), "left"))
    hi = int(np.searchsorted(ts, S.et_ns(d, w_end), "left"))
    ia = int(np.searchsorted(ts, t_arm, "left"))
    out = {}
    if ia <= lo or ia >= hi:
        return iso, {k: None for k in variants}
    lp = float(px[ia - 1])
    up, dn = tt(lp + OFF), tt(lp - OFF)
    ic = int(np.searchsorted(ts, t_cancel, "left"))
    ifl = min(int(np.searchsorted(ts, t_flat, "left")), hi)
    for slip_t, place_ms, trig_ms in variants:
        slip = slip_t * TICK
        a = int(np.searchsorted(ts, t_arm + place_ms * MS, "left"))
        seg = px[a:min(ic, hi)]
        hit = np.flatnonzero((seg >= up - 1e-9) | (seg <= dn + 1e-9))
        if not len(hit):
            out[(slip_t, place_ms, trig_ms)] = None
            continue
        k = a + int(hit[0])
        side = 1 if px[k] >= up - 1e-9 else -1
        stop_px = up if side > 0 else dn
        kf = k if not trig_ms else int(np.searchsorted(ts, ts[k] + trig_ms * MS, "left"))
        if kf >= hi:
            out[(slip_t, place_ms, trig_ms)] = None
            continue
        p = float(px[kf])
        fill = tt((max(stop_px, p) + slip) if side > 0 else (min(stop_px, p) - slip))
        sl, tp = tt(fill - side * STOP), tt(fill + side * TGT)
        # exits from the print after the fill print
        b = kf + 1
        seg = px[b:ifl]
        if side > 0:
            h_sl = np.flatnonzero(seg <= sl + 1e-9)
            h_tp = np.flatnonzero(seg >= tp + TICK - 1e-9)
        else:
            h_sl = np.flatnonzero(seg >= sl - 1e-9)
            h_tp = np.flatnonzero(seg <= tp - TICK + 1e-9)
        i_sl = b + int(h_sl[0]) if len(h_sl) else None
        i_tp = b + int(h_tp[0]) if len(h_tp) else None
        if i_sl is not None and (i_tp is None or i_sl <= i_tp):
            ke = i_sl if not trig_ms else min(int(np.searchsorted(ts, ts[i_sl] + trig_ms * MS, "left")), hi - 1)
            q = float(px[ke])
            ex = tt((min(sl, q) - slip) if side > 0 else (max(sl, q) + slip))
            why, kx = "sl", ke
        elif i_tp is not None:
            ex, why, kx = tp, "tp", i_tp
        else:
            kx = ifl if ifl < hi else hi - 1
            ex, why = tt(float(px[kx]) - side * slip), "time"
        net = side * (ex - fill) * PV - 4.0
        mae = max(0.0, (fill - float(px[kf:kx + 1].min())) if side > 0 else (float(px[kf:kx + 1].max()) - fill))
        out[(slip_t, place_ms, trig_ms)] = {"date": iso, "side": side, "entry_ms": int(ts[kf]) // MS, "exit_ms": int(ts[kx]) // MS,
                                            "entry": fill, "exit": ex, "why": why, "net": round(net, 2), "anchor": lp,
                                            "dur_s": (int(ts[kx]) - int(ts[kf])) / 1e9, "mae_usd": round(mae * PV, 2)}
    return iso, out


def engine(period, stress):
    cls = families.REGISTRY["straddle_tight_0830"][0]
    spec = json.loads((W / "members" / NAME / "spec.json").read_text())
    params = dict(spec["inputs"])
    kw = dict(S.STRESS) if stress else {}
    res = S.run(cls, params, period=period, root="NQ", workers=8, **kw)
    return res


def cmp(mine, eng, label):
    a = {t["date"]: t for t in mine}
    b = {t["date"]: t for t in eng}
    only_a, only_b = sorted(set(a) - set(b)), sorted(set(b) - set(a))
    diff = []
    for d in sorted(set(a) & set(b)):
        x, y = a[d], b[d]
        ys = 1 if y["side"] in ("long", 1) else -1
        ye = y.get("entry_price", y.get("entry"))
        if x["side"] != ys or x["entry_ms"] != y["entry_ms"] or abs(x["net"] - y["net"]) > 0.005 or abs(x["entry"] - ye) > 1e-9:
            diff.append((d, x["side"], ys, x["entry_ms"], y["entry_ms"], x["net"], y["net"]))
    print(f"  {label}: mine {len(a)} trades net {sum(t['net'] for t in mine):.2f} | other {len(b)} trades net "
          f"{sum(t['net'] for t in eng):.2f} | only mine {len(only_a)} only other {len(only_b)} | differing {len(diff)}")
    for r in diff[:6]:
        print("     diff", r)
    if only_a[:5] or only_b[:5]:
        print("     only mine", only_a[:8], "only other", only_b[:8])
    return {"mine": len(a), "other": len(b), "only_mine": only_a, "only_other": only_b, "differing": len(diff)}


def main():
    report = {}
    variants = [(1.0, 85, 0), (2.0, 250, 0), (1.0, 85, 25), (1.0, 85, 50), (1.0, 85, 100), (1.0, 85, 250), (1.0, 85, 500),
                (2.0, 85, 100)]
    for period in ("build", "pick"):
        a, b = S.period(period)
        days = [d.isoformat() for d in S.sessions(a, b, "NQ")]
        assert days[-1] < "2025-01-01"
        print(f"== {period}: {days[0]} .. {days[-1]} ({len(days)} sessions)", flush=True)
        with get_context("spawn").Pool(8) as pool:
            res = dict(pool.imap_unordered(own_day, [(d, variants) for d in days], chunksize=8))
        base_e = engine(period, False)
        str_e = engine(period, True)
        skipped = {s["date"] for s in base_e["skipped"]}
        print("  engine range", base_e["meta"]["range"], "sessions", base_e["sessions"], "used", base_e["used"],
              "skipped", sorted(skipped))
        own = {v: [r[v] for d, r in sorted(res.items()) if r is not None and r.get(v) is not None and d not in skipped]
               for v in variants}
        own_sk = [d for d, r in sorted(res.items()) if d in skipped and r is not None and r.get(variants[0]) is not None]
        member = json.loads((W / "members" / NAME / f"trades_{period}.json").read_text())
        rep = {"sessions": len(days), "engine_skipped": sorted(skipped), "own_trades_on_skipped_days": own_sk}
        rep["engine_vs_member_file"] = cmp([{"date": t["date"], "side": 1 if t["side"] == "long" else -1, "entry_ms": t["entry_ms"],
                                             "net": t["net"], "entry": t["entry_price"]} for t in base_e["trades"]], member,
                                           "engine re-run vs member file")
        rep["own_vs_engine_base"] = cmp(own[variants[0]], base_e["trades"], "OWN replay vs engine re-run (base)")
        rep["own_vs_engine_stress"] = cmp(own[variants[1]], str_e["trades"], "OWN replay vs engine re-run (2 ticks + 250 ms)")
        # the bracket anchor of every engine trade = the last print before 08:29:59.000 (own replay's anchor)
        anc = {t["date"]: t["anchor"] for t in own[variants[0]]}
        bad = [t["date"] for t in base_e["trades"]
               if abs(t["order_price"] - (1 if t["side"] == "long" else -1) * OFF - anc.get(t["date"], 1e18)) > 1e-9]
        early = [t["date"] for t in base_e["trades"]
                 if t["entry_ms"] * MS < S.et_ns(dt.date.fromisoformat(t["date"]), "08:29:59") + 85 * MS - MS]
        late = [t["date"] for t in base_e["trades"]
                if t["entry_ms"] * MS >= S.et_ns(dt.date.fromisoformat(t["date"]), "08:29:59") + 300 * 1_000_000_000]
        print(f"  anchor != last print before 08:29:59: {len(bad)} | fills before the order is live: {len(early)} | fills after the "
              f"5-min cancel: {len(late)}")
        rep.update(anchor_bad=bad, fill_early=early, fill_late=late)
        tr = own[variants[0]]
        by_year = {}
        for t in tr:
            by_year.setdefault(t["date"][:4], []).append(t["net"])
        rep["own_per_year"] = {y: {"trades": len(v), "net": round(sum(v), 2)} for y, v in sorted(by_year.items())}
        net = np.array([t["net"] for t in tr])
        rep["own_base"] = {"trades": len(tr), "net": round(float(net.sum()), 2),
                           "t": float(net.mean() / (net.std(ddof=1) / np.sqrt(len(net)))),
                           "pf": float(net[net > 0].sum() / -net[net < 0].sum()), "win": float((net > 0).mean()),
                           "worst_open_loss": max(t["mae_usd"] for t in tr)}
        fast = [t for t in tr if t["dur_s"] <= 2.0]
        rep["own_fast_le_2s"] = {"trades": len(fast), "net": round(sum(t["net"] for t in fast), 2),
                                 "rest_trades": len(tr) - len(fast), "rest_net": round(sum(t["net"] for t in tr if t["dur_s"] > 2.0), 2)}
        rep["engine_stress_net"] = round(sum(t["net"] for t in str_e["trades"]), 2)
        rep["engine_base_net"] = round(sum(t["net"] for t in base_e["trades"]), 2)
        rep["sens"] = {}
        for v in variants:
            n = np.array([t["net"] for t in own[v]])
            rep["sens"][f"slip{v[0]:g}t_place{v[1]}ms_trig{v[2]}ms"] = {"trades": len(n), "net": round(float(n.sum()), 2)}
        print("  per year", rep["own_per_year"])
        print("  base", rep["own_base"])
        print("  <= 2 s", rep["own_fast_le_2s"])
        for k, v in rep["sens"].items():
            print("  sens", k, v)
        # entry second after 08:30:00 distribution of the money
        e0 = {t["date"]: (t["entry_ms"] * MS - S.et_ns(dt.date.fromisoformat(t["date"]), "08:30")) / 1e9 for t in tr}
        bands = [(-1.0, 0.0), (0.0, 1.0), (1.0, 5.0), (5.0, 60.0), (60.0, 301.0)]
        rep["by_entry_time"] = {}
        for lo_, hi_ in bands:
            sel = [t for t in tr if lo_ <= e0[t["date"]] < hi_]
            rep["by_entry_time"][f"{lo_:g}..{hi_:g}s"] = {"trades": len(sel), "net": round(sum(t["net"] for t in sel), 2)}
        print("  by entry time vs 08:30:00", rep["by_entry_time"])
        report[period] = rep
        (OUT / f"own_trades_{period}.json").write_text(json.dumps(tr))
    (OUT / "check_member.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()

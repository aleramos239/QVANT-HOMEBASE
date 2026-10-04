"""CHECKER (stage 2b) -- INFORMATION ONLY (not a gate, no rule added): how the admitted member's net depends on WHERE a
triggered stop entry fills. Engine law = on the trigger print (+ 1 tick). Here the entry fills at the first print L ms
after the trigger print; three readings:
  entry_neutral   entry only delayed, fill = that print + 1 tick (may be better than the stop price), exits as the engine
  entry_floor     entry only delayed, fill never better than the stop price (engine convention max / min)
  both_floor      entry and the protective stop both delayed, floor convention
Own tick replay (check_member.own_day's rules). BUILD + 2024, this one cell only."""
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

MS = 1_000_000
PV, TICK = 20.0, 0.25
OFF, STOP, TGT = 5.0, 5.0, 15.0
LAGS = (0, 1, 2, 5, 10, 25, 50, 100)
MODES = ("entry_neutral", "entry_floor", "both_floor")


def tt(x):
    return round(round(x / TICK) * TICK, 6)


def day(iso):
    d = dt.date.fromisoformat(iso)
    S.check_holdout(d, False)
    tape = S.load_tape(d, "NQ")
    if tape is None or not len(tape.ts):
        return iso, None
    w_end = "13:15" if S.day_flat(d, "NQ") != "15:58" else "16:10"
    ts, px = tape.ts, tape.px
    t_arm = S.et_ns(d, "08:29:59")
    lo = int(np.searchsorted(ts, S.et_ns(d, "00:00"), "left"))
    hi = int(np.searchsorted(ts, S.et_ns(d, w_end), "left"))
    ia = int(np.searchsorted(ts, t_arm, "left"))
    if ia <= lo or ia >= hi:
        return iso, None
    lp = float(px[ia - 1])
    up, dn = tt(lp + OFF), tt(lp - OFF)
    ic = min(int(np.searchsorted(ts, t_arm + 300 * 1_000_000_000, "left")), hi)
    ifl = min(int(np.searchsorted(ts, S.et_ns(d, S.day_flat(d, "NQ")), "left")), hi)
    a = int(np.searchsorted(ts, t_arm + 85 * MS, "left"))
    seg = px[a:ic]
    hit = np.flatnonzero((seg >= up - 1e-9) | (seg <= dn + 1e-9))
    if not len(hit):
        return iso, None
    k = a + int(hit[0])
    side = 1 if px[k] >= up - 1e-9 else -1
    stop_px = up if side > 0 else dn
    same_ts = int(np.searchsorted(ts, ts[k], "right")) - k          # prints sharing the trigger print's timestamp (from it on)
    out = {"same_ts": same_ts, "trig_s": (int(ts[k]) - S.et_ns(d, "08:30")) / 1e9}
    for L in LAGS:
        kf = k if not L else int(np.searchsorted(ts, ts[k] + L * MS, "left"))
        if kf >= hi:
            continue
        p = float(px[kf])
        for mode in MODES:
            if mode == "entry_neutral" and L:
                fill = tt(p + side * TICK)
            else:
                fill = tt((max(stop_px, p) + TICK) if side > 0 else (min(stop_px, p) - TICK))
            sl, tp = tt(fill - side * STOP), tt(fill + side * TGT)
            b = kf + 1
            sg = px[b:ifl]
            if side > 0:
                h_sl, h_tp = np.flatnonzero(sg <= sl + 1e-9), np.flatnonzero(sg >= tp + TICK - 1e-9)
            else:
                h_sl, h_tp = np.flatnonzero(sg >= sl - 1e-9), np.flatnonzero(sg <= tp - TICK + 1e-9)
            i_sl = b + int(h_sl[0]) if len(h_sl) else None
            i_tp = b + int(h_tp[0]) if len(h_tp) else None
            if i_sl is not None and (i_tp is None or i_sl <= i_tp):
                ke = i_sl
                if mode == "both_floor" and L:
                    ke = min(int(np.searchsorted(ts, ts[i_sl] + L * MS, "left")), hi - 1)
                q = float(px[ke])
                ex = tt((min(sl, q) - TICK) if side > 0 else (max(sl, q) + TICK))
            elif i_tp is not None:
                ex = tp
            else:
                kx = ifl if ifl < hi else hi - 1
                ex = tt(float(px[kx]) - side * TICK)
            out[f"{mode}|{L}"] = side * (ex - fill) * PV - 4.0
            if mode == "entry_neutral":
                out[f"slip_pts|{L}"] = side * (fill - stop_px)          # how far past the stop price the entry filled
    return iso, out


def main():
    rep = {}
    for period in ("build", "pick"):
        a, b = S.period(period)
        days = [d.isoformat() for d in S.sessions(a, b, "NQ")]
        assert days[-1] < "2025-01-01"
        own = {t["date"] for t in json.loads((Path(__file__).with_name(f"own_trades_{period}.json")).read_text())}
        with get_context("spawn").Pool(8) as pool:
            res = {d: r for d, r in pool.imap_unordered(day, days, chunksize=8) if r is not None and d in own}
        r = {"trades": len(res)}
        for mode in MODES:
            r[mode] = {f"{L}ms": round(sum(x.get(f"{mode}|{L}", 0.0) for x in res.values()), 2) for L in LAGS}
        r["mean_entry_slip_pts"] = {f"{L}ms": round(float(np.mean([x[f"slip_pts|{L}"] for x in res.values() if f"slip_pts|{L}" in x])), 3)
                                    for L in LAGS}
        fast = [x for x in res.values() if 0 <= x["trig_s"] < 5]
        r["trigger_0_5s_after_0830"] = {"trades": len(fast),
                                        "mean_entry_slip_pts": {f"{L}ms": round(float(np.mean([x[f"slip_pts|{L}"] for x in fast])), 3)
                                                                for L in LAGS},
                                        "median_prints_sharing_trigger_ts": float(np.median([x["same_ts"] for x in fast]))}
        rep[period] = r
        print(period, json.dumps(r, indent=1), flush=True)
    Path(__file__).with_name("sens_fill.json").write_text(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()

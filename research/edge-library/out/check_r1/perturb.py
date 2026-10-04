"""CHECKER (stage 2b) -- look-ahead perturbation test on REAL BUILD tapes, own code.
For one family cell and a seeded sample of BUILD dates:
  1. run the day on the real tape, take the FIRST trade (later trades of a day depend on earlier outcomes by rule);
  2. T_sig = the decision time of that trade (bar families: the minute boundary at / before entry - 85 ms; late_mom 15:30:00;
     straddle_tight: the clock time - 1 s);
  3. rewrite every print with ts >= T_sig (three ways: mirror around the last earlier price, +0.6 % jump, -0.6 % jump; sizes
     reversed) and run again: the first trade must keep its side and its entry print (market) / its bracket anchor (straddle);
  4. POWER control: the same rewrite started one tf bar EARLIER (the signal bar itself is altered) must change decisions often.
BUILD dates only (2021-09-22 .. 2023-12-29). Nothing is written but out/check_r1/perturb.json."""
import datetime as dt
import json
import random
import sys
from bisect import bisect_left
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(W))
sys.path.insert(0, str(W / "engine"))
import l2sim as S  # noqa: E402
import families  # noqa: E402

NS = 1_000_000_000
LAT = 85_000_000
_D = {}


def daily_of(root):
    if root not in _D:
        d = S.with_eve_atr(S.load_daily(root), root)
        _D[root] = (d, [r["date"] for r in d], S.rolls(d))
    return _D[root]


def run_day(cls, params, root, tape):
    daily, dates, roll = daily_of(root)
    iso = tape.date.isoformat()
    st = cls(dict(params))
    st.ROLLS = roll
    st.root = root
    if getattr(st, "begin_day", None):
        st.begin_day(tape.date)
    i = bisect_left(dates, iso)
    prior = daily[:i]
    c_day = daily[i].get("atr30e") if i < len(daily) and dates[i] == iso and getattr(st, "ATR_CARRY", False) else None
    window = S.effective_session_window(tape.date, tuple(st.session_window), root)
    if S.missing_hours(tape.ts, tape.date, window):
        return None, st
    res = S.run_session(st, tape, S.Costs(), qty=1, daily=prior, window=window, on_error="raise", carry=c_day)
    return res.trades, st


def rewrite(tape, t_cut, how):
    ts = tape.ts
    k = int(np.searchsorted(ts, t_cut, side="left"))
    if k == 0 or k >= len(ts):
        return None
    px, sz = tape.px.copy(), tape.size.copy()
    p0 = px[k - 1]
    tick = S.SPECS[tape.root][1]
    if how == "mirror":
        px[k:] = 2 * p0 - px[k:]
    else:
        j = round(p0 * 0.006 / tick) * tick * (1 if how == "up" else -1)
        px[k:] = px[k:] + j
    sz[k:] = sz[k:][::-1]
    return S.Tape(tape.root, tape.date, tape.contract, ts, px, sz)


def first(trades):
    return min(trades, key=lambda t: t["entry_ns"]) if trades else None


def test(name, root, tf, sess, variant, exit_cell, n_days=24, seed=7, kind="bar"):
    cls = families.REGISTRY[name][0]
    params = {**families.unit_inputs(name, tf, sess), **variant, **exit_cell, "hold_to": "day"}
    days = [d.isoformat() for d in S.sessions(S.BUILD[0], S.BUILD[1], root)]
    assert days[-1] <= "2023-12-31"
    rnd = random.Random(seed)
    rnd.shuffle(days)
    out = {"name": name, "root": root, "tf": tf, "sess": sess, "variant": variant, "exit": exit_cell, "days": 0, "runs": 0,
           "moved": 0, "moved_detail": [], "power_runs": 0, "power_changed": 0}
    off = None
    for iso in days:
        if out["days"] >= n_days:
            break
        tape = S.load_tape(iso, root)
        if tape is None or not len(tape.ts):
            continue
        tr, st = run_day(cls, params, root, tape)
        f = first(tr)
        if f is None:
            continue
        d = dt.date.fromisoformat(iso)
        sd = 1 if f["side"] == "long" else -1
        if kind == "bar":
            t_sig = ((f["entry_ns"] - LAT) // (60 * NS)) * (60 * NS)
            # the event that sent the order is a minute boundary in ET; ET offsets are whole hours -> same floor
        elif kind == "late":
            t_sig = S.et_ns(d, "15:30")
        else:                                           # straddle_tight: the clock time minus 1 s
            t_sig = S.et_ns(d, params["at"])
            off = st.p["off_val"]
            k = int(np.searchsorted(tape.ts, t_sig, side="left"))
            lp = float(tape.px[k - 1])
            if abs((f["order_price"] - sd * off) - lp) > 1e-9:
                out["moved"] += 1
                out["moved_detail"].append({"date": iso, "why": "bracket anchor is not the last print before the arm time",
                                            "anchor": f["order_price"] - sd * off, "last_print": lp})
            if f["entry_ns"] < t_sig + LAT:
                out["moved"] += 1
                out["moved_detail"].append({"date": iso, "why": "fill before the order could be live"})
        if f["entry_ns"] < t_sig:
            out["moved_detail"].append({"date": iso, "why": "entry before t_sig?"})
            out["moved"] += 1
            continue
        out["days"] += 1
        for how in ("mirror", "up", "down"):
            t2 = rewrite(tape, t_sig, how)
            if t2 is None:
                continue
            tr2, st2 = run_day(cls, params, root, t2)
            g = first(tr2)
            out["runs"] += 1
            if kind == "straddle":
                ok = g is None or abs((g["order_price"] - (1 if g["side"] == "long" else -1) * off)
                                      - (f["order_price"] - sd * off)) < 1e-9
            else:
                ok = g is not None and g["side"] == f["side"] and g["entry_ns"] == f["entry_ns"]
            if not ok:
                out["moved"] += 1
                out["moved_detail"].append({"date": iso, "how": how, "orig": [f["side"], f["entry_ns"]],
                                            "new": None if g is None else [g["side"], g["entry_ns"]]})
        # POWER: start the rewrite one tf bar (bar families) / 1 minute (clock families) earlier
        back = int(tf) * 60 * NS if kind == "bar" else 60 * NS
        for how in ("mirror", "up", "down"):
            t3 = rewrite(tape, t_sig - back, how)
            if t3 is None:
                continue
            tr3, _ = run_day(cls, params, root, t3)
            g = first(tr3)
            out["power_runs"] += 1
            if kind == "straddle":
                ch = g is None or abs((g["order_price"] - (1 if g["side"] == "long" else -1) * off)
                                      - (f["order_price"] - sd * off)) > 1e-9
            else:
                ch = g is None or g["side"] != f["side"] or g["entry_ns"] != f["entry_ns"]
            out["power_changed"] += bool(ch)
    return out


TESTS = [
    ("vwap_trend_pull", "NQ", "5", "pm", {"x": 0.10}, {"stop_mode": "pts", "stop_val": 30.0, "tgt_r": 2.0}, "bar"),
    ("vwap_trend_pull", "NQ", "15", "mid", {"x": 0.05}, {"stop_mode": "atr", "stop_val": 1.5, "tgt_r": 1.0}, "bar"),
    ("va_reclaim", "NQ", "5", "nyam", {"d_atr": 0.25}, {"stop_mode": "pts", "stop_val": 20.0, "tgt_r": 2.0}, "bar"),
    ("va_reclaim", "GC", "15", "london", {"d_atr": 0.0}, {"stop_mode": "atr", "stop_val": 1.5, "tgt_r": 1.0}, "bar"),
    ("orb_confirm", "NQ", "5", "nyam", {"or_min": "15", "dir": "long"}, {"stop_mode": "pts", "stop_val": 20.0, "tgt_r": 2.0}, "bar"),
    ("orb_confirm", "NQ", "15", "mid", {"or_min": "60", "dir": "short"}, {"stop_mode": "pct", "stop_val": 0.2, "tgt_r": 0.0}, "bar"),
    ("late_mom", "NQ", "30", "all", {"sig": "15:30", "thr": 0.0}, {"stop_mode": "pts", "stop_val": 20.0, "tgt_r": 0.0}, "late"),
    ("late_mom", "ES", "30", "all", {"sig": "12:00", "thr": 0.25}, {"stop_mode": "atr", "stop_val": 1.5, "tgt_r": 1.0}, "late"),
    ("open_fade", "NQ", "1", "nyam", {"k": 1.0}, {"stop_mode": "pts", "stop_val": 20.0, "tgt_r": 1.0}, "bar"),
    ("open_fade", "NQ", "5", "nyam", {"k": 0.5}, {"stop_mode": "atr", "stop_val": 1.5, "tgt_r": 2.0}, "bar"),
    ("vol_spike_break", "NQ", "30", "pm", {"m": 4.0}, {"stop_mode": "pct", "stop_val": 0.2, "tgt_r": 2.0}, "bar"),
    ("vol_spike_break", "NQ", "5", "nyam", {"m": 2.0}, {"stop_mode": "pts", "stop_val": 20.0, "tgt_r": 2.0}, "bar"),
    ("straddle_tight_0830", "NQ", "30", "all", {"off": "B"}, {"stop_mode": "pts", "stop_val": 5.0, "tgt_r": 3.0}, "straddle"),
    ("straddle_tight_0930", "NQ", "30", "all", {"off": "A"}, {"stop_mode": "pts", "stop_val": 8.0, "tgt_r": 1.0}, "straddle"),
    ("straddle_tight_1000", "GC", "30", "all", {"off": "C"}, {"stop_mode": "pts", "stop_val": 1.6, "tgt_r": 2.0}, "straddle"),
]

if __name__ == "__main__":
    which = sys.argv[1:] or None
    res = []
    for t in TESTS:
        if which and t[0] not in which:
            continue
        r = test(t[0], t[1], t[2], t[3], t[4], t[5], kind=t[6])
        res.append(r)
        print(f"{r['name']:22s} {r['root']} tf{r['tf']:>2s} {r['sess']:6s} days {r['days']:3d} rewrites {r['runs']:3d} "
              f"MOVED {r['moved']:2d} | power: changed {r['power_changed']}/{r['power_runs']}", flush=True)
        for m in r["moved_detail"][:5]:
            print("     ", m, flush=True)
    p = Path(__file__).with_name("perturb.json")
    old = json.loads(p.read_text()) if p.exists() else []
    p.write_text(json.dumps(old + res, indent=1, default=str))

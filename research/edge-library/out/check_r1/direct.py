"""CHECKER (stage 2b) -- direct look-ahead checks on real BUILD data, own code:
  N2  the value area a va_reclaim instance holds on day D == MY value area of the PREVIOUS trade date's 09:30-16:00 prints
      (own implementation), and != today's own value area (so it cannot be today's);
  N4  late_mom: on every BUILD trade of the stored cells sig 15:30 / 12:00 / 10:00, thr 0: side == sign(last print strictly
      before the signal time - previous trade date's last print), and the entry print is at / after 15:30:00.085;
  cache: va70_<root>.json holds no date after 2023-12-29."""
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_gates as G  # noqa: E402
import perturb as P  # noqa: E402


def my_va(tape):
    t0, t1 = S.et_ns(tape.date, "09:30"), S.et_ns(tape.date, "16:00")
    m = (tape.ts >= t0) & (tape.ts < t1)
    if not m.any():
        return None
    tick = S.SPECS[tape.root][1]
    vol = {}
    for p, s in zip(np.rint(tape.px[m] / tick).astype(np.int64).tolist(), tape.size[m].tolist()):
        vol[p] = vol.get(p, 0) + s
    tot = sum(vol.values())
    poc = min(k for k, v in vol.items() if v == max(vol.values()))
    lo = hi = poc
    acc = vol[poc]
    kmin, kmax = min(vol), max(vol)
    while acc < 0.70 * tot and (lo > kmin or hi < kmax):
        up = vol.get(hi + 1, 0) if hi < kmax else -1
        dn = vol.get(lo - 1, 0) if lo > kmin else -1
        if up >= dn:
            hi += 1
            acc += up
        if dn >= up:
            lo -= 1
            acc += dn
    return round(lo * tick, 6), round(hi * tick, 6)


def n2(root, n=30, seed=11):
    cls = families.REGISTRY["va_reclaim"][0]
    params = {**families.unit_inputs("va_reclaim", "5", "nyam"), "d_atr": 0.25, "stop_mode": "pts", "stop_val": 20.0, "tgt_r": 2.0,
              "hold_to": "day"}
    days = [d for d in S.sessions(S.BUILD[0], S.BUILD[1], root)]
    rnd = random.Random(seed)
    pick = sorted(rnd.sample(range(1, len(days)), n))
    ok = bad = none = same_as_today = 0
    for i in pick:
        d, dprev = days[i], days[i - 1]
        tape = S.load_tape(d, root)
        tprev = S.load_tape(dprev, root)
        if tape is None or tprev is None:
            continue
        _, st = P.run_day(cls, params, root, tape)
        used = getattr(st, "va", None)
        if used is None:
            none += 1
            continue
        mine = my_va(tprev)
        today = my_va(tape)
        if mine is not None and abs(used[0] - mine[0]) < 1e-9 and abs(used[1] - mine[1]) < 1e-9:
            ok += 1
        else:
            bad += 1
            print("  N2 MISMATCH", root, d, "used", used, "mine(prev day)", mine)
        same_as_today += bool(today is not None and abs(used[0] - today[0]) < 1e-9 and abs(used[1] - today[1]) < 1e-9)
    return {"root": root, "days": len(pick), "equal_prev_day_va": ok, "mismatch": bad, "no_va(roll or first)": none,
            "equal_today_va": same_as_today}


def n4(root):
    u = G.load(f"late_mom-{root}-tf30")
    daily = S.load_daily(root)
    dates = [r["date"] for r in daily]
    roll = S.rolls(daily)
    out = {}
    for sig in ("15:30", "12:00", "10:00"):
        cid = f"sig{sig.replace(':', '')}_thr0_pts20-r0" if root == "NQ" else None
        cid = next(c["id"] for c in u["meta"]["cells"] if c["variant"] == {"sig": sig, "thr": 0.0}
                   and c["exit"]["stop_mode"] == "pts" and c["exit"]["tgt_r"] == 0.0)
        x = G.cell(u, u["idx"][cid])
        bad = early = n = zero = 0
        for o, e_ms, sd in zip(x["date"].tolist(), x["entry_ms"].tolist(), x["side"].tolist()):
            d = dt.date.fromordinal(o)
            iso = d.isoformat()
            tape = S.load_tape(d, root)
            k = int(np.searchsorted(tape.ts, S.et_ns(d, sig), "left"))
            p = float(tape.px[k - 1])
            i = bisect_left(dates, iso)
            pdc = daily[i - 1]["c"]
            assert iso not in roll
            n += 1
            want = 1 if p > pdc else -1 if p < pdc else 0
            zero += want == 0
            got = 1 if sd > 0 else -1
            if want != got:
                bad += 1
                if bad <= 3:
                    print("  N4 MISMATCH", root, sig, iso, "p", p, "pdc", pdc, "side", sd)
            if e_ms * 1_000_000 < S.et_ns(d, "15:30") + 84_000_000:
                early += 1
        out[sig] = {"cell": cid, "trades": n, "side_mismatch": bad, "entry_before_15:30:00.085": early}
    return {"root": root, **out}


if __name__ == "__main__":
    rep = {"va_cache_last_date": {}}
    for root in ("NQ", "ES", "GC"):
        p = S.CACHE / f"va70_{root}.json"
        ks = sorted(json.loads(p.read_text()))
        rep["va_cache_last_date"][root] = [ks[0], ks[-1], len(ks)]
    print(rep["va_cache_last_date"], flush=True)
    rep["n2"] = [n2("NQ"), n2("GC", n=16)]
    print(rep["n2"], flush=True)
    rep["n4"] = [n4("NQ")]
    print(rep["n4"], flush=True)
    Path(__file__).with_name("direct.json").write_text(json.dumps(rep, indent=1, default=str))

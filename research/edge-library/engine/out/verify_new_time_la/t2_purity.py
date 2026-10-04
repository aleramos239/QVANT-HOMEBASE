"""ADVERSARIAL VERIFIER, straddle_t + its time-shuffle null: DECISION PURITY at the exact fire instant.
For every bracket decision (real fire and null fire, seeds 1 / 2) the tape is rebuilt with
  (a) a wild print inserted AT EXACTLY the decision instant (ts == now), and
  (b) every print with ts >= now replaced by garbage prices / sizes,
and the spec is replayed: the anchor, the ATR, both legs and both resting orders (price, stop, target) must be unchanged.
Also: the null fires on a whole minute within +/- 90 min of `at`, its whole window inside its segment, anchor = last print
strictly before ITS fire. Order prices / timing only, no P&L. BUILD days, <= 10 days, 1 process."""
import sys
import datetime as dt
import random

sys.dont_write_bytecode = True
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/edge-library")
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/edge-library/engine")
import numpy as np  # noqa: E402
import l2sim as S  # noqa: E402
import families  # noqa: E402
from families import timed as T  # noqa: E402
from t1_straddle_oracle import Spy, wall, TIMES, FLAT  # noqa: E402

NS = 10**9
REAL_LOAD = S.load_tape


def key(r):
    return (r["date"], r["at"], r["off"], r["seed"], r["stop"])


def fix(r):
    return (r["now"], r["lp"], r["atr"], r["nb"], tuple(r["legs"]), tuple(r["orders"]))


def main(root, days):
    specs = []
    for at in TIMES:
        g = families.unit_grid("straddle_t_" + at.replace(":", ""), root, "30")
        for c in (g[1], g[70], g[150]):                         # atr0p25 / atr1 / ptsB with different exits
            cls, p = c["spec"]
            for seed in (0, 1, 2):
                specs.append((Spy, {**p, "shift_seed": seed}))
    Spy.log = []
    res = S.run_many(specs, days=days, root=root, workers=1)
    assert all(r["skipped_by_error"] == 0 for r in res)
    real = {key(r): r for r in Spy.log}
    assert len(real) == len(Spy.log)
    tapes = {iso: REAL_LOAD(iso, root) for iso in days}
    rng = np.random.default_rng(11)
    bad, n, n_null, shifts = [], 0, 0, {}
    # null geometry
    for r in Spy.log:
        d = dt.date.fromisoformat(r["date"])
        eve = r["at"] >= "18:00"
        base, flat = wall(d, r["at"], eve), wall(d, FLAT[r["at"]], eve)
        k = (r["now"] - base) / (60 * NS)
        if r["seed"] == 0:
            if k != 0:
                bad.append(("real fire not at `at`", key(r)))
            continue
        n_null += 1
        shifts.setdefault((r["at"], r["seed"]), set()).add(k)
        lo, hi = (wall(d, "18:00", True), wall(d, "23:59", True)) if eve else (wall(d, "00:00", False), wall(d, "15:58", False))
        if k != int(k) or abs(k) > 90 or base + k * 60 * NS < lo or flat + k * 60 * NS > hi:
            bad.append(("null fire outside +/- 90 min / its segment", key(r), k))
        tp = tapes[r["date"]]
        i = int(np.searchsorted(tp.ts, r["now"]))
        if i > 0 and r["lp"] != float(tp.px[i - 1]):
            bad.append(("null anchor is not the last print before its fire", key(r), r["lp"], float(tp.px[i - 1])))
    # purity: one replay per distinct (day, decision instant)
    by_now = {}
    for r in Spy.log:
        by_now.setdefault((r["date"], r["now"]), []).append(r)
    for (iso, now), rows in sorted(by_now.items()):
        tp = tapes[iso]
        d = dt.date.fromisoformat(iso)
        i = int(np.searchsorted(tp.ts, now, side="left"))
        ref = float(tp.px[i - 1]) if i > 0 else float(tp.px[0])
        tick = S.SPECS[root][1]; px_tail = np.round(tp.px[i:] * rng.uniform(0.6, 1.4, len(tp.px) - i) / tick) * tick
        ts = np.concatenate([tp.ts[:i], [now], tp.ts[i:]])
        px = np.concatenate([tp.px[:i], [ref + 777.0], px_tail])
        sz = np.concatenate([tp.size[:i], [9999], rng.integers(1, 400, len(tp.size) - i)])
        fake = S.Tape(root, d, tp.contract, ts, px, sz)
        assert np.all(np.diff(ts) >= 0) and ts[i] == now
        S.load_tape = lambda dd, r=root, **kw: fake              # noqa: E731
        try:
            mine = [(Spy, {"at": x["at"], "off": x["off"], "shift_seed": x["seed"], "tf": "30", "stop_mode": x["stop"][0],
                           "stop_val": x["stop"][1], "tgt_r": x["stop"][2]}) for x in rows]
            Spy.log = []
            rr = S.run_many(mine, days=[iso], root=root, workers=1)
            got = {key(g): g for g in Spy.log}
        finally:
            S.load_tape = REAL_LOAD
        if any(x["skipped_by_error"] for x in rr):
            bad.append(("replay error", iso, now, [x["no_trade"] for x in rr]))
        for x in rows:
            n += 1
            g = got.get(key(x))
            if g is None or fix(g) != fix(x):
                bad.append(("decision changed by prints at / after its own instant", key(x), fix(x), None if g is None else fix(g)))
    print(f"{root}: days={len(days)} decisions replayed={n} (null decisions {n_null}) MISMATCHES={len(bad)}")
    for (at, seed), ks in sorted(shifts.items()):
        print(f"   null {at} seed {seed}: shifts (min) {sorted(int(k) for k in ks)}")
    for b in bad[:20]:
        print("  BAD", b)
    return bad


if __name__ == "__main__":
    root, days = sys.argv[1], sys.argv[2].split(",")
    assert len(days) <= 10 and all(S.BUILD[0] <= dt.date.fromisoformat(x) <= S.BUILD[1] for x in days)
    sys.exit(1 if main(root, days) else 0)

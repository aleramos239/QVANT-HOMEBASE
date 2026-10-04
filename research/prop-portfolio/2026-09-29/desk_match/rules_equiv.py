"""Desk daily-rule math (homebase/dayrules.py) vs the research (evalcore._walk_day / take_level), random cases."""
import sys, random, math
from pathlib import Path
HB = Path.home() / "ramos-quant-homebase"
sys.path.insert(0, str(HB / "research/prop-portfolio/2026-09-29")); sys.path.insert(0, str(HB))
import numpy as np
import evalcore as E
import homebase
sys.path.insert(0, str(Path.cwd()))
for m in [m for m in sys.modules if m == 'homebase' or m.startswith('homebase.')]: del sys.modules[m]
from homebase.dayrules import DayBook, DayRules, take_level, take_points, size_for_profit
rnd = random.Random(20261001)
# 1. target_take level
bad = n = 0
for _ in range(200000):
    r = {"eval_target": rnd.choice([2000., 3000., 4000., 6000.]), "eval_min_days": rnd.choice([1, 2, 3, 5]),
         "consistency": rnd.choice([None, 0.5, 0.4, 0.3])}
    profit = rnd.choice([-1500., 0., 500., 900., 1500., 2500., 2999., 3000., 4500.]) + rnd.choice([0, 0.5, 12.25])
    largest = rnd.choice([0., 400., 1500., 2100., 3000.]); days = rnd.randint(0, 6)
    a = float(E.take_level(r, [profit], [largest], [days])[0])
    b = take_level(r["eval_target"], profit, largest, days, min_days=r["eval_min_days"], consistency=r["consistency"])
    n += 1
    if not ((b is None and math.isnan(a)) or (b is not None and not math.isnan(a) and abs(a - b) < 1e-9)):
        bad += 1
        if bad < 5: print("TAKE_LEVEL MISMATCH", r, profit, largest, days, a, b)
print("target_take level: cases", n, "mismatches", bad)
# 2. day_take / day_lock: which trades of a multi-trade day get taken, who stops the day
bad = n = 0; kinds = {}
for _ in range(60000):
    N = rnd.choice([10, 20, 30, 40]); micros = N; fee_rt = 4.0
    tk = rnd.choice([0., 600., 1000., 1500.]); dl = rnd.choice([0., 300., 750., 1000.])
    if not (tk or dl): continue
    k = rnd.randint(1, 5); trs, mfes, nets = [], [], []
    t = 0
    for i in range(k):
        g = rnd.choice([-1, 1]) * rnd.uniform(0, 3500) * rnd.choice([0.2, 1])
        mfe = max(g, 0) + rnd.choice([0, 0, rnd.uniform(0, 4000)])
        trs.append((t, t + 10, 1, g, max(0.0, -g) + 10, micros, float("nan"), 0)); mfes.append(mfe); t += 100
    st = E._new_st()
    E._walk_day(trs, micros, 0, 0, dl, 1.0, 1.0, False, micros, st, mfes, tk)
    ref_n = st["executed"]
    # desk: DayBook with the same rules; a trade is taken iff best net >= what is still needed today
    book, rules, nd = DayBook("a", "d"), DayRules(day_take=tk, day_lock=dl), 0
    cost = E.cost(micros)
    for (te, tx, sd, g, mae, m, rk, mem), mfe in zip(trs, mfes):
        if book.locked: continue
        nd += 1
        p = micros * g / 10 - cost
        best = max(micros * mfe / 10 - cost, p)
        need = book.take_net(rules)
        if need is not None and best >= need - book.closed_net - 1e-9:
            net = need - book.closed_net            # the take limit fills: the day total lands on the take
        else:
            net = p
        book.record_close(net, rules)
    n += 1
    if nd != ref_n:
        bad += 1
        if bad < 5: print("DAY RULE MISMATCH", tk, dl, trs, mfes, ref_n, nd)
print("day_take/day_lock: random days", n, "trades-taken mismatches", bad)
# 3. take_points vs the research's trigger: MFE net >= X  <=>  MFE pts >= (X + fee) / (pv * q)
bad = 0
for q in (1, 2, 3, 4):
    for X in (300., 600., 750., 1000., 1500., 2000., 3000.):
        pts = take_points(X, q, 20.0, 4.0, 0.25)
        net = pts * 20 * q - 4 * q
        net_below = (pts - 0.25) * 20 * q - 4 * q
        if not (net >= X and net_below < X): bad += 1; print("TAKE_POINTS", q, X, pts)
print("take_points: first tick that nets >= X, all (qty, X):", "OK" if not bad else bad)
tiers = [[0, 2], [1000, 3], [2000, 4]]
assert [size_for_profit(tiers, p, 4) for p in (-500, 0, 999.99, 1000, 1999.99, 2000, 9000)] == [2, 2, 2, 3, 3, 4, 4]
print("size tiers (spec: <1000 2 NQ, <2000 3 NQ, else 4): OK")

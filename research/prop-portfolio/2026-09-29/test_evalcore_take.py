#!/usr/bin/python3
"""Tests for the intraday take rules (day_take / target_take) of evalcore. Hand-derived cases first (n = 10 micros:
cost(10) = $4, 1 tick x 10 micros = $5, so a trade with gross g nets g - 4), then brute-force references.
Run: /usr/bin/python3 test_evalcore_take.py  (or pytest)."""
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalcore as E                                            # noqa: E402
from test_evalcore import tr, port, LUCID, APEX                 # noqa: E402
from test_evalcore_adv import week                              # noqa: E402

_, LU = LUCID
_, AP = APEX
CAL = week(0, 1, 2, 3, 4)
D1 = CAL[0]
IDX = np.arange(5)[None, :]


def trm(date, hhmm, gross, mae=0.0, mfe=None, **kw):
    t = tr(date, hhmm, gross, mae=mae, **kw)
    t["mfe_usd"] = max(gross, 0.0) if mfe is None else mfe
    return t


def day(ts, rules, m=10, cap=100, cal=CAL):
    """-> (Port, DayArr) with the rule dict applied (day_take via take_rules)."""
    P = port([(ts, m)], cal)
    return P, E.walk(P, cap, E.norm_rules(rules), want_chk=True, day_take=E.take_rules(rules)[0])


def eval1(ts, rules, firm, m=10, breach="eod", cal=CAL):
    P, A = day(ts, rules, m, cal=cal)
    return tuple(int(x[0]) for x in E.race(np.arange(len(cal))[None, :][:, :5], A, firm, breach, False,
                                            E.take_rules(rules)[1]))


# ---------------------------------------------------------------- day_take: hand cases

def test_day_take_hit_and_exact_exit():
    # best = 1500 - 4 = 1496 >= 1000 -> closed at 1000 - 0 - 5 = 995 (final 300-4 = 296 is replaced); later trade skipped
    ts = [trm(D1, "10:00", 300.0, mfe=1500.0), trm(D1, "11:00", 500.0)]
    P, A = day(ts, {"day_take": 1000})
    assert abs(A.tot[0] - 995) < 1e-9 and A.st["executed"] == 1 and A.st["skipped"] == 1
    # the take can also improve a trade that reversed to a loss
    _, A = day([trm(D1, "10:00", -300.0, mae=300.0, mfe=1500.0)], {"day_take": 1000})
    assert abs(A.tot[0] - 995) < 1e-9
    # it caps a winner that ran past the level
    _, A = day([trm(D1, "10:00", 2500.0, mfe=2600.0)], {"day_take": 1000})
    assert abs(A.tot[0] - 995) < 1e-9


def test_day_take_threshold_is_net_of_costs_and_inclusive():
    # best = mfe - 4: mfe 1004 -> exactly 1000 (>= X fires), mfe 1003 -> 999 (no take: the trade keeps its own P&L)
    _, A = day([trm(D1, "10:00", 300.0, mfe=1004.0)], {"day_take": 1000})
    assert abs(A.tot[0] - 995) < 1e-9
    _, A = day([trm(D1, "10:00", 300.0, mfe=1003.0)], {"day_take": 1000})
    assert abs(A.tot[0] - 296) < 1e-9
    # 20 micros: cost 8, tick 10, best = 2*mfe/... n*mfe/10 - 8 = 1592 -> exit 1000 - 10
    _, A = day([trm(D1, "10:00", 300.0, mfe=800.0)], {"day_take": 1000}, m=20)
    assert abs(A.tot[0] - 990) < 1e-9


def test_day_take_uses_realised_pnl_of_earlier_trades():
    # A nets 600; B best = 600 - 4 = 596 -> 600 + 596 >= 1000 -> B exits at 1000 - 600 - 5 = 395; day = 995
    ts = [trm(D1, "10:00", 604.0), trm(D1, "11:00", 100.0, mfe=600.0), trm(D1, "12:00", 900.0)]
    _, A = day(ts, {"day_take": 1000})
    assert abs(A.tot[0] - 995) < 1e-9 and A.st["executed"] == 2
    # after a -104 loser B needs a bigger run: best 1496 - 104 = 1392 >= 1000 -> exit 1000 + 104 - 5 = 1099
    ts = [trm(D1, "10:00", -100.0, mae=100.0), trm(D1, "11:00", 300.0, mfe=1500.0)]
    _, A = day(ts, {"day_take": 1000})
    assert abs(A.tot[0] - 995) < 1e-9
    ts = [trm(D1, "10:00", -100.0, mae=100.0), trm(D1, "11:00", 300.0, mfe=1100.0)]     # 1096 - 104 = 992 < 1000: no take
    _, A = day(ts, {"day_take": 1000})
    assert abs(A.tot[0] - (-104 + 296)) < 1e-9


def test_day_take_none_changes_nothing():
    rng = random.Random(5)
    for trial in range(200):
        ts = [trm(D1, f"{9 + k}:{rng.randint(0, 40):02d}", float(rng.randint(-600, 900)), mae=float(rng.randint(0, 700)),
                  mfe=float(rng.randint(900, 3000)), side=rng.choice(["long", "short"]), dur=rng.choice([3, 90]))
              for k in range(rng.randint(1, 5))]
        rules = {"max_day_tr": rng.choice([0, 2]), "day_stop": rng.choice([0, 500]), "day_lock": rng.choice([0, 400]),
                 "after_loss": rng.choice([1.0, 0.5])}
        P = port([(ts, rng.choice([10, 20]))])
        rl = E.norm_rules(rules)
        base = E.walk(P, 40, rl)
        for tk in (None, 0, 1e9):                                          # off, or a level no trade can reach
            A = E.walk(P, 40, rl, day_take=tk)
            assert np.array_equal(A.tot, base.tot) and np.array_equal(A.worst, base.worst) and A.st == base.st
    assert E.take_rules({}) == (0.0, False) and E.take_rules({"day_take": None}) == (0.0, False)
    # without an mfe column (or with mfe < final) best = final P&L: a take fires only when the realised path gets there
    ts = [{**trm(D1, "10:00", 1300.0), "mfe_usd": None}]
    _, A = day(ts, {"day_take": 1000})
    assert abs(A.tot[0] - 995) < 1e-9                                                  # 1296 >= 1000 -> capped at the level


# ---------------------------------------------------------------- ordering conflicts (pessimistic)

def test_day_stop_beats_day_take_in_the_same_trade():
    # worst -604 <= -500: the adverse point came first -> closed at -500 - 0 - 5, no take although MFE = 1500
    _, A = day([trm(D1, "10:00", -100.0, mae=600.0, mfe=1500.0)], {"day_stop": 500, "day_take": 1000})
    assert abs(A.tot[0] - (-505)) < 1e-9
    # MAE 400 (worst -404) does not reach the stop -> the take fires
    _, A = day([trm(D1, "10:00", -100.0, mae=400.0, mfe=1500.0)], {"day_stop": 500, "day_take": 1000})
    assert abs(A.tot[0] - 995) < 1e-9
    # the rule file's soft daily limit is a stop too (Lucid $1,200 variant)
    r = E.firm_rules("lucid-flex-50k-dll@2026-09-27b")[1]
    P = port([([trm(D1, "10:00", -100.0, mae=1300.0, mfe=1500.0)], 10)])
    A = E.walk(P, 40, E.norm_rules({}), dll=E.PS._dll(r), day_take=1000)
    assert abs(A.tot[0] - (-1205)) < 1e-9
    # an earlier realised loss brings the stop closer: -404 realised, next trade worst -104-404 ... hits -500
    ts = [trm(D1, "10:00", -400.0, mae=400.0), trm(D1, "11:00", 200.0, mae=200.0, mfe=1800.0)]
    _, A = day(ts, {"day_stop": 600, "day_take": 1000})
    assert abs(A.tot[0] - (-600 - 5)) < 1e-9 and A.st["executed"] == 2


def test_intraday_floor_beats_the_take():
    # target_take, Apex, day 1: the trade dips to -2104 (floor -2000) and later touches +3100. EOD model: the take
    # passes it; intraday model: the MAE came first -> bust, even though the take fired.
    t = [trm(D1, "10:00", 100.0, mae=2100.0, mfe=3100.0)]
    assert eval1(t, {"target_take": True}, AP) == (1, 1)
    assert eval1(t, {"target_take": True}, AP, breach="intraday") == (2, 1)
    # day_take only (X = 1000): the day's worst still holds the MAE -> intraday bust
    P, A = day(t, {"day_take": 1000})
    assert abs(A.tot[0] - 995) < 1e-9 and abs(A.worst[0] - (-2104)) < 1e-9
    assert E.race(IDX, A, AP, "intraday")[0][0] == 2 and E.race(IDX, A, AP, "eod")[0][0] == 0


# ---------------------------------------------------------------- interaction with day_lock / max_day_tr

def test_day_take_with_day_lock_and_max_day_tr():
    # day_lock 300 acts on CLOSED P&L: A closes 346 -> locked before B; the take (1000) never fires
    ts = [trm(D1, "10:00", 350.0, mfe=400.0), trm(D1, "11:00", 900.0, mfe=2000.0)]
    _, A = day(ts, {"day_lock": 300, "day_take": 1000})
    assert abs(A.tot[0] - 346) < 1e-9 and A.st["executed"] == 1
    # a take BELOW the lock ends the day first: X = 200 -> A exits at 200 - 5
    _, A = day(ts, {"day_lock": 300, "day_take": 200})
    assert abs(A.tot[0] - 195) < 1e-9 and A.st["executed"] == 1
    # max_day_tr = 2: the taking trade counts as an entry; with 1 the second trade is refused before any take
    ts = [trm(D1, "10:00", -100.0, mae=100.0, mfe=50.0), trm(D1, "11:00", 300.0, mfe=1500.0), trm(D1, "12:00", 500.0)]
    _, A = day(ts, {"max_day_tr": 2, "day_take": 1000})
    assert abs(A.tot[0] - 995) < 1e-9 and A.st["executed"] == 2
    _, A = day(ts, {"max_day_tr": 1, "day_take": 1000})
    assert abs(A.tot[0] - (-104)) < 1e-9 and A.st["executed"] == 1
    # after_loss sizing: B is half size (5 micros, cost 5, tick 2.5): best = 5*1500/10 - 5 = 745; -104 + 745 >= 600
    ts = [trm(D1, "10:00", -100.0, mae=100.0), trm(D1, "11:00", 300.0, mfe=1500.0)]
    _, A = day(ts, {"after_loss": 0.5, "day_take": 600})
    assert abs(A.tot[0] - (600 - 2.5)) < 1e-9


def test_day_take_overlapping_portfolio_trades():
    # A open 10:00-10:30 (final 196, NOT credited its MFE); B enters 10:10: 0 + 196 + (1500 - 4) >= 1000 ->
    # B closes so that the book's day total is 1000 - 5: p_B = 1000 - 196 - 5 = 799, day = 995
    a = trm(D1, "10:00", 200.0, mfe=900.0, dur=30)
    b = trm(D1, "10:10", 100.0, mfe=1500.0, dur=30, side="short")
    P = port([([a], 10), ([b], 10)])
    A = E.walk(P, 100, E.norm_rules({}), day_take=1000)
    assert abs(A.tot[0] - 995) < 1e-9 and A.st["overlap"] == 1
    b["mfe_usd"] = 700.0                                   # 196 + 696 = 892 < 1000: no take, plain sum
    P = port([([a], 10), ([b], 10)])
    A = E.walk(P, 100, E.norm_rules({}), day_take=1000)
    assert abs(A.tot[0] - (196 + 96)) < 1e-9


# ---------------------------------------------------------------- target_take: level per firm

def test_take_level_apex_and_lucid_hand_cases():
    lv = lambda r, p, la, td: float(E.take_level(r, [p], [la], [td])[0])
    assert lv(AP, 0, 0, 0) == 3000 and lv(AP, 2000, 1500, 3) == 1000                 # Apex: remaining distance
    assert np.isnan(lv(AP, 3000, 0, 0))                                              # nothing left: no level
    assert np.isnan(lv(LU, 0, 0, 0))                                                 # Lucid day 1: min-days blocks
    assert lv(LU, 1500, 1500, 1) == 1500                                             # 1500 <= 0.5 * 3000 exactly
    assert np.isnan(lv(LU, 1000, 1000, 1))                                           # 2000 would be > half of 3000
    assert lv(LU, 2000, 1600, 2) == 1200                                             # target 1000 fails consistency:
    #   largest 1600 needs total >= 3200 -> smallest passing day is 1200 (3200, largest 1600 <= 1600)
    assert lv(LU, 2400, 1200, 2) == 600                                              # plain remaining distance
    assert np.isnan(lv(LU, 1600, 1800, 2))                                           # even L = 2000 (3600) < 1800/.5
    assert lv(dict(LU, consistency=None), 1000, 1000, 1) == 2000                     # no consistency -> Apex-like
    assert np.isnan(lv(dict(LU, eval_min_days=3), 500, 500, 1))                      # needs 2 more days
    assert lv(dict(LU, eval_min_days=3), 1500, 800, 2) == 1500                       # third day: 3000, 800 <= 1500


def test_take_level_matches_bruteforce_scan():
    rng = random.Random(9)
    Ls = np.arange(0.5, 20000, 0.5)
    for r in (LU, AP, dict(LU, eval_min_days=1)):
        for _ in range(300):
            profit = float(rng.randint(-1500, 3000)) * 1.0
            largest = float(rng.randint(0, 2500))
            td = rng.randint(0, 4)
            ok = (profit + Ls >= r["eval_target"]) & (td + 1 >= r["eval_min_days"])
            if r["consistency"] is not None:
                ok &= np.maximum(largest, Ls) <= r["consistency"] * (profit + Ls)
            want = float(Ls[ok.argmax()]) if ok.any() else np.nan
            got = float(E.take_level(r, [profit], [largest], [td])[0])
            assert (np.isnan(want) and np.isnan(got)) or got == want, (r["consistency"], profit, largest, td, got, want)


# ---------------------------------------------------------------- target_take: end to end

def test_target_take_apex_hand_cases():
    # day 1: remaining distance 3000: trigger 3000 + 5 (slippage on top so the day lands exactly on 3000)
    assert eval1([trm(D1, "10:00", 100.0, mfe=3009.0)], {"target_take": True}, AP) == (1, 1)     # best 3005 -> 3000
    assert eval1([trm(D1, "10:00", 100.0, mfe=3008.0)], {"target_take": True}, AP) == (0, 0)     # best 3004: no take
    assert eval1([trm(D1, "10:00", 100.0, mfe=3100.0)], {}, AP) == (0, 0)                          # rule off: 96 only
    # day 2 needs only the remaining 1000
    ts = [trm(D1, "10:00", 2004.0), trm(CAL[1], "10:00", 50.0, mfe=1500.0), trm(CAL[1], "12:00", -3000.0, mae=3000.0)]
    assert eval1(ts, {"target_take": True}, AP) == (1, 2)
    # later trades of the pass day are skipped (the -3000 loser would have busted the account)
    P, A = day(ts, {"target_take": True})
    assert A.tot[1] < -2000 and E.race(IDX, A, AP, "eod", False, False)[0][0] == 2               # untruncated day busts
    assert E.race(IDX, A, AP, "eod", False, True)[0][0] == 1


def test_target_take_lucid_hand_cases():
    # day 1 can never pass (2-day minimum): no level -> the trade runs to its own P&L
    assert eval1([trm(D1, "10:00", 100.0, mfe=5000.0)], {"target_take": True}, LU) == (0, 0)
    # d1 +1504 (net 1500, largest 1500) ; d2 level = 1500 -> pass on day 2 with the largest day exactly 50%
    ts = [trm(D1, "10:00", 1504.0), trm(CAL[1], "10:00", 10.0, mfe=1600.0)]
    assert eval1(ts, {"target_take": True}, LU) == (1, 2)
    # d1 +1000, d2 wants 2000 -> consistency fails at the target -> no level -> keep trading; d2 nets 6: not a pass
    ts = [trm(D1, "10:00", 1004.0), trm(CAL[1], "10:00", 10.0, mfe=5000.0)]
    assert eval1(ts, {"target_take": True}, LU) == (0, 0)
    # profit 2000 with largest 1600 (days 1600, 400): the target's 1000 fails consistency, the level is 1200
    ts = [trm(D1, "10:00", 1604.0), trm(CAL[1], "10:00", 404.0), trm(CAL[2], "10:00", 10.0, mfe=1300.0)]
    assert eval1(ts, {"target_take": True}, LU) == (1, 3)
    ts[2]["mfe_usd"] = 1200.0                                                                    # best 1196 < 1205 trigger
    assert eval1(ts, {"target_take": True}, LU) == (0, 0)
    ts[2]["mfe_usd"] = 1100.0                                    # only the plain target distance: must NOT stop at 1000
    assert eval1(ts, {"target_take": True}, LU) == (0, 0)


def test_target_take_with_other_rules():
    # day_take below the target level fires first (lower trigger): day 995, not a pass
    t = [trm(D1, "10:00", 100.0, mfe=3100.0)]
    assert eval1(t, {"target_take": True, "day_take": 1000}, AP) == (0, 0)
    assert eval1(t, {"target_take": True, "day_take": 5000}, AP) == (1, 1)
    # day_stop conflict: MAE -604 hits the 500 stop first -> stopped at -505, the pass never happens
    t = [trm(D1, "10:00", 100.0, mae=600.0, mfe=4000.0)]
    assert eval1(t, {"target_take": True, "day_stop": 500}, AP) == (0, 0)
    P, A = day(t, {"target_take": True, "day_stop": 500})
    assert abs(A.tot[0] - (-505)) < 1e-9
    assert eval1(t, {"target_take": True}, AP) == (1, 1)                                       # same trade without the stop
    # day_lock / max_day_tr act as before: A closes 346 >= 300 -> B (which would take) is never entered
    t = [trm(D1, "10:00", 350.0, mfe=350.0), trm(D1, "11:00", 100.0, mfe=4000.0)]
    assert eval1(t, {"target_take": True, "day_lock": 300}, AP) == (0, 0)
    assert eval1(t, {"target_take": True, "max_day_tr": 1}, AP) == (0, 0)
    assert eval1(t, {"target_take": True}, AP) == (1, 1)


def test_target_take_off_or_unreachable_changes_nothing():
    rng = random.Random(21)
    cal = week(0, 1, 2, 3, 4, 7, 8, 9, 10, 11)
    idx = np.arange(len(cal) - 4)[:, None] + np.arange(5)
    for trial in range(60):
        ts = [trm(d, f"{10 + k}:{rng.randint(0, 50):02d}", float(rng.randint(-700, 1300)), mae=float(rng.randint(0, 800)),
                  mfe=float(rng.randint(1300, 2500)), dur=20) for d in cal for k in range(rng.randint(0, 3))]
        if not ts:
            continue
        P = port([(ts, rng.choice([10, 20]))], cal)
        A = E.walk(P, 40, E.norm_rules({}))
        for r in (LU, AP):
            off = E.race(idx, A, r, "eod", False, False)
            unreachable = E.race(idx, A, dict(r, eval_target=10 ** 9), "eod", False, True)
            assert np.array_equal(unreachable[0], E.race(idx, A, dict(r, eval_target=10 ** 9), "eod", False, False)[0])
            hand = E.DayArr(A.tot, A.worst, A.trd)                                         # no rewalk closure -> ignored
            assert np.array_equal(E.race(idx, hand, r, "eod", False, True)[0], off[0])


# ---------------------------------------------------------------- brute-force references (non-overlapping trades)

def ref_take_day(trs, m, tk=0.0, tt=0.0, ds=0.0, dl=0.0, mt=0):
    """Independent day walk. trs = [(gross, mae, mfe)] sequential. -> (total, worst, traded)."""
    c = m // 10 * 4.0 + m % 10 * 1.0
    real, taken, halt, worst = 0.0, 0, False, float("inf")
    for g, mae, mfe in trs:
        if halt or (mt and taken >= mt):
            continue
        p = m * g / 10 - c
        w = min(p, -mae * m / 10 - c)
        best = max(m * mfe / 10 - c, p)
        if ds and real + w <= -ds:
            p, halt = -ds - real - 0.5 * m, True
            w = p
        else:
            lv = ([(tk, tk - 0.5 * m)] if tk else []) + ([(tt + 0.5 * m, tt)] if tt else [])
            if lv:
                trig, fin = min(lv)
                if real + best >= trig:
                    p, halt = fin - real, True
                    w = min(w, p)
        worst = min(worst, real + w)
        real += p
        taken += 1
        if dl and real >= dl:
            halt = True
    return (real, min(worst, real), True) if taken else (0.0, 0.0, False)


def test_walk_matches_bruteforce_day_take_random():
    rng = random.Random(4)
    for trial in range(500):
        raw = [(float(rng.randint(-800, 1200)), float(rng.randint(0, 900)), 0.0) for _ in range(rng.randint(1, 6))]
        raw = [(g, mae, float(max(g, 0) + rng.randint(0, 1500))) for g, mae, _ in raw]
        ts = [trm(D1, f"{9 + k}:{rng.randint(0, 40):02d}", g, mae=mae, mfe=mfe, dur=1) for k, (g, mae, mfe) in enumerate(raw)]
        m = rng.choice([1, 5, 10, 20, 40])
        rules = {"day_take": rng.choice([0, 300, 800, 1500]), "day_stop": rng.choice([0, 400, 900]),
                 "day_lock": rng.choice([0, 300]), "max_day_tr": rng.choice([0, 2])}
        P, A = day(ts, rules, m=m, cap=40, cal=week(0))
        tot, worst, traded = ref_take_day(raw, m, rules["day_take"], 0.0, rules["day_stop"], rules["day_lock"], rules["max_day_tr"])
        assert abs(A.tot[0] - tot) < 1e-6 and abs(A.worst[0] - worst) < 1e-6 and bool(A.trd[0]) == traded, (trial, rules, raw, m)


def ref_take_race(days, firm, tt_on, tk=0.0, m=10, breach="eod"):
    """Brute-force 5-day race of one start; days = list of [(g, mae, mfe)]. The take level is found by scanning."""
    profit = peak = largest = 0.0
    floor, td = -float(firm["trailing_mll"]), 0
    Ls = np.arange(0.5, 20000, 0.5)
    for k, trs in enumerate(days):
        tt = 0.0
        if tt_on and trs:
            ok = (profit + Ls >= firm["eval_target"]) & (td + 1 >= firm["eval_min_days"])
            if firm["consistency"] is not None:
                ok &= np.maximum(largest, Ls) <= firm["consistency"] * (profit + Ls)
            tt = float(Ls[ok.argmax()]) if ok.any() else 0.0
        tot, worst, traded = ref_take_day(trs, m, tk, tt)
        new = profit + tot
        if new <= floor or (breach == "intraday" and profit + worst <= floor):
            return 2, k + 1
        profit, td, largest = new, td + traded, max(largest, tot)
        peak = max(peak, new)
        floor = float(firm["lock_floor"]) if peak >= firm["lock_at"] else peak - firm["trailing_mll"]
        if new >= firm["eval_target"] and td >= firm["eval_min_days"] and (firm["consistency"] is None or largest <= firm["consistency"] * new):
            return 1, k + 1
    return 0, 0


def test_race_matches_bruteforce_take_random():
    rng = random.Random(8)
    cal = week(0, 1, 2, 3, 4, 7, 8, 9, 10, 11, 14, 15)
    idx = np.arange(len(cal) - 4)[:, None] + np.arange(5)
    for firm in (LU, AP):
        for trial in range(60):
            per = {d: [] for d in cal}
            ts = []
            for d in cal:
                for k in range(rng.randint(0, 3)):
                    g = float(rng.randint(-700, 1500)) * rng.choice([1, 1, 2])
                    mae, mfe = float(rng.randint(0, 900)), float(max(g, 0) + rng.randint(0, 2500))
                    ts.append(trm(d, f"{10 + 2 * k}:{rng.randint(0, 50):02d}", g, mae=mae, mfe=mfe, dur=20))
                    per[d].append((g, mae, mfe))
            if not ts:
                continue
            m = rng.choice([10, 20, 40])
            tk = rng.choice([0, 0, 1000, 1500])
            rules = {"target_take": True, "day_take": tk}
            P, A = day(ts, rules, m=m, cap=40, cal=cal)
            for breach in ("eod", "intraday"):
                o, dd = E.race(idx, A, firm, breach, False, True)
                for s in range(idx.shape[0]):
                    want = ref_take_race([per[cal[s + k]] for k in range(5)], firm, True, tk, m, breach)
                    assert (int(o[s]), int(dd[s])) == want, (firm["consistency"], breach, trial, s, (int(o[s]), int(dd[s])), want)


def test_evaluate_and_search_accept_the_take_rules():
    cal = week(0, 1, 2, 3, 4, 7, 8, 9, 10, 11)
    ts = [trm(d, "10:00", 200.0, mae=100.0, mfe=1500.0) for d in cal]
    cfg = {"members": [{"src": ts, "micros": 10}], "start": cal[0], "end": cal[-1], "firms": ["apex"]}
    res = {}
    for name, rules in (("off", {}), ("take", {"day_take": 800, "target_take": True})):
        res[name] = E.evaluate({**cfg, "rules": rules}, calendar=cal, mc=200, boots=0, eventual=0)["firms"]
    a, b = (next(iter(res[k].values())) for k in ("off", "take"))
    assert b["eod"]["p_pass"] >= a["eod"]["p_pass"] and b["series"]["net"] != a["series"]["net"]
    rows = E.search(cfg, {"micros": [10], "day_lock": [0], "day_stop": [0], "max_day_tr": [0], "after_loss": [1.0],
                          "target_stop": [False], "day_take": [0, 800], "target_take": [False, True]},
                    port=E.build(cfg, cal), firms=["apex"])
    assert len(rows) == 4 and len({r["p_pass"] for r in rows}) >= 2


if __name__ == "__main__":
    fails = 0
    for k, v in sorted(globals().items()):
        if k.startswith("test_"):
            try:
                v()
                print("ok  ", k)
            except Exception as ex:
                fails += 1
                import traceback
                print("FAIL", k, repr(ex)[:400])
                traceback.print_exc(limit=3)
    sys.exit(1 if fails else 0)

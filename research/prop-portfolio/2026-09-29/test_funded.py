#!/usr/bin/python3
"""Tests for funded.py (funded / PA lifecycle). Hand-built multi-day cases for every rule (Fake source = prescribed day
results; real trades through the day walk where the walk matters), parity with evalcore (day walk and no-payout bust path).
Run: /usr/bin/python3 test_funded.py  (or pytest). Numbers: n = 10 micros, cost(10) = $4, 1 tick x 10 micros = $5."""
import datetime as dt
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalcore as E                                            # noqa: E402
import funded as F                                              # noqa: E402
from evalcore import PS                                         # noqa: E402
from test_evalcore import tr, port                              # noqa: E402
from test_evalcore_take import trm                              # noqa: E402

FLEX, FLEX_DLL = F.make_spec("flex"), F.make_spec("flex", 1200)
PRO, PRO_NODLL = F.make_spec("pro"), F.make_spec("pro", 0)
APEX = F.make_spec("apex")


# ---------------------------------------------------------------- helpers

class Fake:
    """Day source with prescribed results. days: floats (pnl; 0 = no trade) or ready day tuples. Logs every request."""

    def __init__(self, days):
        self.days = [self._d(x) for x in days]
        self.n_days = len(self.days)
        self.log = []

    @staticmethod
    def _d(x):
        if isinstance(x, tuple):
            return x if len(x) == 8 else x + (x[4],)
        hi = max(x, 0.0)                                        # a clean day: equity goes straight from 0 to x
        ev = ((1, hi), (0, x), (1, x), (0, x))
        return (x, x, x, 1 if x else 0, ev, ev, 0, ev)

    def get(self, i, cap, dll=0.0, lim=0.0):
        self.log.append((i, cap, dll, lim))
        return self.days[i]

    @property
    def caps(self):
        return [c for _, c, _, _ in self.log]


def run(S, days, T=500, model=None, H=None):
    src = Fake(days)
    return F.simulate(S, src, 0, H or len(days), T, model), src


def weekdays(n, start=dt.date(2023, 3, 6)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(1)
    return out


def rand_port(seed, ndays=130, micros=20, overlap=True):
    rng = random.Random(seed)
    cal = weekdays(ndays)
    ts = []
    for d in cal:
        for _ in range(rng.choice([0, 1, 1, 2, 3, 4])):
            g = rng.gauss(40, 350)
            mae = max(0.0, -g) + rng.random() * 250
            mfe = max(g, 0.0) + rng.random() * 300
            hh, mm = rng.randint(9, 14), rng.randint(0, 59)
            t = trm(d, f"{hh:02d}:{mm:02d}", g, mae=mae, mfe=mfe, side=rng.choice(["long", "short"]),
                    dur=rng.randint(1, 150 if overlap else 1))
            ts.append(t)
    return port([(ts, micros)], cal), cal


# ---------------------------------------------------------------- day walk parity with evalcore

def test_walk_day_equals_evalcore_walk_day():
    cnt = 0
    for seed in range(6):
        P, cal = rand_port(seed, micros=[10, 20, 35][seed % 3])
        for rules in ({}, {"day_stop": 600}, {"day_lock": 300}, {"day_take": 400}, {"max_day_tr": 1},
                      {"day_stop": 300, "day_lock": 600, "day_take": 250, "max_day_tr": 2}, {"after_loss": 0.5, "after_win": 1.5}):
            rl = E.norm_rules(rules)
            tk = E.take_rules(rules)[0]
            for dll in (0.0, 1200.0):
                for cap in (20, 40):
                    ds = dll if dll and (not rl[1] or dll < rl[1]) else rl[1]
                    for i, trs in enumerate(P.days):
                        if not trs:
                            continue
                        ref = E._walk_day(trs, cap, rl[0], ds, rl[2], rl[3], rl[4], False, None, E._new_st(), P.mfe[i], tk)
                        got = F.walk_day(trs, P.mfe[i], cap, rl, None, dll, tk, 0.0, True)
                        assert abs(got[0] - ref[0]) < 1e-9 and abs(got[1] - ref[1]) < 1e-9, (seed, rules, i, got, ref)
                        assert got[3] == ref[2] and abs(got[2] - ref[6]) < 1e-9, (seed, rules, i, got, ref)
                        assert got[6] == 0
                        cnt += 1
    assert cnt > 3000


def test_events_bracket_the_day():
    # every low <= the day's worst-of-lows bookkeeping: min(lows) == worst; last events are the EOD point
    P, _ = rand_port(3)
    for i, trs in enumerate(P.days):
        if not trs:
            continue
        o = F.walk_day(trs, P.mfe[i], 40, E.norm_rules({"day_take": 400}), None, 0.0, 400.0, 0.0, True)
        for ev in (o[4], o[5]):
            assert min(v for k, v in ev if k == 0) <= o[1] + 1e-9 or abs(min(v for k, v in ev if k == 0) - o[1]) < 1e-9
            assert ev[-2:] == ((1, o[0]), (0, o[0]))


# ---------------------------------------------------------------- parity with evalcore.race_funded (no-payout path)

def _bust_days(S, P, rules, r, models=E.MODELS, micros=None):
    src = F.DaySrc(P, rules, micros)
    rl = E.norm_rules(rules)
    As, thr, _ = E._funded_levels(P, r, rl, E.take_rules(rules)[0])
    D = len(P.days)
    idx = np.arange(D - 60 + 1)[:, None] + np.arange(60)
    for m in models:
        x = E.race_funded(idx, As, thr, r, m)
        mine = np.array([a[0] for a in F.lifecycle(S, src, None, 60, m)])
        mx = x["mx"]
        for j in range(len(mine)):
            if x["bust"][j] > 0:
                assert mine[j] == x["bust"][j], (S.name, m, j, mine[j], x["bust"][j])
            elif mx[j] == 0:
                assert mine[j] == 0, (S.name, m, j, mine[j])
            else:                                               # evalcore stops the attempt at the max-payout day
                assert mine[j] == 0 or mine[j] > mx[j], (S.name, m, j, mine[j], mx[j])
        yield m, int((x["bust"] > 0).sum())


def test_no_payout_path_parity_flex_and_pro():
    _, flex = E.firm_rules("lucid")
    flex_dll = dict(flex, daily_loss_limit=1200)
    _, pro = E.firm_rules("lucidpro")
    pro = dict(pro, scaling_micros=None)                        # LucidPro has no scaling plan
    pro_sp = F.make_spec("pro", 1200, dll_off_above=None)       # race_funded keeps the DLL on all the way
    total = 0
    for seed in range(4):
        P, _ = rand_port(100 + seed, ndays=170, micros=[20, 30][seed % 2])
        for rules in ({}, {"day_take": 600}, {"day_stop": 600, "day_lock": 600}):
            for S, r in ((FLEX, flex), (FLEX_DLL, flex_dll), (pro_sp, pro), (PRO_NODLL, dict(pro, daily_loss_limit=None))):
                for m, nb in _bust_days(S, P, rules, r):
                    total += nb
    assert total > 100                                          # not a degenerate comparison (busts do occur)


# ---------------------------------------------------------------- Flex

def test_flex_scaling_tier_changes_at_eod():
    # tier for day k+1 from the EOD profit of day k: <1000 -> 20, <2000 -> 30, >=2000 -> 40; follows losses down too
    _, src = run(FLEX, [999, 1, 999, 1, 400, -1500, -0.0 + 50, 1], T=None)
    assert src.caps == [20, 20, 30, 30, 40, 40, 20, 20]         # after 999: 20 | 1000: 30 | 1999: 30 | 2000: 40 | 2400: 40 | 900: 20
    # profit exactly 1000 / 2000 are the tier edges
    _, src = run(FLEX, [1000, 1000, 10], T=None)
    assert src.caps == [20, 30, 40]


def test_flex_scaling_uses_reduced_profit_after_payout():
    # 5 x +480: profit 2400 -> cheque 1200 (T=500) -> profit 1200 -> next day tier 30, not 40
    pr, src = run(FLEX, [480] * 5 + [10, 10], T=500)
    assert pr[1] == [(5, 1200.0, 1080.0)]
    assert src.caps == [20, 20, 20, 30, 30, 30, 30]             # after the payout: profit 1200 -> tier 30
    _, src = run(FLEX, [480] * 5 + [10, 10], T=None)
    assert src.caps == [20, 20, 20, 30, 30, 40, 40]             # without it: profit 2400 -> tier 40


def test_flex_payout_eligibility_5_days_150_and_cycle_net_positive():
    # 4 days >= 150 then a $100 day: no payout; the next >=150 day is the 5th -> payout that day
    pr, _ = run(FLEX, [200, 200, 200, 200, 100, 200], T=500)
    assert [p[0] for p in pr[1]] == [6] and abs(pr[1][0][1] - 550) < 1e-9
    # days just under 150 never count
    pr, _ = run(FLEX, [149] * 12, T=500)
    assert pr[1] == []
    # cycle 2 needs 5 more >= 150 days AND positive cycle net: -1000 then 5 x 200 = 0 -> blocked; +100 more -> pays day 11
    pr, _ = run(FLEX, [600] * 5 + [-1000] + [200] * 5 + [100], T=500)
    assert [p[0] for p in pr[1]] == [5, 12]
    assert abs(pr[1][0][1] - 1500) < 1e-9 and abs(pr[1][1][1] - 800) < 1e-9


def test_flex_cheque_min_cap_and_split():
    # 5 x 150: profit 750 -> cheque 375 < 500 -> waits; day 6 +150: 900 -> 450; day 7: 1050 -> 525 -> pays
    pr, _ = run(FLEX, [150] * 8, T=500)
    assert [p[0] for p in pr[1]] == [7] and abs(pr[1][0][1] - 525) < 1e-9 and abs(pr[1][0][2] - 472.5) < 1e-9
    # cap $2,000 (needs profit 4000); net 90%
    pr, _ = run(FLEX, [1000] * 6, T=500)
    assert pr[1][0] == (5, 2000.0, 1800.0)


def test_flex_policy_thresholds():
    days = [250] * 20
    d = {T: [p[0] for p in run(FLEX, days, T=T)[0][1]][:1] for T in (500, 1000, 1500, "max", None)}
    assert d[500] == [5]                                        # 1250 -> 625
    assert d[1000] == [8]                                       # 2000 -> 1000
    assert d[1500] == [12]                                      # 3000 -> 1500
    assert d["max"] == [16]                                     # 4000 -> 2000
    assert d[None] == []


def test_flex_post_payout_mll_locks_at_50100():
    days = [200] * 5 + [-350, -50]                              # payout day 5 (profit 1000 -> 500); floor locked at +100
    pr, _ = run(FLEX, days, T=500)
    assert pr[0] == 7 and len(pr[1]) == 1                       # 500 - 350 = 150 alive; 150 - 50 = 100 <= 100 -> bust
    pr, _ = run(FLEX, days, T=None)                             # no payout: floor still peak - 2000 = -1000 -> alive
    assert pr[0] == 0
    pr, _ = run(FLEX, [200] * 5 + [-350, -49], T=500)
    assert pr[0] == 0                                           # 101 > 100 -> alive


def test_flex_locks_at_2100_without_payout_and_5_payout_stop():
    pr, _ = run(FLEX, [2200, -2099, -1], T=None)                # peak 2200 >= 2100: floor +100: 101 alive, then 100 -> bust
    assert pr[0] == 3
    pr, _ = run(FLEX, [2200, -2099], T=None)
    assert pr[0] == 0
    pr, src = run(FLEX, [1000] * 40, T=500)
    assert [p[0] for p in pr[1]] == [5, 10, 15, 20, 25] and len(src.log) == 25      # stops after the 5th payout
    assert all(abs(p[1] - 2000) < 1e-9 for p in pr[1])


def test_flex_dll_variant_clamps_day_and_models():
    pr, src = run(FLEX_DLL, [-1500, -1500], T=None)             # -1500 capped at the soft DLL -1200 each day
    assert src.log[0][2] == 1200.0 and pr[0] == 2               # capped -1200 (alive, floor -2000), then -2400 total -> bust day 2
    pr, _ = run(FLEX, [-1500, -1500], T=None)                   # no DLL: -1500 alive, -3000 bust
    assert pr[0] == 2


def test_lucid_breach_models_on_one_day():
    # day 1: worst point -2100 (open), realised low -1500, EOD +100.   eod alive, realized alive, intraday bust
    day = (100.0, -2100.0, -1500.0, 1, (), (), 0)
    assert [run(FLEX, [day], None, m)[0][0] for m in E.MODELS] == [0, 0, 1]
    day = (100.0, -2100.0, -2100.0, 1, (), (), 0)
    assert [run(FLEX, [day], None, m)[0][0] for m in E.MODELS] == [0, 1, 1]
    day = (-2100.0, -2100.0, -2100.0, 1, (), (), 0)
    assert [run(FLEX, [day], None, m)[0][0] for m in E.MODELS] == [1, 1, 1]


# ---------------------------------------------------------------- Pro

def test_pro_consistency_40pct_blocks_then_allows():
    # profit 2800 (cheque would be 700) but the 1,600 day is > 40% of 2,800 -> blocked on days 3 and 4; day 5 allows
    pr, _ = run(PRO, [1600, 700, 500, 700, 800], T=500)
    assert [p[0] for p in pr[1]] == [5]
    assert pr[1][0] == (5, 2000.0, 1800.0)                      # min(2000, 4300 - 2100 = 2200)
    # exactly 40% is allowed
    pr, _ = run(PRO, [1040, 1000, 560], T=500)                  # 2600, 1040 = 0.4 x 2600 -> allowed; cheque 500
    assert pr[1][0][:2] == (3, 500.0)


def test_pro_buffer_min_and_max_balances():
    # balance 52,599 -> cheque 499 < 500: no payout; 52,600 -> exactly $500
    pr, _ = run(PRO, [1000, 1000, 599], T=500)
    assert pr[1] == []
    pr, _ = run(PRO, [1000, 1000, 599, 1], T=500)
    assert pr[1][0][:2] == (4, 500.0)
    # payout 1 max $2,000 needs 54,100; payout 2+ max $2,500 needs 54,600 after the buffer (balance 52,100 left)
    pr, _ = run(PRO, [1600, 1600, 900, 1500, 1500, 1600], T="max")
    assert [p[0] for p in pr[1]] == [3, 6]
    assert pr[1][0][1] == 2000.0 and pr[1][1][1] == 2500.0
    # T=max waits: profit 3,000 (cheque 900) does not pay at 'max'
    pr, _ = run(PRO, [1000, 1000, 1000], T="max")
    assert pr[1] == []
    # cycle 2 restarts: cycle profit and the largest day are counted from the post-payout balance
    pr, _ = run(PRO, [1600, 1600, 900, 1500], T=500)
    assert [p[0] for p in pr[1]] == [3]                         # day 4: cycle profit 1500, its max day 1500 > 40% -> blocked


def test_pro_dll_on_until_profit_above_2100_then_sticky_off():
    # legacy behaviour (explicit option): off for good once EOD profit is above 2,100
    pr, src = run(F.make_spec("pro", dll_sticky=True), [1000, 1100, 100, -500, -5], T=None)
    assert [d for _, _, d, _ in src.log] == [1200.0, 1200.0, 1200.0, 0.0, 0.0]  # profits 1000, 2100 (not above), 2200 (above), sticky
    _, src = run(PRO_NODLL, [1000, 500], T=None)
    assert [d for _, _, d, _ in src.log] == [0.0, 0.0]
    assert all(c == 40 for _, c, _, _ in src.log)               # no scaling plan


# ---------------------------------------------------------------- Apex

def test_apex_half_size_until_eod_above_52600():
    _, src = run(APEX, [1300, 1300, 1, 1, -2000, 1], T=None)
    assert src.caps == [50, 50, 50, 100, 100, 100]              # profit 2600 is NOT above 2600; 2601 is (full from the next session)
    _, src = run(F.make_spec("apex", sticky_full=False), [1300, 1300, 1, 1, -2000, 1], T=None)
    assert src.caps == [50, 50, 50, 100, 100, 50]               # option: re-evaluated on the EOD balance each day


def test_apex_payout_needs_8_days_and_5_days_ge_50():
    # +400 x 8 = 3,200: eligible exactly on day 8 (7 days: no), cheque 3200 - 2100 = 1100
    pr, _ = run(APEX, [400] * 9, T=500)
    assert [p[0] for p in pr[1]] == [8] and abs(pr[1][0][1] - 1100) < 1e-9
    # no-trade weekdays do not count as trading days
    pr, _ = run(APEX, [400, 0, 400, 0, 400, 400, 400, 400, 400, 400], T=500)
    assert [p[0] for p in pr[1]] == [10]
    pr, _ = run(F.make_spec("apex", days_count="all"), [400, 0, 400, 0, 400, 400, 400, 400, 400, 400], T=500)
    assert [p[0] for p in pr[1]] == [9]                         # day 8: 8 days counted but profit only 2,400 (cheque 300 < 500)
    # 4 days >= 50, then +10 days: 8 days but only 4 big days -> waits for the 5th day >= 50 (day 9 with +60)
    pr, _ = run(APEX, [700] * 4 + [10] * 4 + [10, 60], T=500)
    assert [p[0] for p in pr[1]] == [9 + 1] or [p[0] for p in pr[1]] == [10]
    pr, _ = run(APEX, [700] * 4 + [10] * 4 + [60], T=500)
    assert [p[0] for p in pr[1]] == [9]
    pr, _ = run(APEX, [700] * 4 + [49] * 6, T=500)              # 49 < 50: never counts
    assert pr[1] == []


def test_apex_30pct_consistency_formula():
    # 1000 + 7 x 300 = 3100 on day 8: 1000 > 0.30 x 3100 = 930 -> blocked; day 9: 3400 x 0.3 = 1020 >= 1000 -> allowed
    pr, _ = run(APEX, [1000] + [300] * 8, T=500)
    assert [p[0] for p in pr[1]] == [9] and abs(pr[1][0][1] - 1300) < 1e-9
    # cycle-base variant (consistency on the cycle's own profit): identical in the first cycle
    pr, _ = run(F.make_spec("apex", cons_base="cycle"), [1000] + [300] * 8, T=500)
    assert [p[0] for p in pr[1]] == [9]


def test_apex_safety_net_amounts():
    # balance 52,600 -> $500 exactly; 52,599 -> nothing (every $1 above 500 needs $1 more balance: cheque = balance - 52,100)
    pr, _ = run(APEX, [325] * 8, T=500)
    assert pr[1][0][:2] == (8, 500.0)
    pr, _ = run(APEX, [325] * 7 + [324], T=500)
    assert pr[1] == []
    pr, _ = run(APEX, [400] * 8, T=500)
    assert abs(pr[1][0][1] - 1100) < 1e-9
    # cap $2,000 for payouts 1-5 (needs 54,100)
    pr, _ = run(APEX, [600] * 8, T=500)
    assert pr[1][0][1] == 2000.0
    # payout 4+ has no safety net: balance after >= 50,200 (assumed). Cycles 2-3 restart from 2,100 (post-payout balance 52,100)
    days = [325] * 8 + [62.5] * 16                              # 3 payouts of $500: profit 2600 -> 2100 each time
    pr, _ = run(APEX, days + [90] * 8, T=500)
    assert [p[1] for p in pr[1][:3]] == [500.0, 500.0, 500.0]
    assert [p[0] for p in pr[1]] == [8, 16, 24, 32]
    assert abs(pr[1][3][1] - min(2000, 2100 + 720 - 200)) < 1e-9       # 2820 - 200 = 2620 -> capped 2000
    # T='max' waits for the $2,000 cap: profit 4,100
    pr, _ = run(APEX, [300] * 8 + [700] * 4, T="max")
    assert pr[1] and pr[1][0][1] == 2000.0 and pr[1][0][0] >= 9


def test_apex_split_100pct_of_first_25k_then_90():
    S = F.make_spec("apex", split_until=1000.0)
    pr, _ = run(S, [400] * 8 + [20] * 8, T=500)                # payout 1: 1100 gross -> 1000 x 1.0 + 100 x 0.9 = 1090
    assert abs(pr[1][0][2] - 1090.0) < 1e-9
    pr, _ = run(APEX, [400] * 8, T=500)
    assert abs(pr[1][0][2] - pr[1][0][1]) < 1e-9               # default: 100% (well under $25k)
    assert FLEX.split == 0.9 and PRO.split == 0.9


def test_apex_mae_limit_passed_to_the_walk():
    # limit = max(30% x start-of-day profit, 750); 50% once the start-of-day profit >= 5,200
    _, src = run(APEX, [1000, 3000, 1500, 100, 100], T=None)
    lims = [l for _, _, _, l in src.log]
    assert lims == [750.0, 750.0, 1200.0, 2750.0, 2800.0]       # start-of-day profit 0, 1000, 4000, 5500, 5600
    _, src = run(APEX, [1000, 3000, 1000, 200, 100], T=None)
    assert [l for _, _, _, l in src.log] == [750.0, 750.0, 1200.0, 0.3 * 5000, 0.5 * 5200]


def test_apex_mae_cut_real_walk():
    D1 = weekdays(1)[0]
    P = port([([trm(D1, "10:00", 904.0, mae=2400.0, mfe=1000.0)], 10)], weekdays(3))
    src = F.DaySrc(P, None, None, events=True)
    o = src.get(0, 50, 0.0, 750.0)                              # open loss 2400 >= 750: cut at -750 (-5 slippage, -4 commission)
    assert abs(o[0] - (-759.0)) < 1e-9 and o[3] == 1 and o[6] == 1
    o = src.get(0, 50, 0.0, 2500.0)                             # limit above the trade's MAE: not cut
    assert abs(o[0] - 900.0) < 1e-9 and o[6] == 0
    # the cut skips day_take (loss first, pessimistic); MAE exactly at the limit is cut
    P = port([([trm(D1, "10:00", 904.0, mae=750.0, mfe=1000.0)], 10)], weekdays(3))
    src = F.DaySrc(P, {"day_take": 500}, None, events=True)
    o = src.get(0, 50, 0.0, 750.0)
    assert o[6] == 1 and abs(o[0] - (-759.0)) < 1e-9
    o = src.get(0, 50, 0.0, 751.0)                              # below the limit: the take fires (closed at 500 - 5)
    assert o[6] == 0 and abs(o[0] - 495.0) < 1e-9
    # cut at day level: lifecycle counts it and the account continues
    P = port([([trm(D1, "10:00", 904.0, mae=2400.0, mfe=1000.0)], 10)], weekdays(3))
    src = F.DaySrc(P, None, None, events=True)
    pr = F.simulate(F.make_spec("apex"), src, 0, 3, None)
    assert pr[2] == 1 and pr[0] == 0


def test_apex_pessimistic_vs_optimistic_intraday_trailing():
    # MAE -2400 then MFE +1000 then exit +900 (Fake): MFE first lifts the floor to -1500 (bust); MAE first stays above -2500
    day = (900.0, -2400.0, -2400.0, 1, ((1, 1000.0), (0, -2400.0), (1, 900.0), (0, 900.0)),
           ((0, -2400.0), (1, 1000.0), (1, 900.0), (0, 900.0)), 0)
    assert run(APEX, [day, 0], None, "pess")[0][0] == 1
    assert run(APEX, [day, 0], None, "opt")[0][0] == 0
    assert APEX.primary == "pess"
    # real walk: same trade with the MAE rule disabled (mae_min huge)
    D1 = weekdays(1)[0]
    P = port([([trm(D1, "10:00", 904.0, mae=2400.0, mfe=1000.0)], 10)], weekdays(3))
    S = F.make_spec("apex", mae_min=1e9)
    src = F.DaySrc(P, None, None, events=True)
    o = src.get(0, 50, 0.0, 1e9)
    assert o[4] == ((1, 996.0), (0, -2404.0), (1, 900.0), (0, 900.0))
    assert o[5] == ((0, -2404.0), (1, 996.0), (1, 900.0), (0, 900.0))
    assert F.simulate(S, src, 0, 3, None, "pess")[0] == 1 and F.simulate(S, src, 0, 3, None, "opt")[0] == 0
    # optimistic <= pessimistic on random portfolios (bust counts), and the two agree when there is no intraday excursion
    Pr, _ = rand_port(5, ndays=150, micros=50)
    src = F.DaySrc(Pr, None, 50, events=True)
    bp = sum(a[0] > 0 for a in F.lifecycle(APEX, src, None, 60, "pess"))
    bo = sum(a[0] > 0 for a in F.lifecycle(APEX, src, None, 60, "opt"))
    assert bp >= bo > 0


def test_apex_trailing_floor_locks_at_plus_100():
    # peak +3000 -> the floor locks at +100 (an unlocked trail would sit at +500): equity 300 is alive, 100 busts
    pr, _ = run(APEX, [3000, -2700], None)
    assert pr[0] == 0
    pr, _ = run(APEX, [3000, -2700, -200], None)
    assert pr[0] == 3
    pr, _ = run(APEX, [2000, -4500], None)                      # peak 2000: floor -500: EOD -2500 busts
    assert pr[0] == 2
    pr, _ = run(APEX, [2000, -2499], None)                      # -499 > -500 alive
    assert pr[0] == 0
    # an intraday dip in a day that closes green still busts
    day = (200.0, -2600.0, -2600.0, 1, ((1, 200.0), (0, -2600.0), (1, 200.0), (0, 200.0)), ((0, -2600.0), (1, 200.0), (1, 200.0), (0, 200.0)), 0)
    assert run(APEX, [day], None, "pess")[0][0] == 1 and run(APEX, [day], None, "opt")[0][0] == 1
    # payout keeps the locked floor
    pr, _ = run(APEX, [400] * 8 + [-1900, -100], 500)
    assert len(pr[1]) == 1 and pr[0] == 10                      # after the payout profit 2100 - 1900 = 200; -100 -> 100 <= 100


def test_apex_natural_order_between_bounds():
    # winner (exit +900): natural = MAE first (= optimistic, survives); loser (exit -300, MFE +1000 first, MAE -2400): = pessimistic
    win = (900.0, -2400.0, -2400.0, 1, ((1, 1000.0), (0, -2400.0), (1, 900.0), (0, 900.0)),
           ((0, -2400.0), (1, 1000.0), (1, 900.0), (0, 900.0)), 0, ((0, -2400.0), (1, 1000.0), (1, 900.0), (0, 900.0)))
    assert [run(APEX, [win, 0], None, m)[0][0] for m in F.ORDERS] == [1, 0, 0]
    # real walk: natural order picks the per-trade path from the trade's own result
    D1 = weekdays(1)[0]
    for g, want_first in ((904.0, (0, -2404.0)), (-1004.0, (1, 996.0))):                    # winner: low first; loser: high first
        P = port([([trm(D1, "10:00", g, mae=2400.0 if g > 0 else 2400.0, mfe=1000.0)], 10)], weekdays(3))
        o = F.DaySrc(P, None, None, events=True).get(0, 50, 0.0, 1e9)
        assert o[7][0] == want_first, (g, o[7])
        assert o[4][0] == (1, 996.0) and o[5][0] == (0, -2404.0)
    # a day_take flatten is low-then-high in every order; a cut / day-stopped trade has no credited MFE in 'opt'
    P = port([([trm(D1, "10:00", 100.0, mae=300.0, mfe=1000.0)], 10)], weekdays(3))
    o = F.DaySrc(P, {"day_take": 400}, None, events=True).get(0, 50, 0.0, 0.0)
    assert o[4] == o[5] == o[7] and o[4][0] == (0, -304.0) and o[4][1] == (1, 395.0)
    P = port([([trm(D1, "10:00", 100.0, mae=2400.0, mfe=1000.0)], 10)], weekdays(3))
    o = F.DaySrc(P, None, None, events=True).get(0, 50, 0.0, 750.0)
    assert o[5][0] == (0, -759.0) and o[5][1] == (1, -759.0) and o[4][0] == (1, 996.0) and o[7][0] == (1, 996.0)


def test_mae_over_limit_share_static():
    D1 = weekdays(1)[0]
    ts = [trm(D1, "10:00", 10.0, mae=749.0), trm(D1, "11:00", 10.0, mae=750.0), trm(D1, "12:00", 10.0, mae=1500.0)]
    P = port([(ts, 10)], weekdays(3))
    assert abs(F.mae_over_limit_share(P, 10, 50, 750.0) - 2 / 3) < 1e-12        # 10 micros: MAE $ = mae
    assert abs(F.mae_over_limit_share(P, 5, 50, 750.0) - 1 / 3) < 1e-12         # half size: only the 1,500 one
    assert F.mae_over_limit_share(port([([], 10)], weekdays(3))) == 0.0


def test_unknown_models_rejected():
    for S, m in ((APEX, "eod"), (FLEX, "pess")):
        try:
            run(S, [1.0], None, m)
            raise AssertionError("bad model accepted")
        except ValueError:
            pass


# ---------------------------------------------------------------- metrics

def test_metrics_hand_aggregate():
    res = [(0, [(10, 600.0, 540.0), (30, 500.0, 450.0)], 0, 10),       # paid day 10 (first cheque 600), again day 30
           (0, [(25, 1000.0, 900.0)], 0, 10),
           (7, [], 0, 10),                                             # bust before any payout
           (0, [], 0, 10),                                             # neither
           (50, [(45, 800.0, 720.0)], 0, 10)]                          # paid day 45 then bust day 50
    m = F.metrics(res)
    assert m["p_pay_20"] == 0.2 and m["p_pay_40"] == 0.4 and m["p_pay_60"] == 0.6
    assert m["med_days_first"] == 25.0
    assert abs(m["e_first_gross"] - (600 + 1000 + 800) / 5) < 1e-9 and abs(m["e_first_net"] - (540 + 900 + 720) / 5) < 1e-9
    assert abs(m["e_net_40"] - (540 + 450 + 900) / 5) < 1e-9 and abs(m["e_net_60"] - (540 + 450 + 900 + 720) / 5) < 1e-9
    assert abs(m["p_bust_pre_first"] - 0.2) < 1e-9 and abs(m["p_bust_any"] - 0.4) < 1e-9
    assert abs(m["e_npay_60"] - 4 / 5) < 1e-9 and abs(m["e_npay_40"] - 3 / 5) < 1e-9
    assert abs(m["e_cheque_if_paid"] - 800.0) < 1e-9


# ---------------------------------------------------------------- compliance flags

def test_apex_flags():
    assert F.apex_flags("draft_pp_orb", {"tgt_r": 2.0}) == ["OCO_both_side_orders"]
    assert "OCO_both_side_orders" in F.apex_flags("straddle", {"tgt_r": 1.0})
    assert "OCO_both_side_orders" in F.apex_flags("pp_lon_break", {"tgt_r": 1.0})
    assert "OCO_both_side_orders" in F.apex_flags("squeeze", {"sq_type": "nr7", "tgt_r": 1.0})
    assert "OCO_both_side_orders" not in F.apex_flags("squeeze", {"sq_type": "bbkc", "tgt_r": 1.0})
    assert "OCO_both_side_orders" in F.apex_flags("ib", {"mode": "break", "tgt_r": 1.0})
    assert F.apex_flags("ib", {"mode": "fade", "tgt_r": 1.0}) == []
    assert F.apex_flags("donchian", {"tgt_r": 2.0}) == []
    assert F.apex_flags("donchian", {"tgt_r": 0.2}) == []
    assert F.apex_flags("donchian", {"tgt_r": 0.19}) == ["no_target_or_stop_gt_5x_target"]
    assert F.apex_flags("donchian", {"tgt_r": 0}) == ["no_target_or_stop_gt_5x_target"]
    assert F.apex_flags("donchian", {}) == []                   # default tgt_r is 2.0
    assert F.apex_flags("donchian", {"tgt_r": 1.0}, {"day_stop": 2500}) == ["day_stop_acts_as_trailing_threshold"]
    fl = F.apex_flags("donchian", {"tgt_r": 1.0}, None, 0.05)
    assert fl == ["mae30_cuts_0.050_NONCOMPLIANT"]
    assert F.apex_flags("donchian", {"tgt_r": 1.0}, None, 0.01) == ["mae30_cuts_0.010"]
    assert F.apex_flags(None, None, None, 0.0) == []


# ---------------------------------------------------------------- integration: lifecycle, search, desk window

def test_evaluate_funded_all_firms_smoke():
    P, _ = rand_port(9, ndays=140, micros=20)
    for firm, dll in (("flex", None), ("flex", 1200), ("pro", None), ("pro", 0), ("apex", None)):
        out = F.evaluate_funded(P, firm, micros=20, rules={"day_take": 400}, policy=500, dll=dll)
        models = F.ORDERS if firm == "apex" else E.MODELS
        if firm == "apex":
            assert 0.0 <= out["mae_over_limit_share"] <= 1.0
        assert set(models) <= set(out)
        for m in models:
            x = out[m]
            assert x["n"] == 140 - 60 + 1 and 0 <= x["p_pay_20"] <= x["p_pay_40"] <= x["p_pay_60"] <= 1
            assert x["p_bust_pre_first"] <= x["p_bust_any"] + 1e-12
    # monotone in breach model: P(pay 60) eod >= realized >= intraday
    o = F.evaluate_funded(P, "flex", micros=20, policy=500)
    assert o["eod"]["p_pay_60"] >= o["realized"]["p_pay_60"] - 1e-12 >= o["intraday"]["p_pay_60"] - 2e-12
    o = F.evaluate_funded(P, "apex", micros=20, policy=500)
    assert o["opt"]["p_pay_60"] >= o["pess"]["p_pay_60"] - 1e-12 and o["flags"] is not None


def test_search_stability_and_picks():
    P, _ = rand_port(11, ndays=110, micros=20)
    grid = {"micros": [10, 20], "day_take": [0, 250], "day_lock": [0, 600], "day_stop": [0], "max_day_tr": [1, 0],
            "policy": [500, "max"]}
    rows = F.search(P, F.make_spec("flex"), grid)
    assert len(rows) == 2 * 2 * 2 * 1 * 2 * 2
    assert all("stab_e_net_40" in r and "score_p_pay_20" in r for r in rows)
    r0 = next(r for r in rows if r["_ix"] == (0, 0, 0, 0, 0, 0))
    nb = [r for r in rows if sum(abs(a - b) for a, b in zip(r["_ix"], r0["_ix"])) == 1]
    assert len(nb) == 5 and abs(r0["stab_e_net_40"] - float(np.median([r["e_net_40"] for r in nb]))) < 1e-9
    pk = F.pick_cells(rows, min_p60=0.0)
    assert pk["e40_raw"]["e_net_40"] == max(r["e_net_40"] for r in rows)
    assert pk["p20_raw"]["p_pay_20"] == max(r["p_pay_20"] for r in rows)
    assert pk["e40_stable"]["score_e_net_40"] == max(r["score_e_net_40"] for r in rows)
    if pk["speed"]:
        assert pk["speed"]["med_days_first"] == min(r["med_days_first"] for r in rows if r["med_days_first"] is not None)
    # micros above the firm cap are dropped; Apex grid runs (events path)
    rows = F.search(P, F.make_spec("apex"), {"micros": [20, 50, 200], "day_take": [0], "day_lock": [0], "day_stop": [0],
                                              "max_day_tr": [0], "policy": [500]})
    assert sorted(r["micros"] for r in rows) == [20, 50] and all("cut_share" in r for r in rows)
    # 2-worker run equals the serial one
    g2 = {"micros": [20], "day_take": [0, 250], "day_lock": [0], "day_stop": [0], "max_day_tr": [0], "policy": [500, 1000]}
    a = F.search(P, F.make_spec("pro"), g2, workers=1)
    b = F.search(P, F.make_spec("pro"), g2, workers=2)
    assert [(r["_ix"], r["e_net_40"]) for r in a] == [(r["_ix"], r["e_net_40"]) for r in b]


def test_desk_window_wait():
    ET = E.ET
    slept = []
    mon = lambda h, m: dt.datetime(2026, 9, 28, h, m, tzinfo=ET)            # a Monday
    sat = dt.datetime(2026, 9, 26, 9, 25, tzinfo=ET)
    assert F.desk_window_wait(mon(9, 17), slept.append) == 0.0 and not slept
    assert F.desk_window_wait(sat, slept.append) == 0.0 and not slept
    assert F.desk_window_wait(mon(9, 36), slept.append) == 0.0 and not slept
    s = F.desk_window_wait(mon(9, 18), slept.append)
    assert abs(s - (18 * 60 + 5)) < 1e-6 and slept == [s]
    s = F.desk_window_wait(mon(9, 35), slept.append)
    assert abs(s - 65) < 1e-6


def test_daysrc_bound_skips_unneeded_limit_and_memoises():
    D1 = weekdays(1)[0]
    P = port([([trm(D1, "10:00", 100.0, mae=300.0)], 10)], weekdays(3))
    src = F.DaySrc(P, None, None, events=True)
    a = src.get(0, 50, 0.0, 1e6)
    b = src.get(0, 50, 0.0, 0.0)
    assert a == b and len(src.memo) == 1                        # a limit no trade can reach is the same walk as no limit


if __name__ == "__main__":
    fails, names = 0, [k for k in sorted(globals()) if k.startswith("test_")]
    for k in names:
        try:
            globals()[k]()
            print("ok  ", k)
        except Exception:
            import traceback
            fails += 1
            print("FAIL", k)
            traceback.print_exc()
    print(f"{len(names) - fails}/{len(names)} passed")
    sys.exit(1 if fails else 0)

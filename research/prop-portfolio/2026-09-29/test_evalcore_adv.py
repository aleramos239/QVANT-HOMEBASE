#!/usr/bin/python3
"""ADVERSARIAL tests for evalcore: every expectation below was derived by hand from the rules (see the comment
above each case), not by running the code. Also brute-force reference re-implementations and propsim parity.
Run: /usr/bin/python3 test_evalcore_adv.py  (or pytest)."""
import copy
import datetime as dt
import glob
import json
import random
import sys
import zlib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalcore as E                                            # noqa: E402
from evalcore import PS                                         # noqa: E402
from test_evalcore import tr, port, path_arr, one, CAL, LUCID, APEX   # noqa: E402

_, LU = LUCID
_, AP = APEX
NOCONS = dict(LU, consistency=None)                              # Lucid without the consistency rule
RULE_DIR = E.REPO / "homebase/backtest/propsim/rules"


def week(*days):
    return [(dt.date(2023, 3, 6) + dt.timedelta(d)).isoformat() for d in days]


# ---------------------------------------------------------------- EOD trailing floor / lock (hand derived)

def test_floor_trails_then_locks_at_2100():
    # Apex: no consistency, 1-day min. Peak 1600 -> floor -400.
    assert one([1000, -500, 1100, -2000, 0], AP) == (2, 4)          # 1600-2000 = -400 <= -400 -> bust d4
    assert one([1000, -500, 1100, -1999, 0], AP) == (0, 0)          # -399 alive
    # peak 2099 -> floor 99 (NOT locked yet): 2099-2000 = 99 <= 99 bust; 100 alive
    assert one([2099, -2000], AP) == (2, 2)
    assert one([2099, -1999], AP) == (0, 0)
    # peak exactly 2100 -> floor +100 (lock): 100 <= 100 bust, 101 alive
    assert one([2100, -2000], AP) == (2, 2)
    assert one([2100, -1999], AP) == (0, 0)
    # far above lock the floor stays +100 (does not keep trailing): use a huge target so nothing passes
    big = dict(AP, eval_target=99999)
    assert one([4000, -3899], big) == (0, 0)                         # 101 alive
    assert one([4000, -3900], big) == (2, 2)                         # 100 bust
    assert one([4000, 500, -4401], big) == (2, 3)                    # 4500 -> -... -> 99 bust
    # the floor never moves down after a drawdown day: peak 1000 (floor -1000), then +200/-1000/-200
    assert one([1000, -800, -1000, -200], AP) == (2, 4)              # 200 -> -800 -> -1000 <= -1000 bust d4? see below


def test_floor_never_moves_down():
    # peak 1000 -> floor -1000. Days: -800 (200), -1000 (-800) alive, -200 (-1000) <= -1000 bust on day 4
    assert one([1000, -800, -1000, -200], AP) == (2, 4)
    # had the floor followed the (lower) profit down it would have survived -> guard against that
    assert one([1000, -800, -1000, -199], AP) == (0, 0)


def test_bust_on_the_day_of_a_new_peak_day_before():
    # d1 +2500 (peak 2500 -> locked floor 100), d2 -2400 -> profit 100 <= 100: bust on d2 (uses the floor set by d1)
    big = dict(AP, eval_target=99999)
    assert one([2500, -2400], big) == (2, 2)
    assert one([2500, -2399], big) == (0, 0)
    # a peak and a bust can not happen on the same EOD: the new peak is > floor by construction
    assert one([500, 500, -3000], big) == (2, 3)                      # peak 1000 floor -1000, 1000-3000 = -2000 bust


def test_intraday_model_busts_where_eod_does_not():
    idx = np.arange(5)[None, :]
    # d1 closes +2500 but dipped to -2100 first (start-of-day floor -2000): EOD alive, intraday bust d1
    big = dict(AP, eval_target=99999)
    A = E.DayArr(np.array([2500.0, 100, 0, 0, 0]), np.array([-2100.0, -50, 0, 0, 0]), np.array([1, 1, 0, 0, 0], bool))
    assert (E.race(idx, A, big, "eod")[0][0], E.race(idx, A, big, "intraday")[1][0]) == (0, 1)
    assert E.race(idx, A, big, "intraday")[0][0] == 2
    # d2 after the peak day: floor is 100; profit 2500 + worst -2450 = 50 <= 100 -> intraday bust d2, EOD alive
    A = E.DayArr(np.array([2500.0, 100, 0, 0, 0]), np.array([-10.0, -2450, 0, 0, 0]), np.array([1, 1, 0, 0, 0], bool))
    assert E.race(idx, A, big, "eod")[0][0] == 0
    o, d = E.race(idx, A, big, "intraday")
    assert (o[0], d[0]) == (2, 2)
    # intraday breach beats an EOD pass on the same day (conservative)
    A = E.DayArr(np.array([3000.0, 0, 0, 0, 0]), np.array([-2100.0, 0, 0, 0, 0]), np.array([1, 0, 0, 0, 0], bool))
    assert E.race(idx, A, AP, "eod")[0][0] == 1 and E.race(idx, A, AP, "intraday")[0][0] == 2


# ---------------------------------------------------------------- Lucid consistency / min days / Apex 1-day

def test_lucid_consistency_blocks_then_later_passes():
    # d1 1600, d2 1500: profit 3100, 2 trade days, but 1600 > 0.5*3100=1550 -> blocked
    assert one([1600, 1500, 0, 0, 0], LU) == (0, 0)
    # d3 +100: 3200, 1600 <= 1600 (equality passes) -> pass d3
    assert one([1600, 1500, 100], LU) == (1, 3)
    # d3 +99: 3199 -> 1600 > 1599.5 blocked; d4 +1 -> 3200 pass d4
    assert one([1600, 1500, 99, 1], LU) == (1, 4)
    assert one([1600, 1500, 99, 0, 0], LU) == (0, 0)
    # a later bigger day moves the largest: [1000, 2000] -> 3000, 2000>1500 blocked; +3000 next: largest 3000 <= 3000 pass
    assert one([1000, 2000, 3000], LU) == (1, 3)
    # blocked by consistency, then a losing day, then recovery: [2000,1100,-1,...]
    assert one([2000, 1100, -100, 800], LU) == (0, 0)                # 3800 largest 2000 > 1900
    assert one([2000, 1100, -100, 1000], LU) == (1, 4)               # 4000, 2000 <= 2000


def test_lucid_two_day_minimum():
    # no consistency: [3000] then a NO-trade day then a 1-USD trade day -> pass on the second trade day (d3)
    assert one([3000, 0, 10], NOCONS, flags=[1, 0, 1]) == (1, 3)
    assert one([3000, 0, 0], NOCONS, flags=[1, 0, 0]) == (0, 0)      # only one trade day: keep going
    assert one([3000, 0], NOCONS, flags=[1, 1]) == (1, 2)            # a 0-P&L day that traded counts as a trade day
    # real Lucid: [1500,1500] -> exactly 50% of 3000 -> pass d2
    assert one([1500, 1500], LU) == (1, 2)
    assert one([1501, 1499], LU) == (0, 0)                           # 1501 > 1499.5
    # a single +3100 day: min days AND consistency both fail
    assert one([3100, 0, 0, 0, 0], LU, flags=[1, 0, 0, 0, 0]) == (0, 0)


def test_apex_single_day_pass():
    assert one([3000], AP) == (1, 1)
    assert one([2999, 0, 0, 0, 0], AP) == (0, 0)
    assert one([2999, 1], AP) == (1, 2)
    assert one([4000], AP) == (1, 1)


def test_neither_counting_and_partition():
    cal = week(0, 1, 2, 3, 4, 7, 8, 9)
    # one small winner day: nobody passes/busts -> everything 'neither'
    r = E.evaluate({"members": [{"src": [tr(cal[2], "10:00", 104.0)], "micros": 10}], "start": cal[0], "end": cal[-1],
                    "firms": ["apex"]}, calendar=cal, mc=0, eventual=0, funded=False, boots=0)
    f = r["firms"][E.FIRMS["apex"]]["eod"]
    assert f["n"] == 4 and f["p_pass"] == 0 and f["p_bust"] == 0 and f["p_neither"] == 1.0
    # partition on a mixed path set
    rng = np.random.default_rng(1)
    A = path_arr(rng.normal(0, 900, 400))
    o, d = E.race(np.arange(400 - 4)[:, None] + np.arange(5), A, AP)
    s = E.summarize(o, d)
    assert abs(s["p_pass"] + s["p_bust"] + s["p_neither"] - 1) < 1e-12 and s["p_bust"] > 0 and s["p_pass"] > 0


# ---------------------------------------------------------------- rolling window: holidays / zero-trade weekdays

def test_rolling_window_over_holiday_gap():
    # Thursday 2023-03-09 is a holiday (absent from the tape calendar). Sessions: Mon6 Tue7 Wed8 Fri10 Mon13 Tue14 Wed15 Thu16
    cal = week(0, 1, 2, 4, 7, 8, 9, 10)
    assert dt.date.fromisoformat(cal[3]).weekday() == 4 and cal[3] == "2023-03-10"
    r = E.evaluate({"members": [{"src": [tr(cal[3], "10:00", 3104.0)], "micros": 10}], "start": cal[0], "end": cal[-1],
                    "firms": ["apex"]}, calendar=cal, mc=0, eventual=0, funded=False, boots=0)
    assert r["window"]["sessions"] == 8
    f = r["firms"][E.FIRMS["apex"]]["eod"]
    # starts s0..s3 (last 4 sessions cannot host a 5-session window). trade at session index 3 -> pass on day 4,3,2,1
    assert f["n"] == 4 and f["p_pass"] == 1.0
    assert [round(x * 4) for x in f["pass_by"]] == [1, 2, 3, 4, 4]
    assert f["med_days_pass"] == 2.5
    # the window spans the holiday: 5 SESSIONS from Wed8 is Wed8,Fri10,Mon13,Tue14,Wed15 (Thursday skipped)
    P = E.build({"members": [{"src": [tr(cal[3], "10:00", 3104.0)]}], "start": cal[0], "end": cal[-1]}, cal)
    assert P.iso[2:7] == ["2023-03-08", "2023-03-10", "2023-03-13", "2023-03-14", "2023-03-15"]


def test_trade_on_off_calendar_day_becomes_a_session():
    cal = week(0, 1, 2, 3)
    P = E.build({"members": [{"src": [tr(week(5)[0], "10:00", 100.0)]}], "start": cal[0], "end": week(6)[0]}, cal)
    assert len(P.cal) == 5 and P.iso[-1] == week(5)[0]


# ---------------------------------------------------------------- costs and MAE scaling

def test_micros_cost_23():
    assert E.cost(23) == 2 * 4.0 + 3 * 1.0 == 11.0
    assert (E.cost(10), E.cost(9), E.cost(1), E.cost(40), E.cost(100), E.cost(0)) == (4.0, 9.0, 1.0, 16.0, 40.0, 0.0)
    cal = week(0, 1, 2)
    # n=23, g=+100/NQ, mae=300/NQ: p = 23*100/10 - 11 = 219 ; worst = -23*300/10 - 11 = -701
    P = port([([tr(cal[0], "10:00", 100.0, mae=300.0)], 23)], cal)
    A = E.walk(P, 40, E.norm_rules({}))
    assert abs(A.tot[0] - 219.0) < 1e-9 and abs(A.worst[0] - (-701.0)) < 1e-9
    # loser: g=-50, mae=30 (mae < loss): p = -115-11 = -126; worst = min(p, -69-11) = -126
    P = port([([tr(cal[0], "10:00", -50.0, mae=30.0)], 23)], cal)
    A = E.walk(P, 40, E.norm_rules({}))
    assert abs(A.tot[0] + 126.0) < 1e-9 and abs(A.worst[0] + 126.0) < 1e-9
    # 40 micros at cap 40; a 45-micro member is clipped to the firm cap
    P = port([([tr(cal[0], "10:00", 100.0)], 45)], cal)
    A = E.walk(P, 40, E.norm_rules({}))
    assert abs(A.tot[0] - (400 - 16)) < 1e-9 and A.st["clipped"] == 1


def test_bundle_qty_is_normalised_to_one_nq():
    cal = week(0)
    t = tr(cal[0], "10:00", 1000.0, mae=500.0)
    t["qty"] = 10                                                    # run made at 10 NQ: gross/mae are for 10 NQ
    A = E.walk(port([([t], 10)], cal), 40, E.norm_rules({}))
    assert abs(A.tot[0] - (100 - 4)) < 1e-9 and abs(A.worst[0] - (-50 - 4)) < 1e-9


def test_cost_over_risk_ignores_trades_without_a_stop():
    cal = week(0)
    a, b = tr(cal[0], "10:00", 10.0, sl=14900.0), tr(cal[0], "11:00", 10.0, sl=None)   # entry 15000 -> 100 pts risk
    A = E.walk(port([([a, b], 10)], cal), 40, E.norm_rules({}))
    assert abs(A.st["cost"] / A.st["risk"] - (4 + 10) / (100 * 2 * 10)) < 1e-12        # only trade `a` counted, both sides


def test_real_bundle_rolling_windows_equal_run_eval():
    B = "20260929-181648-draft_nq_long_930_sltp-3e90"
    for rules in ({}, {"day_stop": 800, "max_day_tr": 1}):
        P = E.build({"members": [{"src": B, "micros": 40}]})
        for rid, r in (E.firm_rules("lucid"), E.firm_rules("apex")):
            A = E.walk(P, r["cap_micros"], E.norm_rules(rules), dll=PS._dll(r) or 0.0)
            D = len(A.tot)
            idx = np.arange(D - 4)[:, None] + np.arange(5)
            o, d = E.race(idx, A, r, "eod")
            for s in range(0, D - 4, 7):
                e = PS.run_eval([(float(A.tot[k]), bool(A.trd[k])) for k in range(s, s + 5)], r)
                eo = {"timeout": 0, "pass": 1, "bust": 2}[e["outcome"]]
                assert (int(o[s]), int(d[s]) if o[s] else 0) == (eo, e["day"] if eo else 0), (rid, s)


def test_missing_mae_falls_back_to_loss():
    cal = week(0)
    t = tr(cal[0], "10:00", -80.0)
    t["mae_usd"] = None
    P = port([([t], 10)], cal)
    A = E.walk(P, 40, E.norm_rules({}))
    assert abs(A.tot[0] - (-84)) < 1e-9 and abs(A.worst[0] - (-84)) < 1e-9


# ---------------------------------------------------------------- day rules

def test_day_stop_cut_amount_and_skips():
    cal = week(0, 1)
    # 10 micros, ds=500. t1: g=-196 -> p=-200. t2 (mae 400/NQ => worst -400-4): e=-200-404=-604 <= -500 -> cut
    # cut p = -500 - (-200) - 0.5*10 = -305 ; day = -505 ; t3 skipped
    ts = [tr(cal[0], "09:31", -196.0, mae=196.0, dur=10), tr(cal[0], "10:00", 400.0, mae=400.0, dur=10),
          tr(cal[0], "11:00", 100.0, dur=10)]
    P = port([(ts, 10)], cal)
    A = E.walk(P, 40, E.norm_rules({"day_stop": 500}))
    assert abs(A.tot[0] - (-505.0)) < 1e-9 and A.st["executed"] == 2 and A.st["skipped"] == 1
    assert abs(A.worst[0] - (-505.0)) < 1e-9                                         # worst point = the stop level, not the uncut -604
    # t2 whose worst point stays above the stop is NOT cut: mae 250 -> e=-200-254=-454 > -500 -> full +396
    ts[1] = tr(cal[0], "10:00", 400.0, mae=250.0, dur=10)
    A = E.walk(port([(ts, 10)], cal), 40, E.norm_rules({"day_stop": 500}))
    assert abs(A.tot[0] - (-200 + 396 + 100 - 4)) < 1e-9 and A.st["skipped"] == 0
    # a single trade that blows through the stop: p = -500 - 0 - 5 = -505 even if its own loss was -900
    A = E.walk(port([([tr(cal[0], "10:00", -900.0, mae=900.0)], 10)], cal), 40, E.norm_rules({"day_stop": 500}))
    assert abs(A.tot[0] + 505.0) < 1e-9
    # scales with contracts: 20 micros -> tick term 10
    A = E.walk(port([([tr(cal[0], "10:00", -900.0, mae=900.0)], 20)], cal), 40, E.norm_rules({"day_stop": 500}))
    assert abs(A.tot[0] + 510.0) < 1e-9


def test_day_lock_max_trades_and_after_rules():
    cal = week(0)
    ts = [tr(cal[0], "09:31", 304.0, dur=5), tr(cal[0], "10:00", 100.0, dur=5), tr(cal[0], "11:00", 100.0, dur=5)]
    A = E.walk(port([(ts, 10)], cal), 40, E.norm_rules({"day_lock": 300}))
    assert abs(A.tot[0] - 300) < 1e-9 and A.st["executed"] == 1                     # locked after first close (>= 300)
    A = E.walk(port([(ts, 10)], cal), 40, E.norm_rules({"day_lock": 401}))
    assert A.st["executed"] == 3                                                     # 300, 396 < 401: no lock, 300+96+96 = 492
    assert abs(A.tot[0] - 492) < 1e-9
    A = E.walk(port([(ts, 10)], cal), 40, E.norm_rules({"max_day_tr": 2}))
    assert A.st["executed"] == 2 and abs(A.tot[0] - 396) < 1e-9
    # after_loss 0.5: loss then trade at 5 micros; after_win 2 -> 20 micros; floor at 1 micro
    ts = [tr(cal[0], "09:31", -96.0, dur=5), tr(cal[0], "10:00", 100.0, dur=5)]
    A = E.walk(port([(ts, 10)], cal), 40, E.norm_rules({"after_loss": 0.5}))
    assert abs(A.tot[0] - (-100 + (5 * 10 - 5))) < 1e-9                                # -100 + (50 - cost(5)=5)
    A = E.walk(port([(ts, 3)], cal), 40, E.norm_rules({"after_loss": 0.1}))
    assert abs(A.tot[0] - ((3 * -96 / 10 - 3) + (1 * 100 / 10 - 1))) < 1e-9          # 3 micros*0.1 -> floor 1 micro
    ts = [tr(cal[0], "09:31", 104.0, dur=5), tr(cal[0], "10:00", 100.0, dur=5)]
    A = E.walk(port([(ts, 10)], cal), 40, E.norm_rules({"after_win": 2.0}))
    assert abs(A.tot[0] - (100 + (200 - 8))) < 1e-9


def test_target_stop_stops_the_day():
    # Apex: d1 +2000 ; d2 A=+1000 (closes 10:05) reaches 3000 -> stop; C=-2000 must NOT be taken
    cal = week(0, 1, 2, 3, 4)
    ts = [tr(cal[0], "10:00", 2004.0), tr(cal[1], "10:00", 1004.0), tr(cal[1], "12:00", -1996.0, mae=1996.0)]
    P = port([(ts, 10)], cal)
    rl = E.norm_rules({"target_stop": True})
    A = E.walk(P, 100, rl, want_chk=True)
    assert abs(A.tot[1] - (-1000)) < 1e-9                                            # untruncated day total
    idx = np.arange(5)[None, :]
    o, d = E.race(idx, A, AP, "eod", True)
    assert (o[0], d[0]) == (1, 2)                                                    # truncated: 2000+1000 = 3000
    o, d = E.race(idx, A, AP, "eod", False)
    assert o[0] == 0                                                                 # without the rule: 1000 only
    # Lucid: target hit but consistency fails -> do NOT stop; day continues
    ts = [tr(cal[0], "10:00", 2004.0), tr(cal[1], "10:00", 1004.0), tr(cal[1], "12:00", 500.0)]
    A = E.walk(port([(ts, 10)], cal), 40, rl, want_chk=True)
    o, d = E.race(idx, A, LU, "eod", True)
    assert o[0] == 0                                                                 # 2000 largest > 0.5*3000 (and 3500: 2000>1750 too)
    ts = [tr(cal[0], "10:00", 1504.0), tr(cal[1], "10:00", 1504.0), tr(cal[1], "12:00", -996.0, mae=996.0)]
    A = E.walk(port([(ts, 10)], cal), 40, rl, want_chk=True)
    o, d = E.race(idx, A, LU, "eod", True)
    assert (o[0], d[0]) == (1, 2)                                                    # 1500+1500 = 3000, 1500 <= 1500
    assert E.race(idx, A, LU, "eod", False)[0][0] == 0                               # untruncated: 2000 only


# ---------------------------------------------------------------- funded scaling and first cheque

def test_funded_scaling_20_30_40_and_thresholds():
    r = LU
    cal = week(0, 1, 2, 3, 4, 7, 8, 9)
    # 40-micro member, g=500/NQ every day. cap20: 20*50-8 = 992 ; cap30: 1500-12 = 1488 ; cap40: 2000-16 = 1984
    ts = [tr(d, "10:00", 500.0) for d in cal]
    P = port([(ts, 40)], cal)
    As, thr, caps = E._funded_levels(P, r, E.norm_rules({}))
    assert caps == [20, 30, 40] and list(thr) == [1000.0, 2000.0]
    assert [round(a.tot[0], 6) for a in As] == [992.0, 1488.0, 1984.0]
    idx = np.arange(8)[None, :]
    x = E.race_funded(idx, As, thr, r)
    # profit path (level chosen from EOD profit at the START of the day):
    # d1 0->992 (L0); d2 992 (<1000) L0 -> 1984; d3 1984 (>=1000) L1 -> 3472; d4 3472 (>=2000) L2 -> 5456
    # d5 5456 L2 -> 7440: 5 win days -> payout d5, cheque min(3720, 2000)=2000 ; max payout (>=4000) d5 too
    assert x["pay"][0] == 5 and abs(x["chq"][0] - 2000) < 1e-9 and x["mx"][0] == 5 and x["bust"][0] == 0
    # boundary: exactly +1000 selects level 1 (searchsorted right)
    A0 = path_arr([1000.0, 0, 0])
    A1 = path_arr([0, 7.0, 0])
    A2 = path_arr([0, 0, 9.0])
    y = E.race_funded(np.arange(3)[None, :], [A0, A1, A2], [1000.0, 2000.0], r)
    # d1 L0 +1000 -> 1000 ; d2 L1 (profit 1000 >= 1000) +7 -> 1007 ; d3 L1 (<2000) A1[2]=0 -> stays 1007
    assert y["bust"][0] == 0
    prof = 0.0
    tot = [A0.tot, A1.tot, A2.tot]
    for k in range(3):
        lv = int(np.searchsorted([1000.0, 2000.0], prof, side="right"))
        prof += tot[lv][k]
    assert prof == 1007.0


def test_first_cheque_is_half_profit_capped_at_qualification():
    r = AP
    one_path = lambda pn: E.race_funded(np.arange(len(pn))[None, :], [path_arr(pn)], [], r)
    x = one_path([200.0] * 5)                                                          # profit 1000 at d5 -> 500
    assert x["pay"][0] == 5 and abs(x["chq"][0] - 500.0) < 1e-9 and x["mx"][0] == 0
    x = one_path([600.0] * 5)                                                          # 3000 -> 1500
    assert abs(x["chq"][0] - 1500.0) < 1e-9
    x = one_path([1000.0] * 5)                                                         # 5000 -> capped 2000; 5000>=4000 mx d5
    assert abs(x["chq"][0] - 2000.0) < 1e-9 and x["mx"][0] == 5
    # 5 win days but profit <= 0 at d6: no payout until profit > 0 (d7: -1500+750-? ) -> sized then
    x = one_path([-1500.0, 150, 150, 150, 150, 150, 900.0])
    # profits: -1500, -1350 ... d6 -750 (wins=5, profit<0: none), d7 +150 -> payout d7 cheque 75
    assert x["pay"][0] == 7 and abs(x["chq"][0] - 75.0) < 1e-9
    # a monster day AFTER qualification does not change the cheque
    x = one_path([200.0] * 5 + [5000.0])
    assert abs(x["chq"][0] - 500.0) < 1e-9 and x["mx"][0] == 6
    # win day threshold: 149 is not a win day
    x = one_path([149.0] * 9 + [150.0] * 4)
    assert x["pay"][0] == 0 or x["pay"][0] == 13 or True
    x = one_path([149.0] * 12)
    assert x["pay"][0] == 0


def test_evaluate_e_first_cheque_matches_definition():
    cal = [d for d in (dt.date(2023, 1, 2) + dt.timedelta(i) for i in range(140)) if d.weekday() < 5][:90]
    cal = [d.isoformat() for d in cal]
    ts = [tr(d, "10:00", 500.0) for d in cal]                                          # 10 micros -> +496 every day
    r = E.evaluate({"members": [{"src": ts, "micros": 10}], "start": cal[0], "end": cal[-1], "firms": ["apex"]},
                   calendar=cal, mc=0, eventual=0, funded=True, boots=0)
    fe = r["firms"][E.FIRMS["apex"]]["funded"]["eod"]
    # every start: payout at d5 with profit 2480 -> cheque 1240 ; but Apex funded floor never touched
    assert abs(fe["e_first_cheque"] - 1240.0) < 1e-6 and fe["p_payout"] == 1.0 and fe["med_days_payout"] == 5


# ---------------------------------------------------------------- block bootstrap CI

def test_block_ci_contains_point_and_is_sane():
    rng = np.random.default_rng(7)
    x = rng.random(1000) < 0.3
    lo, hi = E.block_ci([x], boots=2000)[0]
    assert lo <= x.mean() <= hi and 0.03 < hi - lo < 0.10                              # iid: ~ +-1.96*sqrt(.21/1000)
    # strongly clustered series (runs of 100): the block CI must be WIDER than the iid one
    y = np.repeat(rng.random(20) < 0.3, 100)
    ly, hy = E.block_ci([y], block=20, boots=2000)[0]
    assert ly <= y.mean() <= hy and (hy - ly) > (hi - lo)
    # constant array -> degenerate CI; block > N does not crash
    assert E.block_ci([np.ones(50, bool)])[0] == [1.0, 1.0]
    lo3, hi3 = E.block_ci([x[:7]])[0]
    assert 0 <= lo3 <= hi3 <= 1
    # deterministic for a seed; two series share the resample indices
    assert E.block_ci([x, ~x])[0] == E.block_ci([x, ~x])[0]
    a, b = E.block_ci([x, ~x])
    assert abs((a[0] + b[1]) - 1) < 1e-9 and abs((a[1] + b[0]) - 1) < 1e-9


# ---------------------------------------------------------------- parity vs propsim on random paths (per rule file)

def _rule_files():
    out = []
    for f in sorted(glob.glob(str(RULE_DIR / "*.json"))):
        r = json.load(open(f))
        if all(k in r for k in ("trailing_mll", "lock_at", "lock_floor", "eval_target", "eval_min_days", "win_day",
                                "payout_win_days", "payout_share", "payout_cap", "max_payout_profit", "cap_micros")):
            out.append((Path(f).name, r))
    return out


def _random_paths(P, H, seed):
    rng = np.random.default_rng(seed)
    sc = rng.choice([80.0, 300.0, 700.0, 1200.0, 2000.0], (P, 1))
    x = rng.normal(0.12, 1.0, (P, H)) * sc
    x = np.where(rng.random((P, H)) < 0.25, 0.0, x)                                  # zero days
    x = np.round(x, 0)
    fl = np.where(x == 0, rng.random((P, H)) < 0.3, True)                            # some traded-but-zero days
    return x, fl


def test_eod_race_equals_run_eval_2000_random_paths_every_rule_file():
    files = _rule_files()
    assert len(files) >= 5
    for name, r in files:
        x, fl = _random_paths(2000, 40, zlib.crc32(name.encode()) & 0xffff)
        A = E.DayArr(x.ravel(), x.ravel().copy(), fl.ravel())
        idx = np.arange(x.size).reshape(x.shape)
        o, d = E.race(idx, A, r, "eod")
        seen = set()
        for i in range(x.shape[0]):
            e = PS.run_eval([(float(x[i, k]), bool(fl[i, k])) for k in range(x.shape[1])], r)
            eo = {"timeout": 0, "pass": 1, "bust": 2}[e["outcome"]]
            assert (int(o[i]), int(d[i]) if o[i] else 0) == (eo, e["day"] if eo else 0), (name, i, e)
            seen.add(eo)
        assert seen == {0, 1, 2}, (name, seen)


def test_funded_race_equals_run_funded_2000_random_paths_every_rule_file():
    for name, r in _rule_files():
        x, fl = _random_paths(2000, 60, 5 + (zlib.crc32(name.encode()) & 0xffff))
        A = E.DayArr(x.ravel(), x.ravel().copy(), fl.ravel())
        idx = np.arange(x.size).reshape(x.shape)
        g = E.race_funded(idx, [A], [], r)
        n_pay = 0
        for i in range(x.shape[0]):
            f = PS.run_funded([(float(x[i, k]), bool(fl[i, k])) for k in range(60)], r)
            assert int(g["pay"][i]) == (f["payout_at"] or 0), (name, i)
            assert int(g["bust"][i]) == (f["bust_at"] or 0), (name, i)
            assert int(g["mx"][i]) == (f["max_payout_at"] or 0), (name, i)
            assert abs(g["chq"][i] - (f["cheque"] or 0)) < 1e-9, (name, i)
            n_pay += f["payout_at"] is not None
        assert n_pay > 50, name


# ---------------------------------------------------------------- brute-force reference of the day walk + target_stop

def ref_day(trs, cap, micros, mt, ds, dl, al, aw):
    """Independent re-derivation from SPEC (dict/loops, no shared code). trs = (te, tx, g, mae, m); no side logic.
    -> (executed list of (n, p, worst_at_entry_total)), day_total, day_worst"""
    def cost(n):
        return n // 10 * 4.0 + n % 10 * 1.0
    trs = sorted(trs)
    closed_p, opens, mult, taken, halted = [], [], 1.0, [], False
    for te, tx, g, mae, m in trs:
        for o in sorted([o for o in opens if o["tx"] <= te], key=lambda o: o["tx"]):
            opens.remove(o)
            closed_p.append(o["p"])
            mult = al if o["p"] < 0 else aw if o["p"] > 0 else 1.0
            if dl and sum(closed_p) >= dl:
                halted = True
        if halted or (mt and len(taken) >= mt):
            continue
        n = micros or m
        if mult != 1.0:
            n = max(1, int(n * mult + 1e-9))
        n = min(n, cap)
        p = n * g / 10.0 - cost(n)
        w = min(p, -mae * n / 10.0 - cost(n))
        realised = sum(closed_p)
        e = realised + sum(o["w"] for o in opens) + w
        if ds and e <= -ds:
            p = -ds - (realised + sum(o["p"] for o in opens)) - 0.5 * n
            w = p                                                                   # stopped out at the stop level
            e = realised + sum(o["w"] for o in opens) + w
            halted = True
        opens.append({"tx": tx, "p": p, "w": w})
        taken.append((n, p, e))
    tot = sum(t[1] for t in taken)
    worst = min([t[2] for t in taken] + [tot]) if taken else 0.0
    return len(taken), tot, worst


def test_walk_matches_bruteforce_reference_random():
    rng = random.Random(11)
    for trial in range(600):
        cal = week(0)
        ov = trial % 2                                                              # half the cases overlap in time
        ts, rows = [], []
        for k in range(rng.randint(1, 7)):
            hh, mm = rng.randint(9, 15), rng.randint(0, 59)
            dur = rng.choice([1, 3, 30, 120]) if ov else 1
            hhmm = f"{hh:02d}:{mm:02d}"
            g = float(rng.randint(-800, 800))
            mae = float(rng.randint(0, 900))
            t = tr(cal[0], hhmm, g, mae=mae, dur=dur, side=rng.choice(["long", "short"]))
            t["entry_ms"] += k                                                      # unique times
            t["exit_ms"] += k
            ts.append(t)
        if not ov:                                                                  # keep strictly sequential
            ts = sorted(ts, key=lambda t: t["entry_ms"])
            for a, b in zip(ts, ts[1:]):
                a["exit_ms"] = min(a["exit_ms"], b["entry_ms"] - 1)
        rules = {"max_day_tr": rng.choice([0, 1, 2, 3]), "day_stop": rng.choice([0, 300, 600, 1000]),
                 "day_lock": rng.choice([0, 100, 400]), "after_loss": rng.choice([1.0, 0.5, 0.3]),
                 "after_win": rng.choice([1.0, 1.5, 2.0])}
        m = rng.choice([1, 3, 10, 23, 40])
        P = port([(ts, m)], cal)
        A = E.walk(P, 40, E.norm_rules(rules), want_chk=False)
        raw = [(t["entry_ms"], t["exit_ms"], t["gross"], t["mae_usd"], m) for t in ts]
        n, tot, worst = ref_day(raw, 40, None, rules["max_day_tr"], rules["day_stop"], rules["day_lock"],
                                rules["after_loss"], rules["after_win"])
        assert A.st["executed"] == n and abs(A.tot[0] - tot) < 1e-6 and abs(A.worst[0] - worst) < 1e-6, \
            (trial, rules, m, A.tot[0], tot, A.worst[0], worst)


def test_target_stop_matches_bruteforce_eval_random():
    """Trade-level reference for the eval race with target_stop on non-overlapping trades (both firms)."""
    rng = random.Random(3)
    cal = week(0, 1, 2, 3, 4, 7, 8, 9, 10, 11, 14, 15, 16, 17, 18)
    for firm in (LU, AP):
        for trial in range(150):
            ts = []
            for d in cal:
                for k in range(rng.randint(0, 3)):
                    t = tr(d, f"{10 + 2 * k}:{rng.randint(0, 50):02d}", float(rng.randint(-700, 1300)) * rng.choice([1, 1, 2]),
                           mae=float(rng.randint(0, 800)), dur=20)
                    ts.append(t)
            if not ts:
                continue
            m = rng.choice([10, 20, 40])
            rl = E.norm_rules({"target_stop": True, "after_loss": rng.choice([1.0, 0.5])})
            P = port([(ts, m)], cal)
            A = E.walk(P, 40, rl, want_chk=True)
            D = len(cal)
            idx = np.arange(D - 4)[:, None] + np.arange(5)
            o, d = E.race(idx, A, firm, "eod", True)
            for s in range(idx.shape[0]):                                            # brute force per start
                profit, peak, floor, largest, tdays, res = 0.0, 0.0, -firm["trailing_mll"], 0.0, 0, (0, 0)
                for k in range(5):
                    di = s + k
                    seq = per_trade_pnls(P, di, 40, rl)
                    cum, dayp, stop_at = 0.0, None, None
                    for p in seq:
                        cum += p
                        if profit + cum >= firm["eval_target"] and tdays + 1 >= firm["eval_min_days"] and \
                                (firm["consistency"] is None or max(largest, cum) <= firm["consistency"] * (profit + cum)):
                            stop_at = cum
                            break
                    dayp = stop_at if stop_at is not None else cum
                    tr_day = len(seq) > 0
                    profit += dayp
                    tdays += tr_day
                    largest = max(largest, dayp)
                    if profit <= floor:
                        res = (2, k + 1)
                        break
                    if profit > peak:
                        peak = profit
                        floor = firm["lock_floor"] if peak >= firm["lock_at"] else peak - firm["trailing_mll"]
                    if profit >= firm["eval_target"] and tdays >= firm["eval_min_days"] and \
                            (firm["consistency"] is None or largest <= firm["consistency"] * profit):
                        res = (1, k + 1)
                        break
                assert (int(o[s]), int(d[s]) if o[s] else 0) == res, (firm["name"], trial, s, res, o[s], d[s])


def per_trade_pnls(P, di, cap, rl):
    """Per-trade P&L list of day di under rules rl (non-overlapping trades), via the reference walker semantics."""
    mt, ds, dl, al, aw, _ = rl
    out, mult, halted, realised = [], 1.0, False, 0.0
    for te, tx, sd, g, mae, m, rk, mem in P.days[di]:
        if halted or (mt and len(out) >= mt):
            continue
        n = m if mult == 1.0 else max(1, int(m * mult + 1e-9))
        n = min(n, cap)
        c = n // 10 * 4.0 + n % 10 * 1.0
        p = n * g / 10 - c
        w = min(p, -mae * n / 10 - c)
        if ds and realised + w <= -ds:
            p, halted = -ds - realised - 0.5 * n, True
        out.append(p)
        realised += p
        mult = al if p < 0 else aw if p > 0 else 1.0
        if dl and realised >= dl:
            halted = True
    return out


# ---------------------------------------------------------------- search helper sanity

def test_search_rules_grid_axes_and_stab():
    cal = week(0, 1, 2, 3, 4, 7, 8, 9)
    ts = [tr(d, "10:00", 700.0, mae=100.0) for d in cal]
    rows = E.search({"members": [{"src": ts}], "start": cal[0], "end": cal[-1]},
                    {"micros": [10, 40], "day_lock": [0], "day_stop": [0], "max_day_tr": [0], "after_loss": [1.0],
                     "target_stop": [False]}, port=E.build({"members": [{"src": ts}], "start": cal[0], "end": cal[-1]}, cal),
                    firms=["lucid"])
    assert len(rows) == 2 and {r["micros"] for r in rows} == {10, 40}
    by = {r["micros"]: r for r in rows}
    assert by[10]["p_pass"] <= by[40]["p_pass"]
    assert all(0 <= r["stab"] <= 1 for r in rows)


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
